from __future__ import annotations

import datetime
from collections.abc import Sequence

import asyncpg
from pydantic import BaseModel

from rag_eval.legal.errors import (
    E_AST_GROUNDING_VALIDATION,
    E_INVALID_DOCUMENT_HIERARCHY,
    LegalDomainError,
)
from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.ingestion.staging.service import StagingDomainService
from rag_eval.legal.schemas.domain import (
    ChunkDelta,
    GrepScope,
    RelationEdge,
    RelationEdgeFilter,
    StagingStatus,
    StatutoryChunk,
    StatutoryRelationType,
)
from rag_eval.legal.schemas.retrieval import (
    ChunkPreview,
    GrepResult,
    PreviewResult,
    RawTextResult,
)
from rag_eval.legal.schemas.staging import (
    BatchPatchRequest,
    BatchPatchResult,
    FinalizeChunksRequest,
    FinalizeChunksResult,
    MutationResult,
    PendingChunksResult,
    ReparentSubtreeRequest,
    ReparentSubtreeResult,
    SessionStatusResult,
    SessionSummary,
)
from rag_eval.legal.text import (
    validate_ltree_path,
)


class LegalStagingTools:
    """Encapsulates local staging session operations on disk (.cache/stg) with transparent database hydration."""

    def __init__(
        self,
        service: StagingDomainService | None = None,
        staging_manager: StagingManager | None = None,
        pool: asyncpg.Pool | None = None,
    ) -> None:
        self._service = service or StagingDomainService(
            staging_manager=staging_manager, pool=pool
        )

    async def stg_preview(
        self,
        doc_code: str,
        path_prefix: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PreviewResult:
        session = await self._service.get_session(doc_code)
        chunks = session.chunks
        if path_prefix:
            clean_pre = validate_ltree_path(path_prefix)
            chunks = [c for c in chunks if c.path.startswith(clean_pre)]

        total_matched = len(chunks)
        windowed_chunks = chunks[offset : offset + limit]
        has_more = (offset + limit) < total_matched

        preview_hits = [
            ChunkPreview(
                path=c.path,
                preview_text=c.verbatim_text[:120] + ("..." if len(c.verbatim_text) > 120 else ""),
                is_truncated=len(c.verbatim_text) > 120,
                metadata=(c.metadata.model_dump() if isinstance(c.metadata, BaseModel) else dict(c.metadata or {})),
            )
            for c in windowed_chunks
        ]

        return PreviewResult(
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

    async def stg_get_chunk(self, doc_code: str, path: str) -> StatutoryChunk:
        session = await self._service.get_session(doc_code)
        clean_path = validate_ltree_path(path)
        chunk = session.get_chunk(clean_path)
        if chunk is None:
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=f"Đoạn quy phạm '{clean_path}' không tồn tại trong phiên làm việc cho văn bản '{doc_code}'.",
                data={"doc_code": doc_code, "path": clean_path},
            )
        return chunk

    async def stg_get_raw(
        self, doc_code: str, start_line: int = 1, end_line: int = 100
    ) -> RawTextResult:
        session = await self._service.get_session(doc_code)
        return session.get_raw_window(start_line=start_line, end_line=end_line)

    async def stg_grep(
        self,
        doc_code: str,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        search_in: GrepScope = "ALL",
        limit: int = 50,
    ) -> GrepResult:
        session = await self._service.get_session(doc_code)
        matches = session.grep(
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            search_in=search_in,
            limit=limit,
        )
        return GrepResult(
            doc_code=doc_code,
            pattern=pattern,
            is_regex=is_regex,
            total_matches=len(matches),
            returned=len(matches),
            matches=matches,
        )

    async def stg_patch(
        self,
        doc_code: str,
        updated_chunks: Sequence[ChunkDelta | StatutoryChunk | dict[str, object]] | None = None,
        removed_paths: list[str] | None = None,
        cascade_breadcrumbs: bool = True,
    ) -> BatchPatchResult:
        parsed_deltas: list[ChunkDelta] = []
        if updated_chunks:
            for item in updated_chunks:
                if isinstance(item, ChunkDelta):
                    parsed_deltas.append(item)
                elif isinstance(item, StatutoryChunk):
                    parsed_deltas.append(
                        ChunkDelta(
                            path=item.path,
                            verbatim_text=item.verbatim_text,
                            contextualized_text=item.contextualized_text,
                            start_line=item.start_line,
                            end_line=item.end_line,
                            metadata=item.metadata,
                            effective_date=item.effective_date,
                            expiration_date=item.expiration_date,
                            review_status=item.review_status,
                            finalization_state=item.finalization_state,
                            dangling_dependencies=item.dangling_dependencies,
                        )
                    )
                elif isinstance(item, dict):
                    parsed_deltas.append(ChunkDelta.model_validate(item))

        cmd = BatchPatchRequest(
            updated_chunks=parsed_deltas,
            removed_paths=removed_paths or (),
        )
        _session, result = await self._service.patch_chunks(
            doc_code=doc_code,
            request=cmd,
            actor="AGENT",
            cascade_breadcrumbs=cascade_breadcrumbs,
        )
        return result

    async def stg_add_edges(
        self,
        doc_code: str,
        edges: Sequence[RelationEdge | dict[str, object]],
    ) -> MutationResult:
        parsed_edges: list[RelationEdge] = []
        for e in edges:
            if isinstance(e, RelationEdge):
                parsed_edges.append(e)
            elif isinstance(e, dict):
                parsed_edges.append(RelationEdge.model_validate(e))

        session, count = await self._service.add_edges(
            doc_code=doc_code, edges=parsed_edges, actor="AGENT"
        )
        return MutationResult(
            doc_code=doc_code,
            status="SUCCESS",
            affected_count=count,
            total_count=len(session.edges),
            message=f"Attached {count} relation edges.",
        )

    async def stg_reparent(
        self,
        doc_code: str,
        old_path_prefix: str,
        new_path_prefix: str,
        dry_run: bool = False,
    ) -> ReparentSubtreeResult:
        cmd = ReparentSubtreeRequest(
            old_path_prefix=old_path_prefix,
            new_path_prefix=new_path_prefix,
            dry_run=dry_run,
            actor="AGENT",
        )
        _session, result = await self._service.reparent_subtree(
            doc_code=doc_code, request=cmd
        )
        return result

    async def stg_commit(self, doc_code: str) -> SessionStatusResult:
        session = await self._service.commit_session(doc_code=doc_code, actor="AGENT")
        now = datetime.datetime.now(datetime.UTC)
        return SessionStatusResult(
            doc_code=session.doc_code,
            status=StagingStatus.AGENT_COMMITTED.value,
            total_chunks=len(session.chunks),
            total_edges=len(session.edges),
            transitioned_at=now.isoformat(),
            message=f"Phiên làm việc cho văn bản '{doc_code}' đã được chuyển sang trạng thái AGENT_COMMITTED. Dữ liệu được ghi vào WAL và sẵn sàng cho chuyên viên pháp lý thẩm định, phê duyệt.",
        )

    async def stg_poll_pending(
        self,
        doc_code: str,
        limit: int = 10,
        path_prefix: str | None = None,
    ) -> PendingChunksResult:
        chunks, progress_stats = await self._service.poll_pending_chunks(
            doc_code=doc_code, limit=limit, path_prefix=path_prefix
        )
        return PendingChunksResult(
            doc_code=doc_code,
            progress=progress_stats,
            limit=limit,
            has_more=progress_stats.pending_count > len(chunks),
            chunks=chunks,
        )

    async def stg_finalize_chunks(
        self,
        doc_code: str,
        paths: list[str],
    ) -> FinalizeChunksResult:
        cmd = FinalizeChunksRequest(paths=paths)
        _session, result = await self._service.finalize_chunks(
            doc_code=doc_code, request=cmd, actor="AGENT"
        )
        return result

    async def stg_list_sessions(
        self, status: StagingStatus | None = None
    ) -> list[SessionSummary]:
        return await self._service.list_sessions(status=status)

    async def stg_reopen_session(
        self,
        doc_code: str,
        reason: str = "",
    ) -> SessionStatusResult:
        session = await self._service.reopen_session(
            doc_code=doc_code,
            actor="AGENT",
            reason=reason or "Agent reopened session for amendment / errata",
        )
        now = datetime.datetime.now(datetime.UTC)
        return SessionStatusResult(
            doc_code=session.doc_code,
            status=session.status.value,
            total_chunks=len(session.chunks),
            total_edges=len(session.edges),
            transitioned_at=now.isoformat(),
            message=f"Phiên làm việc cho văn bản '{doc_code}' đã được mở lại ở trạng thái AMENDMENT. Các công cụ stg_patch, stg_add_edges, stg_finalize_chunks đã sẵn sàng.",
        )

    async def stg_remove_edge(
        self,
        doc_code: str,
        source_path: str = "",
        target_path: str | None = None,
        relation_type: StatutoryRelationType | None = None,
        clear_all_targets: bool = False,
        edges: Sequence[RelationEdgeFilter | dict[str, object]] | None = None,
    ) -> MutationResult:
        parsed_filters: list[RelationEdgeFilter] = []
        if edges:
            for item in edges:
                if isinstance(item, RelationEdgeFilter):
                    parsed_filters.append(item)
                elif isinstance(item, dict):
                    parsed_filters.append(RelationEdgeFilter.model_validate(item))
            target_repr = f"{len(edges)} edge filter(s)"
        else:
            if not source_path:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message="Bắt buộc phải cung cấp 'source_path' hoặc danh sách 'edges' khi xóa cạnh quan hệ đồ thị.",
                    data={"doc_code": doc_code},
                )
            if not target_path and not clear_all_targets:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=(
                        f"Thao tác xóa cạnh từ '{source_path}' yêu cầu phải chỉ định 'target_path' "
                        "để xác định đúng cạnh cần xóa. Nếu thực sự muốn xóa toàn bộ mọi cạnh xuất phát từ nút này, "
                        "bắt buộc phải đặt 'clear_all_targets=True'."
                    ),
                    data={"doc_code": doc_code, "source_path": source_path},
                )
            parsed_filters.append(
                RelationEdgeFilter(
                    source_path=source_path,
                    target_path=target_path,
                    relation_type=relation_type,
                    clear_all_targets=clear_all_targets,
                )
            )
            target_repr = target_path or ("all targets" if clear_all_targets else "unknown")

        session, removed_count = await self._service.remove_edges(
            doc_code=doc_code, filters=parsed_filters, actor="AGENT"
        )
        return MutationResult(
            doc_code=doc_code,
            status="SUCCESS",
            affected_count=removed_count,
            total_count=len(session.edges),
            message=f"Removed {removed_count} edge(s) from '{source_path or 'batch'}' to '{target_repr}' ({relation_type or 'ANY'}).",
        )
