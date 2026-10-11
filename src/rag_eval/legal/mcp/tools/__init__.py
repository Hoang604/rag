from __future__ import annotations

import datetime
from collections.abc import Sequence

import asyncpg

from rag_eval.legal.mcp.tools.curation import (
    AddEdgesResult,
    EdgeKey,
    EdgeProposal,
    LegalGraphCurationTools,
    RemoveEdgesResult,
)
from rag_eval.legal.mcp.tools.embedder import (
    QueryEmbedder,
    SentenceTransformerQueryEmbedder,
)
from rag_eval.legal.mcp.tools.sensors import LegalRuntimeSensors
from rag_eval.legal.retrieval.reranker import LegalReranker
from rag_eval.legal.schemas.domain import (
    GraphDirection,
    GraphTraversalStep,
    StatutoryRelationType,
)
from rag_eval.legal.schemas.retrieval import (
    RERANK_POOL,
    GraphTraverseResult,
    HierarchicalNavigateResult,
    LegalSearchResult,
    RawTextResult,
    SearchHit,
    SearchResult,
)


class LegalMCPTools:
    """Facade composing the runtime sensors and the graph curation tools."""

    def __init__(self, sensors: LegalRuntimeSensors, curation: LegalGraphCurationTools) -> None:
        self._sensors = sensors
        self._curation = curation

    @classmethod
    def build(
        cls,
        pool: asyncpg.Pool | None = None,
        embedding_engine: QueryEmbedder | None = None,
        reranker: LegalReranker | None = None,
        rerank_by_default: bool = False,
    ) -> LegalMCPTools:
        return cls(
            sensors=LegalRuntimeSensors(
                pool=pool,
                embedding_engine=embedding_engine,
                reranker=reranker,
                rerank_by_default=rerank_by_default,
            ),
            curation=LegalGraphCurationTools(pool=pool),
        )

    @property
    def sensors(self) -> LegalRuntimeSensors:
        return self._sensors

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

    async def annotate_amendments(
        self, hits: list[SearchHit], on_date: datetime.date | None = None
    ) -> list[SearchHit]:
        return await self._sensors.annotate_amendments(hits, on_date)

    async def search(
        self,
        query: str,
        pattern: str,
        is_regex: bool = False,
        temporal_violation_date: str | None = None,
        doc_codes: list[str] | None = None,
        path_prefix: str | None = None,
        limit: int = 10,
        rerank: bool | None = None,
    ) -> LegalSearchResult:
        return await self._sensors.search(
            query=query,
            pattern=pattern,
            is_regex=is_regex,
            temporal_violation_date=temporal_violation_date,
            doc_codes=doc_codes,
            path_prefix=path_prefix,
            limit=limit,
            rerank=rerank,
        )

    async def hierarchical_navigate(self, path: str, limit: int = 100) -> HierarchicalNavigateResult:
        return await self._sensors.hierarchical_navigate(path=path, limit=limit)

    async def graph_traverse(
        self,
        source_path: str,
        direction: GraphDirection = "OUTGOING",
        max_depth: int = 1,
        filter_relations: list[StatutoryRelationType] | None = None,
        limit_per_link: int = 20,
    ) -> GraphTraverseResult:
        return await self._sensors.graph_traverse(
            source_path=source_path,
            direction=direction,
            max_depth=max_depth,
            filter_relations=filter_relations,
            limit_per_link=limit_per_link,
        )

    async def get_raw(self, doc_code: str, start_line: int, end_line: int) -> RawTextResult:
        return await self._sensors.get_raw(doc_code=doc_code, start_line=start_line, end_line=end_line)

    async def graph_add_edges(self, edges: Sequence[EdgeProposal], reason: str) -> AddEdgesResult:
        return await self._curation.graph_add_edges(edges=edges, reason=reason)

    async def graph_remove_edges(self, edges: Sequence[EdgeKey], reason: str) -> RemoveEdgesResult:
        return await self._curation.graph_remove_edges(edges=edges, reason=reason)


__all__ = [
    "RERANK_POOL",
    "AddEdgesResult",
    "EdgeKey",
    "EdgeProposal",
    "GraphDirection",
    "GraphTraversalStep",
    "GraphTraverseResult",
    "HierarchicalNavigateResult",
    "LegalGraphCurationTools",
    "LegalMCPTools",
    "LegalRuntimeSensors",
    "LegalSearchResult",
    "QueryEmbedder",
    "RawTextResult",
    "RemoveEdgesResult",
    "SearchHit",
    "SearchResult",
    "SentenceTransformerQueryEmbedder",
    "StatutoryRelationType",
]
