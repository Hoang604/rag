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
    get_vietnam_today,
    parse_flexible_date,
    validate_ltree_path,
)

logger = logging.getLogger(__name__)


def _extract_metadata_dict(raw: Any) -> dict[str, Any]:
    """Helper to safely coerce database metadata column into Python dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


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
    temporal_as_of: str | None = None


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
    relative_depth: int = 0


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
    total_matched: int = 0
    limit: int = 50
    offset: int = 0
    has_more: bool = False
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
        embedding_engine: Any | None = None,
    ) -> None:
        self._pool = pool
        self._staging = staging_manager or StagingManager()
        self._embedding_engine = embedding_engine

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is not None:
            return self._pool
        try:
            self._pool = await get_db_pool()
            return self._pool
        except (OSError, RuntimeError, asyncpg.PostgresError) as exc:
            raise LegalDomainError(
                error_code=E_STORAGE_CONNECTION,
                message=f"Database storage connection failed: {exc}",
            ) from exc

    # --------------------------------------------------------------------------
    # Dynamic Corpus Manifest Builder
    # --------------------------------------------------------------------------
    async def build_dynamic_corpus_manifest(
        self,
        as_of_date: datetime.date | None = None,
    ) -> str:
        """Dynamically constructs a Markdown manifest of legal documents, their validity status, and modification lineages as of a given date in Vietnam timezone."""
        target_date = as_of_date or get_vietnam_today()
        date_str = target_date.strftime("%d/%m/%Y")

        try:
            pool = await self._get_pool()
        except (OSError, RuntimeError, LegalDomainError):
            return f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})\n- (Cơ sở dữ liệu đang ngoại tuyến hoặc chưa kết nối)"

        sql = """
        WITH doc_modifications AS (
            SELECT 
                src_d.doc_code AS modifying_doc_code,
                tgt_d.doc_code AS target_doc_code
            FROM graph_edges ge
            JOIN chunks src_c ON ge.source_chunk_id = src_c.id
            JOIN documents src_d ON src_c.document_id = src_d.id
            JOIN chunks tgt_c ON ge.target_chunk_id = tgt_c.id
            JOIN documents tgt_d ON tgt_c.document_id = tgt_d.id
            WHERE ge.relation_type = 'MODIFIES_AND_REPLACES'
            GROUP BY src_d.doc_code, tgt_d.doc_code
        ),
        doc_chunk_stats AS (
            SELECT 
                document_id,
                COUNT(id) AS total_chunks,
                COUNT(CASE WHEN expiration_date IS NOT NULL AND expiration_date <= $1::date THEN 1 END) AS expired_chunks
            FROM chunks
            GROUP BY document_id
        )
        SELECT 
            d.doc_code,
            d.title,
            d.effective_date,
            d.expiration_date,
            CASE 
                WHEN d.expiration_date IS NOT NULL AND d.expiration_date <= $1::date THEN 'EXPIRED'
                WHEN COALESCE(s.expired_chunks, 0) > 0 THEN 'PARTIALLY_MODIFIED'
                ELSE 'ACTIVE'
            END AS status,
            dm.modifying_doc_code
        FROM documents d
        LEFT JOIN doc_chunk_stats s ON d.id = s.document_id
        LEFT JOIN doc_modifications dm ON d.doc_code = dm.target_doc_code
        ORDER BY d.effective_date ASC, d.doc_code ASC;
        """

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, target_date)
        except (asyncpg.PostgresError, OSError, RuntimeError):
            return f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})\n- (Chưa có văn bản quy phạm pháp luật được nạp trong cơ sở dữ liệu)"

        if not rows:
            return f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})\n- (Chưa có văn bản quy phạm pháp luật được nạp trong cơ sở dữ liệu)"

        lines: list[str] = [f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})"]
        for r in rows:
            doc_code = str(r["doc_code"])
            title = str(r["title"])
            eff = (
                r["effective_date"].strftime("%d/%m/%Y")
                if isinstance(r["effective_date"], (datetime.date, datetime.datetime))
                else str(r["effective_date"])
            )
            status = r["status"]
            mod_code = r["modifying_doc_code"]

            if status == "ACTIVE":
                lines.append(f"- `[{doc_code}]` {title} (Hiệu lực từ: {eff}) — [CÒN HIỆU LỰC TOÀN BỘ]")
            elif status == "PARTIALLY_MODIFIED":
                mod_txt = f" (Sửa đổi, bổ sung bởi: `[{mod_code}]`)" if mod_code else ""
                lines.append(f"- `[{doc_code}]` {title} (Hiệu lực từ: {eff}) — [CÒN HIỆU LỰC MỘT PHẦN]{mod_txt}")
            else:  # EXPIRED
                exp = (
                    r["expiration_date"].strftime("%d/%m/%Y")
                    if isinstance(r["expiration_date"], (datetime.date, datetime.datetime))
                    else str(r["expiration_date"])
                )
                rep_txt = f" (Thay thế bởi: `[{mod_code}]`)" if mod_code else ""
                lines.append(
                    f"- `[{doc_code}]` {title} (Hiệu lực từ: {eff}, Hết hiệu lực: {exp}) — [HẾT HIỆU LỰC]{rep_txt}"
                )

        return "\n".join(lines)

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
        t_date = get_vietnam_today()
        if temporal_violation_date:
            parsed_d = parse_flexible_date(temporal_violation_date)
            if parsed_d is not None:
                t_date = parsed_d

        # Auto-compute dense vector if engine is available and vector not provided
        computed_vector = dense_vector
        if computed_vector is None and self._embedding_engine is not None:
            try:
                computed_vector = self._embedding_engine.encode(query).tolist()
            except (RuntimeError, ValueError, TypeError, AttributeError):
                computed_vector = None

        vector_param = json.dumps(computed_vector) if computed_vector is not None else None

        sql = """
        SELECT 
            chunk_id, doc_code, doc_title, path, verbatim_text,
            contextualized_text, metadata, effective_date, expiration_date, rrf_score
        FROM hybrid_search($1, $2::vector, $3::date, $4::int, 60);
        """
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, query, vector_param, t_date, limit)
                hits = [
                    SearchHit(
                        chunk_id=str(r["chunk_id"]),
                        doc_code=str(r["doc_code"]),
                        doc_title=str(r["doc_title"]),
                        path=str(r["path"]),
                        verbatim_text=str(r["verbatim_text"]),
                        contextualized_text=str(r["contextualized_text"]),
                        metadata=_extract_metadata_dict(r["metadata"]),
                        effective_date=str(r["effective_date"]),
                        expiration_date=str(r["expiration_date"])
                        if r["expiration_date"]
                        else None,
                        score=float(r["rrf_score"]),
                    )
                    for r in rows
                ]
                return HybridSearchResult(
                    total_hits=len(hits),
                    hits=hits,
                    temporal_as_of=t_date.isoformat(),
                )
        except (OSError, RuntimeError, asyncpg.PostgresError, TypeError, ValueError) as exc:
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
        t_date = get_vietnam_today()
        if temporal_violation_date:
            parsed_d = parse_flexible_date(temporal_violation_date)
            if parsed_d is not None:
                t_date = parsed_d

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
                        metadata=_extract_metadata_dict(r["metadata"]),
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
        except (OSError, RuntimeError, asyncpg.PostgresError, TypeError, ValueError) as exc:
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
        direction: str = "FULL_ARTICLE",
    ) -> HierarchicalNavigateResult:
        """Navigates statutory hierarchy using PostgreSQL ltree operators (<@, @>, subpath)."""
        pool = await self._get_pool()
        dir_upper = direction.upper()
        if dir_upper not in ("FULL_ARTICLE", "CHILDREN", "PARENT_CHAIN", "SIBLINGS"):
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=f"Invalid navigation direction: '{direction}'. Expected 'FULL_ARTICLE', 'CHILDREN', 'PARENT_CHAIN', or 'SIBLINGS'.",
            )

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

            if dir_upper == "CHILDREN":
                sql = """
                SELECT c.id, c.path::text, d.doc_code, c.verbatim_text, c.contextualized_text, c.metadata,
                       (nlevel(c.path) - nlevel($1::ltree)) AS rel_depth
                FROM chunks c JOIN documents d ON c.document_id = d.id
                WHERE c.path <@ $1::ltree AND c.path != $1::ltree
                ORDER BY c.path ASC LIMIT 50;
                """
            elif dir_upper == "PARENT_CHAIN":
                sql = """
                SELECT c.id, c.path::text, d.doc_code, c.verbatim_text, c.contextualized_text, c.metadata,
                       (nlevel($1::ltree) - nlevel(c.path)) AS rel_depth
                FROM chunks c JOIN documents d ON c.document_id = d.id
                WHERE c.path @> $1::ltree
                ORDER BY nlevel(c.path) ASC;
                """
            elif dir_upper == "SIBLINGS":
                sql = """
                SELECT c.id, c.path::text, d.doc_code, c.verbatim_text, c.contextualized_text, c.metadata,
                       0 AS rel_depth
                FROM chunks c JOIN documents d ON c.document_id = d.id
                WHERE subpath(c.path, 0, nlevel($1::ltree) - 1) = subpath($1::ltree, 0, nlevel($1::ltree) - 1)
                  AND nlevel(c.path) = nlevel($1::ltree)
                ORDER BY c.path ASC;
                """
            else:  # FULL_ARTICLE
                sql = """
                SELECT c.id, c.path::text, d.doc_code, c.verbatim_text, c.contextualized_text, c.metadata,
                       (nlevel(c.path) - nlevel($1::ltree)) AS rel_depth
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
                    metadata=_extract_metadata_dict(r["metadata"]),
                    relative_depth=int(r.get("rel_depth", 0)),
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
            $1, $2::uuid, $3::uuid, $4, $5, $6, $7
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
                metadata or {},
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
        self,
        doc_code: str,
        path_prefix: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StgPreviewResult:
        """Previews lightweight structural summary of candidate chunks in staging with pagination support."""
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

    # 8. STG PATCH
    async def stg_patch(
        self,
        doc_code: str,
        updated_chunks: list[dict[str, Any]] | None = None,
        removed_paths: list[str] | None = None,
    ) -> StgPatchResult:
        """Surgically updates candidate chunks in staging session."""
        chunks_to_patch = [StagingChunk.model_validate(c) for c in (updated_chunks or [])]
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
        """Atomically promotes staging session into PostgreSQL 3 tables, resolving cross-document edges and re-used UUIDs."""
        session = self._staging.load_session(doc_code)
        pool = await self._get_pool()
        loader = PostgresBulkLoader(pool=pool, compute_embeddings=compute_embeddings)

        doc_record = DocumentRecord(
            id=uuid.uuid4(),
            doc_code=session.doc_code,
            title=session.title,
            effective_date=session.effective_date,
            expiration_date=session.expiration_date,
            metadata=session.doc_metadata,
        )

        # 1. Upsert document
        doc_id = await loader.load_document(doc_record)

        # 2. Prepare Canonical chunks
        canonical_chunks: list[CanonicalFullyQualifiedChunk] = [
            CanonicalFullyQualifiedChunk(
                id=uuid.uuid4(),
                document_id=doc_id,
                path=c.path,
                verbatim_text=c.verbatim_text,
                contextualized_text=c.contextualized_text,
                embedding=None,
                metadata=c.metadata,
                effective_date=c.effective_date,
                expiration_date=c.expiration_date,
            )
            for c in session.chunks
        ]

        # 3. Load chunks and retrieve authoritative persistent UUIDs from PostgreSQL
        path_to_chunk_id = await loader.load_chunks(canonical_chunks)

        # 4. Resolve external target paths for cross-document edges
        external_target_paths = {
            e.target_path
            for e in session.edges
            if e.target_path and e.target_path not in path_to_chunk_id
        }
        resolved_external: dict[str, uuid.UUID] = {}
        if external_target_paths:
            resolved_external = await loader.resolve_chunk_paths(list(external_target_paths))

        all_paths_map = {**path_to_chunk_id, **resolved_external}

        # 5. Prepare graph edges with strict fail-fast validation on source_path
        graph_edge_records: list[GraphEdgeRecord] = []
        for e in session.edges:
            src_uuid = path_to_chunk_id.get(e.source_path)
            if src_uuid is None:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=f"Invalid edge source path '{e.source_path}': chunk path does not exist in document '{doc_code}'.",
                    data={"doc_code": doc_code, "source_path": e.source_path},
                )

            tgt_uuid = all_paths_map.get(e.target_path) if e.target_path else None

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

        # 6. Load edges
        edges_count = await loader.load_graph_edges(graph_edge_records)

        # 7. Clean up staging file
        self._staging.delete_session(doc_code)

        return StgCommitResult(
            doc_code=doc_code,
            document_id=str(doc_id),
            chunks_committed=len(canonical_chunks),
            edges_committed=edges_count,
            status="SUCCESS",
        )
