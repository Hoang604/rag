"""Vietnamese Traffic Law Model Context Protocol (MCP) Tools.

Exposes pure-DI LegalMCPTools composed of LegalRuntimeSensors and LegalStagingTools,
along with embedders and all canonical output schemas.
"""

from __future__ import annotations

import datetime
from typing import Any

import asyncpg

from rag_eval.legal.ingestion.staging import StgReparentResult
from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.mcp.tools.embedder import (
    QueryEmbedder,
    SentenceTransformerQueryEmbedder,
)
from rag_eval.legal.mcp.tools.schemas import (
    RERANK_POOL,
    AddMetadataResult,
    ChunkBacklogResult,
    CorpusValidateResult,
    DanglingBacklogItem,
    GraphEdgeWriteResult,
    GraphTraversalStep,
    GraphTraverseResult,
    HierarchicalNavigateResult,
    HierarchyNode,
    HybridSearchResult,
    SearchHit,
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
    VerbatimGrepResult,
    extract_metadata_dict,
)
from rag_eval.legal.mcp.tools.sensors import LegalRuntimeSensors
from rag_eval.legal.mcp.tools.staging import LegalStagingTools
from rag_eval.legal.retrieval.annotations import ANSWERS
from rag_eval.legal.retrieval.reranker import LegalReranker


class LegalMCPTools:
    """Canonical 16-tool facade composing runtime sensors and staging operations via strict DI."""

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
        use_relatedness: bool = False,
    ) -> LegalMCPTools:
        """Assembles the facade from loose parts, for callers outside the server.

        The constructor stays pure DI. Scripts, the web app and the CLI hold a
        pool and an embedder rather than a sensor object, and each writing its
        own two-line assembly is how the defaults drift apart.
        """
        manager = staging_manager or StagingManager()
        return cls(
            sensors=LegalRuntimeSensors(
                pool=pool,
                embedding_engine=embedding_engine,
                staging_manager=manager,
                reranker=reranker,
                rerank_by_default=rerank_by_default,
                use_relatedness=use_relatedness,
            ),
            staging=LegalStagingTools(staging_manager=manager),
        )

    @property
    def sensors(self) -> LegalRuntimeSensors:
        return self._sensors

    @property
    def staging(self) -> LegalStagingTools:
        return self._staging

    # Sensor delegations
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
    ) -> HybridSearchResult:
        return await self._sensors.hybrid_search(
            query=query,
            temporal_violation_date=temporal_violation_date,
            limit=limit,
            rerank=rerank,
            rerank_pool=rerank_pool,
            doc_codes=doc_codes,
        )

    async def add_metadata(
        self,
        chunk_id: str,
        query: str,
        relation: str = ANSWERS,
        note: str | None = None,
        session_id: str | None = None,
    ) -> AddMetadataResult:
        return await self._sensors.add_metadata(
            chunk_id=chunk_id,
            query=query,
            relation=relation,
            note=note,
            session_id=session_id,
        )

    async def expand_windows(
        self, hits: list[SearchHit], max_chars: int = 5_000
    ) -> list[SearchHit]:
        return await self._sensors.expand_windows(hits=hits, max_chars=max_chars)

    async def verbatim_grep(
        self,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        temporal_violation_date: str | None = None,
        limit: int = 20,
    ) -> VerbatimGrepResult:
        return await self._sensors.verbatim_grep(
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            temporal_violation_date=temporal_violation_date,
            limit=limit,
        )

    async def hierarchical_navigate(
        self,
        path: str | None = None,
        chunk_id: str | None = None,
        direction: str = "FULL_ARTICLE",
    ) -> HierarchicalNavigateResult:
        return await self._sensors.hierarchical_navigate(
            path=path, chunk_id=chunk_id, direction=direction
        )

    async def graph_traverse(
        self,
        source_chunk_id: str,
        direction: str = "OUTGOING",
        max_depth: int = 2,
    ) -> GraphTraverseResult:
        return await self._sensors.graph_traverse(
            source_chunk_id=source_chunk_id,
            direction=direction,
            max_depth=max_depth,
        )

    async def graph_edge_write(
        self,
        source_chunk_id: str,
        relation_type: str,
        target_chunk_id: str | None = None,
        target_external_ref: str | None = None,
        citation_text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GraphEdgeWriteResult:
        return await self._sensors.graph_edge_write(
            source_chunk_id=source_chunk_id,
            relation_type=relation_type,
            target_chunk_id=target_chunk_id,
            target_external_ref=target_external_ref,
            citation_text=citation_text,
            metadata=metadata,
        )

    async def corpus_validate(self) -> CorpusValidateResult:
        return await self._sensors.corpus_validate()

    async def chunk_backlog_poll(
        self,
        finalization_state: str | None = None,
        doc_code: str | None = None,
        limit: int = 50,
    ) -> ChunkBacklogResult:
        return await self._sensors.chunk_backlog_poll(
            finalization_state=finalization_state,
            doc_code=doc_code,
            limit=limit,
        )


    # Staging delegations
    async def stg_preview(
        self,
        doc_code: str,
        path_prefix: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StgPreviewResult:
        return await self._staging.stg_preview(
            doc_code=doc_code,
            path_prefix=path_prefix,
            limit=limit,
            offset=offset,
        )

    async def stg_get_chunk(self, doc_code: str, path: str) -> StgGetChunkResult:
        return await self._staging.stg_get_chunk(doc_code=doc_code, path=path)

    async def stg_get_raw(
        self, doc_code: str, start_line: int = 1, end_line: int = 100
    ) -> StgGetRawResult:
        return await self._staging.stg_get_raw(
            doc_code=doc_code, start_line=start_line, end_line=end_line
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
        return await self._staging.stg_grep(
            doc_code=doc_code,
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            search_in=search_in,
            limit=limit,
        )

    async def stg_patch(
        self,
        doc_code: str,
        updated_chunks: list[dict[str, Any]] | None = None,
        removed_paths: list[str] | None = None,
        cascade_breadcrumbs: bool = True,
    ) -> StgPatchResult:
        return await self._staging.stg_patch(
            doc_code=doc_code,
            updated_chunks=updated_chunks,
            removed_paths=removed_paths,
            cascade_breadcrumbs=cascade_breadcrumbs,
        )

    async def stg_add_edges(
        self,
        doc_code: str,
        edges: list[dict[str, Any]],
    ) -> StgAddEdgesResult:
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
    ) -> StgReparentResult:
        return await self._staging.stg_reparent(
            doc_code=doc_code,
            old_path_prefix=old_path_prefix,
            new_path_prefix=new_path_prefix,
            dry_run=dry_run,
        )

    async def stg_poll_pending_chunks(
        self,
        doc_code: str,
        limit: int = 10,
        path_prefix: str | None = None,
    ) -> StgPollPendingResult:
        return await self._staging.stg_poll_pending_chunks(
            doc_code=doc_code,
            limit=limit,
            path_prefix=path_prefix,
        )

    async def stg_finalize_chunks(
        self,
        doc_code: str,
        paths: list[str],
    ) -> StgFinalizeResult:
        return await self._staging.stg_finalize_chunks(
            doc_code=doc_code,
            paths=paths,
        )

    async def stg_commit(self, doc_code: str) -> StgCommitResult:
        return await self._staging.stg_commit(doc_code=doc_code)

    async def stg_list_sessions(
        self, status: str | None = None
    ) -> StgListSessionsResult:
        return await self._staging.stg_list_sessions(status=status)


__all__ = [
    "ANSWERS",
    "RERANK_POOL",
    "AddMetadataResult",
    "ChunkBacklogResult",
    "CorpusValidateResult",
    "DanglingBacklogItem",
    "GraphEdgeWriteResult",
    "GraphTraversalStep",
    "GraphTraverseResult",
    "HierarchicalNavigateResult",
    "HierarchyNode",
    "HybridSearchResult",
    "LegalMCPTools",
    "LegalRuntimeSensors",
    "LegalStagingTools",
    "QueryEmbedder",
    "SearchHit",
    "SentenceTransformerQueryEmbedder",
    "StgAddEdgesResult",
    "StgCommitResult",
    "StgFinalizeResult",
    "StgGetChunkResult",
    "StgGetRawResult",
    "StgGrepResult",
    "StgListSessionsResult",
    "StgPatchResult",
    "StgPollPendingResult",
    "StgPreviewHit",
    "StgPreviewResult",
    "StgReparentResult",
    "VerbatimGrepResult",
    "extract_metadata_dict",
]
