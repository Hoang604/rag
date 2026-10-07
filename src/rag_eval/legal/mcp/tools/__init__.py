from __future__ import annotations

import datetime
from collections.abc import Sequence

import asyncpg

from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.ingestion.staging.service import StagingDomainService
from rag_eval.legal.mcp.tools.embedder import (
    QueryEmbedder,
    SentenceTransformerQueryEmbedder,
)
from rag_eval.legal.mcp.tools.sensors import LegalRuntimeSensors
from rag_eval.legal.mcp.tools.staging import LegalStagingTools
from rag_eval.legal.retrieval.reranker import LegalReranker
from rag_eval.legal.schemas.domain import (
    HIERARCHICAL_DIRECTION_DESCRIPTION,
    HIERARCHICAL_DIRECTION_DOCS,
    ChunkDelta,
    FinalizationState,
    GraphDirection,
    GraphTraversalStep,
    HierarchicalDirection,
    RelationEdge,
    RelationEdgeFilter,
    StagingChunkDelta,
    StagingStatus,
    StatutoryRelationType,
    TreeNode,
    UnresolvedReference,
)
from rag_eval.legal.schemas.retrieval import (
    RERANK_POOL,
    GraphTraverseResult,
    GrepResult,
    HierarchicalNavigateResult,
    RawTextResult,
    SearchHit,
    SearchResult,
)
from rag_eval.legal.schemas.staging import (
    BatchPatchResult,
    ChunkFinalizeStatus,
    FinalizeChunksResult,
    GrepHit,
    MutationResult,
    PendingChunkGroup,
    PendingChunkLeaf,
    PendingChunksResult,
    PreFlightValidationResponse,
    ReparentSubtreeResult,
    SessionStatusResult,
    StagedChunkDetail,
    StgGrepRequest,
    StgGrepResponse,
    StgListSessionsResponse,
    StgSessionSummaryItem,
    UnfinalizeChunksRequest,
    UnfinalizeChunksResult,
)


class LegalMCPTools:
    """Canonical 19-tool facade composing runtime sensors and staging operations via strict DI."""

    def __init__(
        self,
        sensors: LegalRuntimeSensors,
        staging: LegalStagingTools,
    ) -> None:
        self._sensors = sensors
        self._staging = staging

    @classmethod
    def build(
        cls,
        pool: asyncpg.Pool | None = None,
        staging_manager: StagingManager | None = None,
        embedding_engine: QueryEmbedder | None = None,
        reranker: LegalReranker | None = None,
        rerank_by_default: bool = False,
    ) -> LegalMCPTools:
        manager = staging_manager or StagingManager()
        service = StagingDomainService(staging_manager=manager, pool=pool)
        return cls(
            sensors=LegalRuntimeSensors(
                pool=pool,
                embedding_engine=embedding_engine,
                reranker=reranker,
                rerank_by_default=rerank_by_default,
            ),
            staging=LegalStagingTools(service=service),
        )

    @property
    def sensors(self) -> LegalRuntimeSensors:
        return self._sensors

    @property
    def staging(self) -> LegalStagingTools:
        return self._staging

    async def build_dynamic_corpus_manifest(
        self, as_of_date: datetime.date | None = None
    ) -> str:
        return await self._sensors.build_dynamic_corpus_manifest(as_of_date=as_of_date)

    async def hybrid_search(
        self,
        query: str,
        temporal_violation_date: str | None = None,
        limit: int = 10,
        rerank: bool | None = None,
        rerank_pool: int = RERANK_POOL,
        doc_codes: list[str] | None = None,
        path_prefix: str | None = None,
    ) -> SearchResult:
        return await self._sensors.hybrid_search(
            query=query,
            temporal_violation_date=temporal_violation_date,
            limit=limit,
            rerank=rerank,
            rerank_pool=rerank_pool,
            doc_codes=doc_codes,
            path_prefix=path_prefix,
        )

    async def expand_windows(
        self, hits: list[SearchHit], max_chars: int = 5_000
    ) -> list[SearchHit]:
        return await self._sensors.expand_windows(hits=hits, max_chars=max_chars)

    async def verbatim_grep(
        self,
        pattern: str,
        doc_codes: list[str] | None = None,
        path_prefix: str | None = None,
        is_regex: bool = False,
        case_sensitive: bool = False,
        temporal_violation_date: str | None = None,
        limit: int = 20,
    ) -> GrepResult:
        return await self._sensors.verbatim_grep(
            pattern=pattern,
            doc_codes=doc_codes,
            path_prefix=path_prefix,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            temporal_violation_date=temporal_violation_date,
            limit=limit,
        )

    async def hierarchical_navigate(
        self,
        path: str,
        direction: HierarchicalDirection = HierarchicalDirection.FULL_ARTICLE,
    ) -> HierarchicalNavigateResult:
        return await self._sensors.hierarchical_navigate(
            path=path, direction=direction
        )

    async def graph_traverse(
        self,
        source_path: str,
        direction: GraphDirection = "OUTGOING",
        max_depth: int = 2,
        filter_relations: list[StatutoryRelationType] | None = None,
    ) -> GraphTraverseResult:
        return await self._sensors.graph_traverse(
            source_path=source_path,
            direction=direction,
            max_depth=max_depth,
            filter_relations=filter_relations,
        )


    async def stg_get_chunk(self, doc_code: str, path: str) -> StagedChunkDetail:
        return await self._staging.stg_get_chunk(doc_code=doc_code, path=path)

    async def stg_get_raw(
        self, doc_code: str, start_line: int = 1, end_line: int = 100
    ) -> RawTextResult:
        return await self._staging.stg_get_raw(
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
        return await self._staging.stg_grep(
            pattern=pattern,
            doc_code=doc_code,
            heading_hint=heading_hint,
            body_hint=body_hint,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            limit=limit,
        )

    async def stg_patch(
        self,
        doc_code: str,
        updated_chunks: Sequence[StagingChunkDelta | dict[str, object]] | None = None,
        removed_paths: list[str] | None = None,
        cascade_breadcrumbs: bool = True,
    ) -> BatchPatchResult:
        return await self._staging.stg_patch(
            doc_code=doc_code,
            updated_chunks=updated_chunks,
            removed_paths=removed_paths,
            cascade_breadcrumbs=cascade_breadcrumbs,
        )

    async def stg_add_edges(
        self,
        doc_code: str,
        edges: Sequence[RelationEdge | dict[str, object]],
    ) -> MutationResult:
        return await self._staging.stg_add_edges(
            doc_code=doc_code,
            edges=edges,
        )

    async def stg_reparent(
        self,
        doc_code: str,
        old_path_prefix: str,
        new_path_prefix: str,
        dry_run: bool = False,
    ) -> ReparentSubtreeResult:
        return await self._staging.stg_reparent(
            doc_code=doc_code,
            old_path_prefix=old_path_prefix,
            new_path_prefix=new_path_prefix,
            dry_run=dry_run,
        )

    async def stg_poll_pending(
        self,
        doc_code: str,
        limit: int = 10,
        path_prefix: str | None = None,
    ) -> PendingChunksResult:
        return await self._staging.stg_poll_pending(
            doc_code=doc_code,
            limit=limit,
            path_prefix=path_prefix,
        )

    async def stg_finalize_chunks(
        self,
        doc_code: str,
        paths: list[str],
    ) -> FinalizeChunksResult:
        return await self._staging.stg_finalize_chunks(
            doc_code=doc_code,
            paths=paths,
        )

    async def stg_unfinalize_chunks(
        self,
        doc_code: str,
        paths: list[str],
    ) -> UnfinalizeChunksResult:
        return await self._staging.stg_unfinalize_chunks(
            doc_code=doc_code,
            paths=paths,
        )

    async def stg_commit(self, doc_code: str) -> SessionStatusResult:
        return await self._staging.stg_commit(doc_code=doc_code)

    async def stg_list_sessions(
        self, status: StagingStatus | None = None
    ) -> StgListSessionsResponse:
        return await self._staging.stg_list_sessions(status=status)

    async def stg_reopen_session(
        self,
        doc_code: str,
        reason: str = "",
    ) -> SessionStatusResult:
        return await self._staging.stg_reopen_session(doc_code=doc_code, reason=reason)

    async def stg_remove_edges(
        self,
        doc_code: str,
        edges: Sequence[RelationEdgeFilter | dict[str, object]],
    ) -> MutationResult:
        return await self._staging.stg_remove_edges(
            doc_code=doc_code,
            edges=edges,
        )


    async def stg_validate(self, doc_code: str) -> PreFlightValidationResponse:
        return await self._staging.stg_validate(doc_code=doc_code)



__all__ = [
    "HIERARCHICAL_DIRECTION_DESCRIPTION",
    "HIERARCHICAL_DIRECTION_DOCS",
    "RERANK_POOL",
    "BatchPatchResult",
    "ChunkDelta",
    "ChunkFinalizeStatus",
    "FinalizationState",
    "FinalizeChunksResult",
    "GraphDirection",
    "GraphTraversalStep",
    "GraphTraverseResult",
    "GrepHit",
    "GrepResult",
    "HierarchicalDirection",
    "HierarchicalNavigateResult",
    "LegalMCPTools",
    "LegalRuntimeSensors",
    "LegalStagingTools",
    "MutationResult",
    "PendingChunkGroup",
    "PendingChunkLeaf",
    "PendingChunksResult",
    "PreFlightValidationResponse",
    "QueryEmbedder",
    "RawTextResult",
    "ReparentSubtreeResult",
    "SearchHit",
    "SearchResult",
    "SentenceTransformerQueryEmbedder",
    "SessionStatusResult",
    "StagedChunkDetail",
    "StagingChunkDelta",
    "StagingStatus",
    "StatutoryRelationType",
    "StgGrepRequest",
    "StgGrepResponse",
    "StgListSessionsResponse",
    "StgSessionSummaryItem",
    "TreeNode",
    "UnfinalizeChunksRequest",
    "UnfinalizeChunksResult",
    "UnresolvedReference",
]
