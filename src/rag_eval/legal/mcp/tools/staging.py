from __future__ import annotations

import datetime
from collections.abc import Sequence

import asyncpg
from pydantic import BaseModel

from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.ingestion.staging.models import (
    ChunkReviewStatus,
    StagingChunk,
    StagingChunkDelta,
    StagingEdge,
    StagingEdgeFilter,
    StagingStatus,
    StgReparentResult,
)
from rag_eval.legal.ingestion.staging.session import StagingDocumentSession
from rag_eval.legal.mcp.tools.schemas import (
    ChunkFinalizeStatus,
    ChunkProgressStats,
    RelationTypeFilter,
    StagingStatusFilter,
    StgAddEdgesResult,
    StgCommitResult,
    StgFinalizeResult,
    StgGetChunkResult,
    StgGetRawResult,
    StgGrepResult,
    StgGrepScope,
    StgListSessionsResult,
    StgPatchResult,
    StgPollPendingResult,
    StgPreviewHit,
    StgPreviewResult,
    StgRemoveEdgeResult,
    StgReopenResult,
)
from rag_eval.legal.schemas import (
    E_AST_GROUNDING_VALIDATION,
    E_INVALID_DOCUMENT_HIERARCHY,
    LegalDomainError,
    validate_ltree_path,
)


class LegalStagingTools:
    """Encapsulates local staging session operations on disk (.cache/stg) with transparent database hydration."""

    def __init__(
        self,
        staging_manager: StagingManager | None = None,
        pool: asyncpg.Pool | None = None,
    ) -> None:
        self._staging = staging_manager or StagingManager()
        self._pool = pool

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            from rag_eval.legal.db.connection import get_db_pool

            self._pool = await get_db_pool()
        return self._pool

    async def _ensure_session(self, doc_code: str) -> StagingDocumentSession:
        return await self._staging.load_or_hydrate_session(
            doc_code=doc_code, pool=await self._get_pool()
        )

    async def stg_preview(
        self,
        doc_code: str,
        path_prefix: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StgPreviewResult:
        session = await self._ensure_session(doc_code)
        chunks = session.chunks
        if path_prefix:
            clean_pre = validate_ltree_path(path_prefix)
            chunks = [c for c in chunks if c.path.startswith(clean_pre)]

        total_matched = len(chunks)
        windowed_chunks = chunks[offset : offset + limit]
        has_more = (offset + limit) < total_matched

        preview_hits = [
            StgPreviewHit(
                path=c.path,
                lead_sentence=c.lead_sentence,
                preview_text=c.verbatim_text[:120] + ("..." if len(c.verbatim_text) > 120 else ""),
                char_length=c.char_length or len(c.verbatim_text),
                is_truncated=len(c.verbatim_text) > 120,
                metadata=(c.metadata.model_dump() if isinstance(c.metadata, BaseModel) else dict(c.metadata or {})),
            )
            for c in windowed_chunks
        ]

        return StgPreviewResult(
            doc_code=session.doc_code,
            title=session.title,
            total_chunks=len(session.chunks),
            total_edges=len(session.edges),
            total_matched=total_matched,
            limit=limit,
            offset=offset,
            has_more=has_more,
            chunks=preview_hits,
        )

    async def stg_get_chunk(self, doc_code: str, path: str) -> StgGetChunkResult:
        session = await self._ensure_session(doc_code)
        clean_path = validate_ltree_path(path)
        chunk = session.get_chunk(clean_path)
        if chunk is None:
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=f"Đoạn quy phạm '{clean_path}' không tồn tại trong phiên làm việc cho văn bản '{doc_code}'.",
                data={"doc_code": doc_code, "path": clean_path},
            )
        return StgGetChunkResult(doc_code=doc_code, chunk=chunk)

    async def stg_get_raw(
        self, doc_code: str, start_line: int = 1, end_line: int = 100
    ) -> StgGetRawResult:
        session = await self._ensure_session(doc_code)
        window = session.get_raw_window(start_line=start_line, end_line=end_line)
        return StgGetRawResult(
            doc_code=window.doc_code,
            start_line=window.start_line,
            end_line=window.end_line,
            total_lines=window.total_lines,
            content=window.content,
        )

    async def stg_grep(
        self,
        doc_code: str,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        search_in: StgGrepScope = "ALL",
        limit: int = 50,
    ) -> StgGrepResult:
        session = await self._ensure_session(doc_code)
        matches = session.grep(
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            search_in=search_in,
            limit=limit,
        )
        return StgGrepResult(
            doc_code=doc_code,
            pattern=pattern,
            is_regex=is_regex,
            total_matches=len(matches),
            matches=matches,
        )

    async def stg_patch(
        self,
        doc_code: str,
        updated_chunks: Sequence[StagingChunkDelta | StagingChunk | dict[str, object]] | None = None,
        removed_paths: list[str] | None = None,
        cascade_breadcrumbs: bool = True,
    ) -> StgPatchResult:
        await self._ensure_session(doc_code)
        session = self._staging.patch_chunks(
            doc_code=doc_code,
            updated_chunks=updated_chunks,
            removed_paths=removed_paths,
            cascade_breadcrumbs=cascade_breadcrumbs,
            actor="AGENT",
        )
        last_diff = (
            session.mutation_history[-1].diff_payload
            if session.mutation_history and session.mutation_history[-1].diff_payload
            else {}
        )
        raw_fields = last_diff.get("fields_modified")
        return StgPatchResult(
            doc_code=doc_code,
            status="SUCCESS",
            updated_count=int(str(last_diff.get("updated_count") or len(updated_chunks or []))),
            cascaded_count=int(str(last_diff.get("cascaded_count") or 0)),
            removed_count=int(str(last_diff.get("removed_count") or len(removed_paths or []))),
            total_chunks_after_patch=len(session.chunks),
            fields_modified=[str(f) for f in raw_fields] if isinstance(raw_fields, list) else [],
        )

    async def stg_add_edges(
        self,
        doc_code: str,
        edges: Sequence[StagingEdge | dict[str, object]],
    ) -> StgAddEdgesResult:
        await self._ensure_session(doc_code)
        session = self._staging.add_edges(
            doc_code=doc_code,
            edges=edges,
            actor="AGENT",
        )
        return StgAddEdgesResult(
            doc_code=doc_code,
            status="SUCCESS",
            total_edges=len(session.edges),
        )

    async def stg_reparent(
        self,
        doc_code: str,
        old_path_prefix: str,
        new_path_prefix: str,
        dry_run: bool = False,
    ) -> StgReparentResult:
        await self._ensure_session(doc_code)
        _session, result = self._staging.reparent_node(
            doc_code=doc_code,
            old_path_prefix=old_path_prefix,
            new_path_prefix=new_path_prefix,
            dry_run=dry_run,
            actor="AGENT",
        )
        return result

    async def stg_commit(self, doc_code: str) -> StgCommitResult:
        session = await self._ensure_session(doc_code)

        unreviewed = [
            c.path
            for c in session.chunks
            if c.review_status == ChunkReviewStatus.PENDING
        ]
        if unreviewed:
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=(
                    f"Không thể commit văn bản '{doc_code}': còn {len(unreviewed)}/{len(session.chunks)} "
                    "đoạn quy phạm ở trạng thái PENDING. Thẩm định viên/Agent bắt buộc phải rà soát "
                    "100% các đoạn quy phạm trước khi phiên làm việc được phép cam kết."
                ),
                data={
                    "doc_code": doc_code,
                    "unreviewed_count": len(unreviewed),
                    "total_chunks": len(session.chunks),
                    "unreviewed_sample": unreviewed[:5],
                },
            )

        chunk_paths = {c.path for c in session.chunks}
        for edge in session.edges:
            if edge.source_path not in chunk_paths:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=f"Invalid edge source path '{edge.source_path}': chunk path does not exist in document '{doc_code}'.",
                    data={"doc_code": doc_code, "source_path": edge.source_path},
                )

        now = datetime.datetime.now(datetime.UTC)
        session = self._staging.update_session_status(
            doc_code=doc_code,
            status=StagingStatus.AGENT_COMMITTED,
            actor="AGENT",
            description=f"Agent completed staging session review and committed for {doc_code}.",
        )

        return StgCommitResult(
            doc_code=session.doc_code,
            status=StagingStatus.AGENT_COMMITTED.value,
            total_chunks=len(session.chunks),
            total_edges=len(session.edges),
            committed_at=now.isoformat(),
            message=f"Phiên làm việc cho văn bản '{doc_code}' đã được chuyển sang trạng thái AGENT_COMMITTED. Dữ liệu được ghi vào WAL và sẵn sàng cho chuyên viên pháp lý thẩm định, phê duyệt.",
        )

    async def stg_poll_pending_chunks(
        self,
        doc_code: str,
        limit: int = 10,
        path_prefix: str | None = None,
    ) -> StgPollPendingResult:
        await self._ensure_session(doc_code)
        chunks, stats = self._staging.poll_pending_chunks(
            doc_code=doc_code, limit=limit, path_prefix=path_prefix
        )
        stats_dict = dict(stats)
        progress_stats = ChunkProgressStats.model_validate(stats_dict)
        pending_val = int(str(stats.get("pending_count", 0)))
        return StgPollPendingResult(
            doc_code=doc_code,
            progress=progress_stats,
            limit=limit,
            has_more=pending_val > len(chunks),
            chunks=chunks,
        )

    async def stg_finalize_chunks(
        self,
        doc_code: str,
        paths: list[str],
    ) -> StgFinalizeResult:
        await self._ensure_session(doc_code)
        session, finalized_count, raw_results = self._staging.finalize_chunks(
            doc_code=doc_code, paths=paths, actor="AGENT"
        )
        pending_remaining = sum(
            1 for c in session.chunks if c.review_status == ChunkReviewStatus.PENDING
        )
        results = [
            ChunkFinalizeStatus.model_validate(r)
            for r in raw_results
        ]
        return StgFinalizeResult(
            doc_code=doc_code,
            status="SUCCESS",
            finalized_count=finalized_count,
            pending_remaining=pending_remaining,
            paths=paths,
            results=results,
        )

    async def stg_list_sessions(
        self, status: StagingStatusFilter | None = None
    ) -> StgListSessionsResult:
        summaries = self._staging.list_sessions()
        if status:
            clean_status = status.strip().upper()
            summaries = [
                s
                for s in summaries
                if s.status.value.upper() == clean_status
                or s.status.name.upper() == clean_status
            ]
        return StgListSessionsResult(
            total_sessions=len(summaries),
            sessions=summaries,
        )

    async def stg_reopen_session(
        self,
        doc_code: str,
        reason: str = "",
    ) -> StgReopenResult:
        """Reopens a PROMOTED statutory session into AMENDMENT status for patching and linkage."""
        now = datetime.datetime.now(datetime.UTC)
        await self._ensure_session(doc_code)
        session = self._staging.reopen_session_for_amendment(
            doc_code=doc_code,
            actor="AGENT",
            reason=reason or "Agent reopened session for amendment / errata",
        )
        return StgReopenResult(
            doc_code=doc_code,
            status=session.status.value,
            total_chunks=len(session.chunks),
            reopened_at=now.isoformat(),
            message=f"Phiên làm việc cho văn bản '{doc_code}' đã được mở lại ở trạng thái AMENDMENT. Các công cụ stg_patch, stg_add_edges, stg_finalize_chunks đã sẵn sàng.",
        )

    async def stg_remove_edge(
        self,
        doc_code: str,
        source_path: str = "",
        target_path: str | None = None,
        target_external_ref: str | None = None,
        relation_type: RelationTypeFilter | None = None,
        clear_all_targets: bool = False,
        edges: Sequence[StagingEdgeFilter | dict[str, object]] | None = None,
    ) -> StgRemoveEdgeResult:
        """Removes relational graph edge(s) from the staging session."""
        await self._ensure_session(doc_code)

        if edges:
            session, removed_count = self._staging.remove_edges(
                doc_code=doc_code,
                filters=edges,
                actor="AGENT",
            )
            target_repr = f"{len(edges)} edge filter(s)"
        else:
            if not source_path:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message="Bắt buộc phải cung cấp 'source_path' hoặc danh sách 'edges' khi xóa cạnh quan hệ đồ thị.",
                    data={"doc_code": doc_code},
                )
            if not target_path and not target_external_ref and not clear_all_targets:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=(
                        f"Thao tác xóa cạnh từ '{source_path}' yêu cầu phải chỉ định 'target_path' hoặc 'target_external_ref' "
                        "để xác định đúng cạnh cần xóa. Nếu thực sự muốn xóa toàn bộ mọi cạnh xuất phát từ nút này, "
                        "bắt buộc phải đặt 'clear_all_targets=True'."
                    ),
                    data={"doc_code": doc_code, "source_path": source_path},
                )
            flt = StagingEdgeFilter(
                source_path=source_path,
                target_path=target_path,
                target_external_ref=target_external_ref,
                relation_type=relation_type,
                clear_all_targets=clear_all_targets,
            )
            session, removed_count = self._staging.remove_edges(
                doc_code=doc_code,
                filters=[flt],
                actor="AGENT",
            )
            target_repr = target_path or target_external_ref or ("all targets" if clear_all_targets else "unknown")

        return StgRemoveEdgeResult(
            doc_code=doc_code,
            status="SUCCESS",
            removed_count=removed_count,
            total_edges=len(session.edges),
            message=f"Removed {removed_count} edge(s) from '{source_path or 'batch'}' to '{target_repr}' ({relation_type or 'ANY'}).",
        )
