"""Staging buffer tools executing candidates validation, patching, and commit gate."""

from __future__ import annotations

import datetime
from typing import Any

from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.ingestion.staging.models import (
    ChunkReviewStatus,
    StagingStatus,
    StgReparentResult,
)
from rag_eval.legal.mcp.tools.schemas import (
    ChunkProgressStats,
    StgAddEdgesResult,
    StgCommitResult,
    StgFinalizeResult,
    StgGetChunkResult,
    StgGetRawResult,
    StgGrepResult,
    StgListSessionsResult,
    StgPatchResult,
    StgPollPendingResult,
    StgPreviewHit,
    StgPreviewResult,
)
from rag_eval.legal.schemas import (
    E_AST_GROUNDING_VALIDATION,
    E_INVALID_DOCUMENT_HIERARCHY,
    LegalDomainError,
    validate_ltree_path,
)


class LegalStagingTools:
    """Encapsulates local staging session operations on disk (.cache/stg). Zero database imports."""

    def __init__(self, staging_manager: StagingManager | None = None) -> None:
        self._staging = staging_manager or StagingManager()

    async def stg_preview(
        self,
        doc_code: str,
        path_prefix: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StgPreviewResult:
        session = self._staging.load_session(doc_code)
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
                metadata=c.metadata,
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
        session = self._staging.load_session(doc_code)
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
        session = self._staging.load_session(doc_code)
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
        search_in: str = "ALL",
        limit: int = 50,
    ) -> StgGrepResult:
        session = self._staging.load_session(doc_code)
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
        updated_chunks: list[dict[str, Any]] | None = None,
        removed_paths: list[str] | None = None,
        cascade_breadcrumbs: bool = True,
    ) -> StgPatchResult:
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
        return StgPatchResult(
            doc_code=doc_code,
            status="SUCCESS",
            updated_count=int(last_diff.get("updated_count", len(updated_chunks or []))),
            cascaded_count=int(last_diff.get("cascaded_count", 0)),
            removed_count=int(last_diff.get("removed_count", len(removed_paths or []))),
            total_chunks_after_patch=len(session.chunks),
            fields_modified=list(last_diff.get("fields_modified", [])),
        )

    async def stg_add_edges(
        self,
        doc_code: str,
        edges: list[dict[str, Any]],
    ) -> StgAddEdgesResult:
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
        _session, result = self._staging.reparent_node(
            doc_code=doc_code,
            old_path_prefix=old_path_prefix,
            new_path_prefix=new_path_prefix,
            dry_run=dry_run,
            actor="AGENT",
        )
        return result

    async def stg_commit(self, doc_code: str) -> StgCommitResult:
        session = self._staging.load_session(doc_code)

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
        chunks, stats = self._staging.poll_pending_chunks(
            doc_code=doc_code, limit=limit, path_prefix=path_prefix
        )
        return StgPollPendingResult(
            doc_code=doc_code,
            progress=ChunkProgressStats(**stats),
            limit=limit,
            has_more=stats["pending_count"] > len(chunks),
            chunks=chunks,
        )

    async def stg_finalize_chunks(
        self,
        doc_code: str,
        paths: list[str],
    ) -> StgFinalizeResult:
        session, finalized_count = self._staging.finalize_chunks(
            doc_code=doc_code, paths=paths, actor="AGENT"
        )
        pending_remaining = sum(
            1 for c in session.chunks if c.review_status == ChunkReviewStatus.PENDING
        )
        return StgFinalizeResult(
            doc_code=doc_code,
            status="SUCCESS",
            finalized_count=finalized_count,
            pending_remaining=pending_remaining,
            paths=paths,
        )

    async def stg_list_sessions(
        self, status: str | None = None
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
