"""Canonical MCP Tool Implementations for the Ultra-Lean 3-Table Agent-First Legal Architecture.

Provides 10 atomic sensor and staging tools executing queries and gated promotion
directly over PostgreSQL (documents, chunks, graph_edges) with zero if-else bias:
1. hybrid_search (Dense HNSW + Sparse TSVector RRF Fusion)
2. verbatim_grep (Trigram GIN Exact & Regex Search)
3. hierarchical_navigate (PostgreSQL ltree tree navigation)
4. graph_traverse (Recursive CTE Knowledge Graph Traversal)
5. graph_edge_write (Directed Relation Edge Persistence)
6. corpus_validate (Integrity & Orphan Verification)
7. stg_preview (Preview staged chunks in .cache/stg)
8. stg_patch (Surgical edits to candidate chunks in staging)
9. stg_add_edges (Attach relational edges in staging)
10. stg_commit (Single-Gateway Promotion from staging to PostgreSQL 3 tables)
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import Any

import asyncpg
from pydantic import BaseModel, ConfigDict, Field

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingEdge,
    StagingManager,
)
from rag_eval.legal.schemas import (
    E_AST_GROUNDING_VALIDATION,
    E_INVALID_DOCUMENT_HIERARCHY,
    E_STORAGE_CONNECTION,
    CanonicalFullyQualifiedChunk,
    DocumentRecord,
    GraphEdgeRecord,
    LegalDomainError,
    validate_ltree_path,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Tool Output Models
# ------------------------------------------------------------------------------
class SearchHit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    doc_code: str
    doc_title: str
    path: str
    verbatim_text: str
    contextualized_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    effective_date: str
    expiration_date: str | None = None
    score: float


class HybridSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_hits: int
    hits: list[SearchHit]


class VerbatimGrepResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pattern: str
    is_regex: bool
    total_matches: int
    matches: list[SearchHit]


class HierarchyNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    path: str
    doc_code: str
    verbatim_text: str
    contextualized_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class HierarchicalNavigateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    anchor_path: str
    direction: str
    total_nodes: int
    nodes: list[HierarchyNode]


class GraphTraversalStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    edge_id: str
    source_chunk_id: str
    target_chunk_id: str | None
    target_external_ref: str | None
    relation_type: str
    citation_text: str | None
    depth: int
    target_path: str | None = None
    target_text: str | None = None


class GraphTraverseResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_chunk_id: str
    total_paths: int
    paths: list[GraphTraversalStep]


class GraphEdgeWriteResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    edge_id: str
    status: str
    relation_type: str


class CorpusValidateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    total_documents: int
    total_chunks: int
    total_edges: int
    orphan_chunks_count: int = 0
    issues: list[str] = Field(default_factory=list)


# Staging Output Models
class StgPreviewHit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    lead_sentence: str
    preview_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StgPreviewResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    title: str
    total_chunks: int
    total_edges: int
    chunks: list[StgPreviewHit]


class StgPatchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    status: str
    total_chunks_after_patch: int


class StgAddEdgesResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    status: str
    total_edges: int


class StgCommitResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    document_id: str
    chunks_committed: int
    edges_committed: int
    status: str


# ------------------------------------------------------------------------------
# LegalMCPTools Class
# ------------------------------------------------------------------------------
class LegalMCPTools:
    """Atomic Sensor & Staging MCP Tools for LLM Agent orchestration over PostgreSQL."""

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        staging_manager: StagingManager | None = None,
    ) -> None:
        self._pool = pool
        self._staging = staging_manager or StagingManager()

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool
        try:
            self._pool = await get_db_pool()
            return self._pool
        except Exception as exc:
            raise LegalDomainError(
                error_code=E_STORAGE_CONNECTION,
                message=f"Database storage connection failed: {exc}",
            ) from exc

    # 1. HYBRID SEARCH
    async def hybrid_search(
        self,
        query: str,
        dense_vector: list[float] | None = None,
        temporal_violation_date: str | None = None,
        limit: int = 10,
    ) -> HybridSearchResult:
        """Executes Reciprocal Rank Fusion (RRF) search over chunks and documents."""
        pool = await self._get_pool()
        t_date = (
            datetime.date.fromisoformat(temporal_violation_date)
            if temporal_violation_date
            else datetime.datetime.now(datetime.UTC).date()
        )
        vec_str = (
            f"[{','.join(str(x) for x in dense_vector)}]"
            if dense_vector is not None
            else None
        )

        sql = """
        SELECT 
            chunk_id, doc_code, doc_title, path, verbatim_text,
            contextualized_text, metadata, effective_date, expiration_date, rrf_score
        FROM hybrid_search($1, $2::vector, $3::date, $4::int, 60);
        """
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, query, vec_str, t_date, limit)
                hits = [
                    SearchHit(
                        chunk_id=str(r["chunk_id"]),
                        doc_code=str(r["doc_code"]),
                        doc_title=str(r["doc_title"]),
                        path=str(r["path"]),
                        verbatim_text=str(r["verbatim_text"]),
                        contextualized_text=str(r["contextualized_text"]),
                        metadata=json.loads(r["metadata"])
                        if isinstance(r["metadata"], str)
                        else (r["metadata"] or {}),
                        effective_date=str(r["effective_date"]),
                        expiration_date=str(r["expiration_date"])
                        if r["expiration_date"]
                        else None,
                        score=float(r["rrf_score"]),
                    )
                    for r in rows
                ]
                return HybridSearchResult(total_hits=len(hits), hits=hits)
        except Exception as exc:
            logger.error("hybrid_search failed: %s", exc)
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=f"Hybrid search execution error: {exc}",
            ) from exc

    # 2. VERBATIM GREP
    async def verbatim_grep(
        self,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        temporal_violation_date: str | None = None,
        limit: int = 20,
    ) -> VerbatimGrepResult:
        """Executes exact substring or regex search accelerated by Trigram GIN index."""
        pool = await self._get_pool()
        t_date = (
            datetime.date.fromisoformat(temporal_violation_date)
            if temporal_violation_date
            else datetime.datetime.now(datetime.UTC).date()
        )

        sql = """
        SELECT 
            chunk_id, doc_code, doc_title, path, verbatim_text,
            contextualized_text, metadata, effective_date, expiration_date, similarity_score
        FROM verbatim_grep($1, NULL, $2::boolean, $3::boolean, $4::date, $5::int);
        """
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    sql, pattern, is_regex, case_sensitive, t_date, limit
                )
                matches = [
                    SearchHit(
                        chunk_id=str(r["chunk_id"]),
                        doc_code=str(r["doc_code"]),
                        doc_title=str(r["doc_title"]),
                        path=str(r["path"]),
                        verbatim_text=str(r["verbatim_text"]),
                        contextualized_text=str(r["contextualized_text"]),
                        metadata=json.loads(r["metadata"])
                        if isinstance(r["metadata"], str)
                        else (r["metadata"] or {}),
                        effective_date=str(r["effective_date"]),
                        expiration_date=str(r["expiration_date"])
                        if r["expiration_date"]
                        else None,
                        score=float(r["similarity_score"]),
                    )
                    for r in rows
                ]
                return VerbatimGrepResult(
                    pattern=pattern,
                    is_regex=is_regex,
                    total_matches=len(matches),
                    matches=matches,
                )
        except Exception as exc:
            logger.error("verbatim_grep failed: %s", exc)
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=f"Verbatim grep execution error: {exc}",
            ) from exc

    # 3. HIERARCHICAL NAVIGATE
    async def hierarchical_navigate(
        self,
        path: str | None = None,
        chunk_id: str | None = None,
        direction: str = "CHILDREN",
    ) -> HierarchicalNavigateResult:
        """Navigates statutory hierarchy using PostgreSQL ltree operators (<@, @>, subpath)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            target_path = path
            if not target_path and chunk_id:
                target_path = await conn.fetchval(
                    "SELECT path::text FROM chunks WHERE id = $1::uuid;",
                    uuid.UUID(chunk_id),
                )
            if not target_path:
                raise LegalDomainError(
                    error_code=E_INVALID_DOCUMENT_HIERARCHY,
                    message="Target path or chunk_id required for hierarchical navigation",
                )

            clean_path = validate_ltree_path(target_path)
            dir_upper = direction.upper()

            if dir_upper == "CHILDREN":
                sql = """
                SELECT c.id, c.path::text, d.doc_code, c.verbatim_text, c.contextualized_text, c.metadata
                FROM chunks c JOIN documents d ON c.document_id = d.id
                WHERE c.path <@ $1::ltree AND c.path != $1::ltree
                ORDER BY c.path ASC LIMIT 50;
                """
            elif dir_upper == "PARENT_CHAIN":
                sql = """
                SELECT c.id, c.path::text, d.doc_code, c.verbatim_text, c.contextualized_text, c.metadata
                FROM chunks c JOIN documents d ON c.document_id = d.id
                WHERE c.path @> $1::ltree
                ORDER BY nlevel(c.path) ASC;
                """
            elif dir_upper == "SIBLINGS":
                sql = """
                SELECT c.id, c.path::text, d.doc_code, c.verbatim_text, c.contextualized_text, c.metadata
                FROM chunks c JOIN documents d ON c.document_id = d.id
                WHERE subpath(c.path, 0, nlevel($1::ltree) - 1) = subpath($1::ltree, 0, nlevel($1::ltree) - 1)
                  AND nlevel(c.path) = nlevel($1::ltree)
                ORDER BY c.path ASC;
                """
            else:  # FULL_ARTICLE
                sql = """
                SELECT c.id, c.path::text, d.doc_code, c.verbatim_text, c.contextualized_text, c.metadata
                FROM chunks c JOIN documents d ON c.document_id = d.id
                WHERE c.path <@ subpath($1::ltree, 0, LEAST(3, nlevel($1::ltree)))
                ORDER BY c.path ASC LIMIT 50;
                """

            rows = await conn.fetch(sql, clean_path)
            nodes = [
                HierarchyNode(
                    chunk_id=str(r["id"]),
                    path=str(r["path"]),
                    doc_code=str(r["doc_code"]),
                    verbatim_text=str(r["verbatim_text"]),
                    contextualized_text=str(r["contextualized_text"]),
                    metadata=json.loads(r["metadata"])
                    if isinstance(r["metadata"], str)
                    else (r["metadata"] or {}),
                )
                for r in rows
            ]
            return HierarchicalNavigateResult(
                anchor_path=clean_path,
                direction=dir_upper,
                total_nodes=len(nodes),
                nodes=nodes,
            )

    # 4. GRAPH TRAVERSE
    async def graph_traverse(
        self,
        source_chunk_id: str,
        direction: str = "OUTGOING",
        max_depth: int = 2,
    ) -> GraphTraverseResult:
        """Traverses the legal knowledge graph recursively across cross-statutory edges."""
        pool = await self._get_pool()
        sql = """
        WITH RECURSIVE traverse AS (
            SELECT 
                e.id AS edge_id,
                e.source_chunk_id,
                e.target_chunk_id,
                e.target_external_ref,
                e.relation_type,
                e.citation_text,
                1 AS depth,
                c.path::text AS target_path,
                c.verbatim_text AS target_text
            FROM graph_edges e
            LEFT JOIN chunks c ON e.target_chunk_id = c.id
            WHERE e.source_chunk_id = $1::uuid

            UNION ALL

            SELECT 
                e2.id AS edge_id,
                e2.source_chunk_id,
                e2.target_chunk_id,
                e2.target_external_ref,
                e2.relation_type,
                e2.citation_text,
                t.depth + 1 AS depth,
                c2.path::text AS target_path,
                c2.verbatim_text AS target_text
            FROM graph_edges e2
            JOIN traverse t ON e2.source_chunk_id = t.target_chunk_id
            LEFT JOIN chunks c2 ON e2.target_chunk_id = c2.id
            WHERE t.depth < $2 AND t.target_chunk_id IS NOT NULL
        )
        SELECT * FROM traverse LIMIT 50;
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, uuid.UUID(source_chunk_id), max_depth)
            paths = [
                GraphTraversalStep(
                    edge_id=str(r["edge_id"]),
                    source_chunk_id=str(r["source_chunk_id"]),
                    target_chunk_id=str(r["target_chunk_id"])
                    if r["target_chunk_id"]
                    else None,
                    target_external_ref=r["target_external_ref"],
                    relation_type=str(r["relation_type"]),
                    citation_text=r["citation_text"],
                    depth=int(r["depth"]),
                    target_path=r["target_path"],
                    target_text=r["target_text"],
                )
                for r in rows
            ]
            return GraphTraverseResult(
                source_chunk_id=source_chunk_id,
                total_paths=len(paths),
                paths=paths,
            )

    # 5. GRAPH EDGE WRITE
    async def graph_edge_write(
        self,
        source_chunk_id: str,
        relation_type: str,
        target_chunk_id: str | None = None,
        target_external_ref: str | None = None,
        citation_text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GraphEdgeWriteResult:
        """Persists a new directed relationship edge into 'graph_edges'."""
        pool = await self._get_pool()
        edge_id = uuid.uuid4()
        tgt_id = uuid.UUID(target_chunk_id) if target_chunk_id else None

        sql = """
        INSERT INTO graph_edges (
            id, source_chunk_id, target_chunk_id, target_external_ref,
            relation_type, citation_text, metadata
        ) VALUES (
            $1, $2::uuid, $3::uuid, $4, $5, $6, $7::jsonb
        )
        ON CONFLICT (source_chunk_id, target_chunk_id, relation_type) DO UPDATE SET
            target_external_ref = EXCLUDED.target_external_ref,
            citation_text = EXCLUDED.citation_text,
            metadata = EXCLUDED.metadata
        RETURNING id;
        """
        async with pool.acquire() as conn:
            res_id = await conn.fetchval(
                sql,
                edge_id,
                uuid.UUID(source_chunk_id),
                tgt_id,
                target_external_ref,
                relation_type,
                citation_text,
                json.dumps(metadata or {}),
            )
            return GraphEdgeWriteResult(
                edge_id=str(res_id),
                status="SUCCESS",
                relation_type=relation_type,
            )

    # 6. CORPUS VALIDATE
    async def corpus_validate(self) -> CorpusValidateResult:
        """Validates the structural integrity and counts of documents, chunks, and graph edges."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            doc_cnt = await conn.fetchval("SELECT count(*) FROM documents;")
            chunk_cnt = await conn.fetchval("SELECT count(*) FROM chunks;")
            edge_cnt = await conn.fetchval("SELECT count(*) FROM graph_edges;")
            orphan_cnt = await conn.fetchval(
                """
                SELECT count(*) FROM chunks c 
                WHERE NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = c.document_id);
                """
            )
            issues: list[str] = []
            if orphan_cnt > 0:
                issues.append(f"Detected {orphan_cnt} orphan chunks without valid document FK")

            status = "HEALTHY" if not issues else "INTEGRITY_WARNING"
            return CorpusValidateResult(
                status=status,
                total_documents=int(doc_cnt),
                total_chunks=int(chunk_cnt),
                total_edges=int(edge_cnt),
                orphan_chunks_count=int(orphan_cnt),
                issues=issues,
            )

    # 7. STG PREVIEW
    async def stg_preview(
        self, doc_code: str, path_prefix: str | None = None
    ) -> StgPreviewResult:
        """Previews lightweight structural summary of candidate chunks in staging."""
        session = self._staging.load_session(doc_code)
        chunks = session.chunks
        if path_prefix:
            clean_pre = validate_ltree_path(path_prefix)
            chunks = [c for c in chunks if c.path.startswith(clean_pre)]

        preview_hits = [
            StgPreviewHit(
                path=c.path,
                lead_sentence=c.lead_sentence,
                preview_text=c.verbatim_text[:120] + ("..." if len(c.verbatim_text) > 120 else ""),
                metadata=c.metadata,
            )
            for c in chunks
        ]

        return StgPreviewResult(
            doc_code=session.doc_code,
            title=session.title,
            total_chunks=len(session.chunks),
            total_edges=len(session.edges),
            chunks=preview_hits,
        )

    # 8. STG PATCH
    async def stg_patch(
        self,
        doc_code: str,
        updated_chunks: list[dict[str, Any]],
        removed_paths: list[str] | None = None,
    ) -> StgPatchResult:
        """Surgically updates candidate chunks in staging session."""
        chunks_to_patch = [StagingChunk.model_validate(c) for c in updated_chunks]
        updated_session = self._staging.patch_chunks(
            doc_code=doc_code,
            updated_chunks=chunks_to_patch,
            removed_paths=removed_paths,
        )
        return StgPatchResult(
            doc_code=doc_code,
            status="SUCCESS",
            total_chunks_after_patch=len(updated_session.chunks),
        )

    # 9. STG ADD EDGES
    async def stg_add_edges(
        self, doc_code: str, edges: list[dict[str, Any]]
    ) -> StgAddEdgesResult:
        """Appends and deduplicates relational graph edges in staging session."""
        stg_edges = [StagingEdge.model_validate(e) for e in edges]
        updated_session = self._staging.add_edges(doc_code=doc_code, edges=stg_edges)
        return StgAddEdgesResult(
            doc_code=doc_code,
            status="SUCCESS",
            total_edges=len(updated_session.edges),
        )

    # 10. STG COMMIT (Single Gateway Promotion)
    async def stg_commit(
        self, doc_code: str, compute_embeddings: bool = True
    ) -> StgCommitResult:
        """Atomically promotes staging session into PostgreSQL 3 tables and deletes staging session."""
        session = self._staging.load_session(doc_code)
        pool = await self._get_pool()
        loader = PostgresBulkLoader(pool=pool, compute_embeddings=compute_embeddings)

        doc_record = DocumentRecord(
            id=uuid.uuid4(),
            doc_code=session.doc_code,
            title=session.title,
            effective_date=datetime.date.fromisoformat(session.effective_date),
            expiration_date=datetime.date.fromisoformat(session.expiration_date)
            if session.expiration_date
            else None,
            metadata=session.doc_metadata,
        )

        # 1. Upsert document
        doc_id = await loader.load_document(doc_record)

        # 2. Prepare Canonical chunks
        canonical_chunks: list[CanonicalFullyQualifiedChunk] = []
        path_to_chunk_id: dict[str, uuid.UUID] = {}

        for c in session.chunks:
            c_uuid = uuid.uuid4()
            path_to_chunk_id[c.path] = c_uuid
            canonical_chunks.append(
                CanonicalFullyQualifiedChunk(
                    id=c_uuid,
                    document_id=doc_id,
                    path=c.path,
                    verbatim_text=c.verbatim_text,
                    contextualized_text=c.contextualized_text,
                    embedding=None,
                    metadata=c.metadata,
                    effective_date=datetime.date.fromisoformat(c.effective_date),
                    expiration_date=datetime.date.fromisoformat(c.expiration_date)
                    if c.expiration_date
                    else None,
                )
            )

        # 3. Load chunks
        chunk_ids = await loader.load_chunks(canonical_chunks)

        # 4. Prepare graph edges
        graph_edge_records: list[GraphEdgeRecord] = []
        for e in session.edges:
            src_uuid = path_to_chunk_id.get(e.source_path)
            tgt_uuid = path_to_chunk_id.get(e.target_path) if e.target_path else None
            if src_uuid is not None:
                graph_edge_records.append(
                    GraphEdgeRecord(
                        id=uuid.uuid4(),
                        source_chunk_id=src_uuid,
                        target_chunk_id=tgt_uuid,
                        target_external_ref=e.target_external_ref,
                        relation_type=e.relation_type,
                        citation_text=e.citation_text,
                        metadata=e.metadata,
                    )
                )

        # 5. Load edges
        edges_count = await loader.load_graph_edges(graph_edge_records)

        # 6. Clean up staging file
        self._staging.delete_session(doc_code)

        return StgCommitResult(
            doc_code=doc_code,
            document_id=str(doc_id),
            chunks_committed=len(chunk_ids),
            edges_committed=edges_count,
            status="SUCCESS",
        )
