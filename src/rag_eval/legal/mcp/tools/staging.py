from __future__ import annotations

import datetime
from collections.abc import Sequence

import asyncpg

from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.ingestion.staging.service import StagingDomainService
from rag_eval.legal.schemas.domain import (
    RelationEdge,
    RelationEdgeFilter,
    StagingChunkDelta,
    StagingStatus,
)
from rag_eval.legal.schemas.retrieval import (
    RawTextResult,
)
from rag_eval.legal.schemas.staging import (
    BatchPatchRequest,
    BatchPatchResult,
    FinalizeChunksRequest,
    FinalizeChunksResult,
    MutationResult,
    PendingChunksResult,
    PreFlightValidationResponse,
    ReparentSubtreeRequest,
    ReparentSubtreeResult,
    SessionStatusResult,
    StagedChunkDetail,
    StgGrepRequest,
    StgGrepResponse,
    StgListSessionsResponse,
    StgSessionSummaryItem,
    UnfinalizeChunksResult,
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

    async def stg_get_chunk(self, doc_code: str, path: str) -> StagedChunkDetail:
        return await self._service.get_chunk(doc_code=doc_code, path=path)

    async def stg_get_raw(
        self, doc_code: str, start_line: int = 1, end_line: int = 100
    ) -> RawTextResult:
        return await self._service.get_raw_window(
            doc_code=doc_code, start_line=start_line, end_line=end_line
        )

    async def stg_grep(
        self,
        pattern: str,
        doc_code: str | None = None,
        heading_hint: str | None = None,
        body_hint: str | None = None,
        is_regex: bool = False,
        case_sensitive: bool = False,
        limit: int = 15,
    ) -> StgGrepResponse:
        req = StgGrepRequest(
            pattern=pattern,
            doc_code=doc_code,
            heading_hint=heading_hint,
            body_hint=body_hint,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            limit=limit,
        )
        return await self._service.grep_staging(req)

    async def stg_patch(
        self,
        doc_code: str,
        updated_chunks: Sequence[StagingChunkDelta | dict[str, object]] | None = None,
        removed_paths: list[str] | None = None,
        cascade_breadcrumbs: bool = True,
    ) -> BatchPatchResult:
        parsed_deltas: list[StagingChunkDelta] = []
        if updated_chunks:
            for item in updated_chunks:
                if isinstance(item, StagingChunkDelta):
                    parsed_deltas.append(item)
                elif isinstance(item, dict):
                    parsed_deltas.append(StagingChunkDelta.model_validate(item))
                else:
                    raise TypeError(
                        f"Unsupported delta item type '{type(item).__name__}': expected StagingChunkDelta or dict."
                    )

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

    async def stg_uncommit(
        self, doc_code: str, reason: str = ""
    ) -> SessionStatusResult:
        session = await self._service.uncommit_session(
            doc_code=doc_code, actor="AGENT", reason=reason
        )
        now = datetime.datetime.now(datetime.UTC)
        return SessionStatusResult(
            doc_code=session.doc_code,
            status=session.status.value,
            total_chunks=len(session.chunks),
            total_edges=len(session.edges),
            transitioned_at=now.isoformat(),
            message=f"Phiên làm việc cho văn bản '{doc_code}' đã được mở lại ở trạng thái {session.status.value}. Các công cụ chỉnh sửa stg_patch, stg_add_edges, stg_unfinalize_chunks đã sẵn sàng.",
        )

    async def stg_poll_pending(
        self,
        doc_code: str,
        limit: int = 10,
        path_prefix: str | None = None,
    ) -> PendingChunksResult:
        groups, progress_stats, has_more, returned_count = (
            await self._service.poll_pending_chunks(
                doc_code=doc_code, limit=limit, path_prefix=path_prefix
            )
        )
        return PendingChunksResult(
            doc_code=doc_code,
            progress=progress_stats,
            limit=min(max(1, limit), 10),
            has_more=has_more,
            returned_chunks=returned_count,
            groups=groups,
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

    async def stg_unfinalize_chunks(
        self,
        doc_code: str,
        paths: list[str],
    ) -> UnfinalizeChunksResult:
        _session, result = await self._service.unfinalize_chunks(
            doc_code=doc_code, paths=paths, actor="AGENT"
        )
        return result

    async def stg_list_sessions(
        self, status: StagingStatus | None = None
    ) -> StgListSessionsResponse:
        summaries = await self._service.list_sessions(status=status)
        items = [
            StgSessionSummaryItem(
                doc_code=s.doc_code,
                status=s.status,
                total_chunks=s.total_chunks,
                total_edges=s.total_edges,
                effective_date=s.effective_date,
                expiration_date=s.expiration_date,
                title=s.title,
            )
            for s in summaries
        ]
        return StgListSessionsResponse(total_sessions=len(items), sessions=items)

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

    async def stg_remove_edges(
        self,
        doc_code: str,
        edges: Sequence[RelationEdgeFilter | dict[str, object]],
    ) -> MutationResult:
        parsed_filters: list[RelationEdgeFilter] = []
        for item in edges:
            if isinstance(item, RelationEdgeFilter):
                parsed_filters.append(item)
            elif isinstance(item, dict):
                parsed_filters.append(RelationEdgeFilter.model_validate(item))

        session, removed_count = await self._service.remove_edges(
            doc_code=doc_code, filters=parsed_filters, actor="AGENT"
        )
        return MutationResult(
            doc_code=doc_code,
            status="SUCCESS",
            affected_count=removed_count,
            total_count=len(session.edges),
            message=f"Removed {removed_count} edge(s) matching {len(parsed_filters)} filter(s).",
        )


    async def stg_validate(self, doc_code: str) -> PreFlightValidationResponse:
        """Runs pre-flight integrity verification on the staging session."""
        return await self._service.validate_session(doc_code=doc_code)

