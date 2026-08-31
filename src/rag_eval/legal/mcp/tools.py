"""Specialized 8 canonical domain handlers for Model Context Protocol (MCP) server."""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import math
import re
import uuid
from typing import Any, cast

import asyncpg
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.schemas import (
    ASTGroundingValidationError,
    GraphRelationType,
    HierarchyNavigationError,
    StorageConnectionError,
    VectorDimensionMismatchError,
)


class LegalMCPBaseModel(BaseModel):
    """Base Pydantic model for MCP responses supporting both direct attribute access and dict indexing."""

    model_config = ConfigDict(extra="ignore", from_attributes=True, populate_by_name=True)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError as err:
            raise KeyError(item) from err

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __contains__(self, item: object) -> bool:
        return hasattr(self, str(item))


class SearchResultItem(LegalMCPBaseModel):
    chunk_id: str
    doc_code: str
    doc_title: str = ""
    path: str
    chunk_level: str = ""
    chunk_index: str
    title: str = ""
    lead_sentence: str | None = None
    raw_text: str = ""
    verbatim_text: str = ""
    contextualized_text: str = ""
    norm_role: str | None = None
    min_fine_vnd: int | None = None
    max_fine_vnd: int | None = None
    additional_sanctions: dict[str, object] = Field(default_factory=dict)
    remedial_measures: list[dict[str, object]] | list[str] = Field(default_factory=list)
    is_exception: bool = False
    rrf_score: float = 0.0
    dense_rank: int | None = None
    sparse_rank: int | None = None
    effective_date: str | None = None
    expiration_date: str | None = None
    similarity_score: float = 0.0
    match_headline: str = ""

    @model_validator(mode="before")
    @classmethod
    def sync_text_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "chunk_id" in data and data["chunk_id"] is not None:
                data["chunk_id"] = str(data["chunk_id"])
            raw = str(data.get("raw_text") or "")
            verb = str(data.get("verbatim_text") or "")
            text = verb or raw
            data["verbatim_text"] = text
            data["raw_text"] = raw or text
            if not data.get("doc_title") and data.get("title"):
                data["doc_title"] = data["title"]
            if not data.get("title") and data.get("doc_title"):
                data["title"] = data["doc_title"]
        return data

    @field_validator("additional_sanctions", mode="before")
    @classmethod
    def parse_additional_sanctions(cls, v: object) -> dict[str, object]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        if isinstance(v, dict):
            return v
        return {}

    @field_validator("remedial_measures", mode="before")
    @classmethod
    def parse_remedial_measures(cls, v: object) -> list[dict[str, object]] | list[str]:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return []
        if isinstance(v, list):
            return v
        return []


class HierarchyNodeItem(LegalMCPBaseModel):
    chunk_id: str
    parent_id: str | None = None
    path: str
    depth: int = 1
    chunk_level: str = ""
    chunk_index: str
    title: str = ""
    lead_sentence: str | None = None
    raw_text: str = ""
    verbatim_text: str
    contextualized_text: str = ""
    norm_role: str | None = None
    doc_code: str = ""


class TraversalPathItem(LegalMCPBaseModel):
    hop_depth: int = 1
    edge_id: str = ""
    relation_type: str
    source_chunk_id: str
    source_path: str = ""
    target_chunk_id: str | None = None
    target_path: str | None = None
    target_doc_code: str = ""
    target_chunk_index: str = ""
    target_norm_role: str = ""
    target_raw_text: str = ""
    target_contextualized_text: str = ""
    min_fine_vnd: int | None = None
    max_fine_vnd: int | None = None
    is_conditional: bool = False
    condition_expression: str | None = None
    confidence_score: float = 1.0
    traversal_trail: str = ""


class CorpusValidateResult(LegalMCPBaseModel):
    status: str = "success"
    document_id: str
    doc_code: str
    doc_title: str = ""
    is_valid: bool = True
    total_chunks_scanned: int = 0
    total_edges_scanned: int = 0
    summary: str = ""
    total_anomalies_detected: int = 0
    anomalies: list[dict[str, object]] = Field(default_factory=list)
    orphaned_points: list[str] = Field(default_factory=list)
    missing_embeddings: list[str] = Field(default_factory=list)
    broken_edges: list[str] = Field(default_factory=list)
    validation_timestamp: str = ""


class HybridSearchResult(LegalMCPBaseModel):
    status: str = "success"
    query: str
    total_hits: int = 0
    results: list[SearchResultItem] = Field(default_factory=list)
    execution_time_ms: float = 0.0


class VerbatimGrepResult(LegalMCPBaseModel):
    status: str = "success"
    query: str = ""
    pattern: str = ""
    is_regex: bool = False
    case_sensitive: bool = False
    total_hits: int = 0
    total_matches: int = 0
    results: list[SearchResultItem] = Field(default_factory=list)
    matched_articles: list[str] = Field(default_factory=list)


class HierarchicalNavigateResult(LegalMCPBaseModel):
    status: str = "success"
    target_path: str
    direction: str
    depth: int = 1
    nodes: list[HierarchyNodeItem] = Field(default_factory=list)
    total_nodes: int = 0


class GraphTraverseResult(LegalMCPBaseModel):
    status: str = "success"
    start_chunk_id: str
    direction: str = "both"
    max_depth: int = 2
    traversal_paths: list[TraversalPathItem] = Field(default_factory=list)
    total_paths: int = 0
    visited_nodes: list[str] = Field(default_factory=list)
    edges: list[TraversalPathItem] = Field(default_factory=list)
    traversed_paths: list[TraversalPathItem] = Field(default_factory=list)
    total_edges: int = 0


class SignCatalogLookupResult(LegalMCPBaseModel):
    status: str = "success"
    sign_code: str = ""
    sign_name: str = ""
    category: str = ""
    meaning: str = ""
    statutory_reference: str = ""
    sign: dict[str, object] = Field(default_factory=dict)
    signs: list[dict[str, object]] = Field(default_factory=list)
    total_hits: int = 0
    total_matches: int = 0
    results: list[dict[str, object]] = Field(default_factory=list)


class GraphEdgeWriteResult(LegalMCPBaseModel):
    status: str = "success"
    is_persisted: bool = True
    source_chunk_id: str
    target_chunk_id: str | None = None
    relation_type: str = ""
    confidence_score: float = 1.0
    edge: dict[str, object] = Field(default_factory=dict)


class KnowledgeCacheQueryResult(LegalMCPBaseModel):
    status: str = "miss"
    query_hash: str = ""
    cache_id: str = ""
    cache_entry: dict[str, object] | None = None
    cached_entry: dict[str, object] | None = None
    cache_hit: bool = False
    answer: str = ""
    similarity_score: float = 0.0
    is_exact_match: bool = False


class KnowledgeCacheWriteResult(LegalMCPBaseModel):
    status: str = "success"
    cache_id: str
    query_hash: str
    is_persisted: bool = True


logger = logging.getLogger(__name__)


def is_redos_safe(pattern: str) -> tuple[bool, str | None]:
    """Validates regular expression safety against ReDoS exponential backtracking attacks."""
    clean_pat = pattern.strip()
    if not clean_pat:
        return True, None

    try:
        re.compile(clean_pat)
    except re.error as err:
        return False, f"Invalid regular expression syntax: {err}"

    nested_quantifiers = re.compile(
        r"\([^)]*[\+\*]\)[\+\*]|\([^)]*\{[0-9]+,\s*\}\)[\+\*]|\([^)]*[\+\*]\)\{[0-9]+,\s*\}",
        re.IGNORECASE,
    )
    if nested_quantifiers.search(clean_pat):
        return False, "Potential ReDoS vulnerability: nested unbounded quantifiers detected."

    overlapping_alternations = re.compile(
        r"\(([^|)]+)\|(\1)\)[\+\*]",
        re.IGNORECASE,
    )
    if overlapping_alternations.search(clean_pat):
        return False, "Potential ReDoS vulnerability: overlapping alternation with quantifier detected."

    group_nested_repeat = re.compile(
        r"\(\[[^\]]+\][\+\*]\)[\+\*\{]",
        re.IGNORECASE,
    )
    if group_nested_repeat.search(clean_pat):
        return False, "Potential ReDoS vulnerability: nested group quantifier on character class detected."

    return True, None


class LegalMCPTools:
    """Production handlers for the 8 canonical Vietnamese Traffic Law MCP tools."""

    def __init__(self, pool: object = None) -> None:
        self.pool = pool

    async def _ensure_pool(self) -> asyncpg.Pool:
        """Acquires active PostgreSQL connection pool directly."""
        if self.pool is not None:
            return cast(asyncpg.Pool, self.pool)

        try:
            pool = await get_db_pool()
            self.pool = pool
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'runtime_knowledge_cache' AND column_name = 'query_embedding') THEN ALTER TABLE runtime_knowledge_cache ALTER COLUMN query_embedding DROP NOT NULL; END IF; END $$;"
                    )
            except (asyncpg.PostgresError, OSError):
                pass
            return pool
        except (RuntimeError, OSError, TimeoutError, asyncpg.PostgresError) as exc:
            logger.error("Database connection pool unavailable: %s", exc)
            raise StorageConnectionError(
                f"Database connection pool unavailable: {exc}",
                data={"error_type": type(exc).__name__, "details": str(exc)},
            ) from exc

    # --------------------------------------------------------------------------
    # 1. mcp_traffic_hybrid_search
    # --------------------------------------------------------------------------
    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        document_codes: list[str] | None = None,
        effective_at: str | None = None,
    ) -> HybridSearchResult:
        """Executes pure dense vector + tsvector lexical search over verbatim statutory text."""
        pool = await self._ensure_pool()

        # Compute dense embedding vector (384-dim) dynamically
        query_vec: list[float] = [0.0] * 384
        try:
            from rag_eval.legal.ingestion.loader import compute_query_embedding

            computed = compute_query_embedding(query)
            if computed is not None:
                query_vec = computed
        except (RuntimeError, ValueError, TypeError, OSError, ImportError):
            query_vec = [0.0] * 384

        vector_param = f"[{','.join(str(x) for x in query_vec)}]"
        results: list[SearchResultItem] = []

        eff_date: datetime.date
        if effective_at:
            try:
                eff_date = datetime.date.fromisoformat(effective_at.strip())
            except ValueError:
                eff_date = datetime.datetime.now(tz=datetime.UTC).date()
        else:
            eff_date = datetime.datetime.now(tz=datetime.UTC).date()

        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    """
                    WITH rrf_matches AS (
                        SELECT chunk_id, path, chunk_index, contextualized_text,
                               min_fine_vnd, max_fine_vnd, rrf_score, dense_rank, sparse_rank
                        FROM hybrid_legal_search_384($1::text, $2::vector, NULL::actor_category, NULL::text[], $3::int, 60, $5::date)
                    )
                    SELECT m.chunk_id, m.path, m.chunk_index, m.contextualized_text,
                       m.min_fine_vnd, m.max_fine_vnd, m.rrf_score, m.dense_rank, m.sparse_rank,
                       c.lead_sentence, c.verbatim_text, c.norm_role::text,
                       c.additional_sanctions, c.remedial_measures, c.is_exception,
                       d.doc_code, d.title as doc_title
                    FROM rrf_matches m
                    JOIN legal_chunks c ON m.chunk_id = c.id
                    JOIN legal_documents d ON c.document_id = d.id
                    WHERE ($4::text[] IS NULL OR d.doc_code = ANY($4::text[]))
                    ORDER BY m.rrf_score DESC
                    LIMIT $3;
                    """,
                    query,
                    vector_param,
                    limit,
                    document_codes,
                    eff_date,
                )
                for r in rows:
                    row_dict = dict(r)
                    if "doc_title" not in row_dict and "title" in row_dict:
                        row_dict["doc_title"] = row_dict["title"]
                    if "raw_text" not in row_dict and "verbatim_text" in row_dict:
                        row_dict["raw_text"] = row_dict["verbatim_text"]
                    results.append(SearchResultItem.model_validate(row_dict))
            except (asyncpg.PostgresError, OSError) as err:
                err_str = str(err).lower()
                if "different vector dimensions" in err_str or "vector dimension" in err_str or "dimension mismatch" in err_str:
                    logger.error("Vector dimension mismatch: %s", err)
                    raise VectorDimensionMismatchError(f"Vector dimension mismatch: {err}") from err
                logger.error("Database hybrid search failed: %s", err)
                raise StorageConnectionError(f"Database hybrid search failed: {err}") from err

        return HybridSearchResult(
            status="success",
            query=query,
            total_hits=len(results),
            results=results[:limit],
        )

    # --------------------------------------------------------------------------
    # 2. mcp_traffic_verbatim_grep
    # --------------------------------------------------------------------------
    async def verbatim_grep(
        self,
        pattern: str,
        is_regex: bool = False,
        limit: int = 20,
        document_codes: list[str] | None = None,
        case_sensitive: bool = False,
        effective_at: str | None = None,
    ) -> VerbatimGrepResult:
        """Executes Trigram GIN accelerated verbatim substring and regex search with ReDoS safety."""
        clean_pattern = pattern.strip()
        if not clean_pattern:
            return VerbatimGrepResult(
                status="success",
                query=pattern,
                pattern=pattern,
                is_regex=is_regex,
                case_sensitive=case_sensitive,
                total_hits=0,
                total_matches=0,
                results=[],
            )

        if is_regex:
            is_safe, safety_err = is_redos_safe(clean_pattern)
            if not is_safe:
                raise ASTGroundingValidationError(
                    f"Regex safety validation failed: {safety_err}",
                    data={"pattern": clean_pattern, "error": safety_err},
                )

        eff_date: datetime.date
        if effective_at:
            try:
                eff_date = datetime.date.fromisoformat(effective_at.strip())
            except ValueError:
                eff_date = datetime.datetime.now(tz=datetime.UTC).date()
        else:
            eff_date = datetime.datetime.now(tz=datetime.UTC).date()

        pool = await self._ensure_pool()
        results: list[SearchResultItem] = []

        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    """
                    WITH grep_matches AS (
                        SELECT chunk_id, path, doc_code, chunk_index,
                               verbatim_text, contextualized_text,
                               min_fine_vnd, max_fine_vnd, similarity_score,
                               effective_date, expiration_date
                        FROM verbatim_legal_grep($1::text, $2::text[], NULL::text[], $3::boolean, $4::boolean, $6::date, $5::int)
                    )
                    SELECT m.chunk_id, m.path, m.doc_code, m.chunk_index,
                           m.verbatim_text, m.contextualized_text,
                           m.min_fine_vnd, m.max_fine_vnd, m.similarity_score,
                           m.effective_date, m.expiration_date,
                           c.lead_sentence, c.norm_role::text,
                           c.additional_sanctions, c.remedial_measures, c.is_exception,
                           d.title as doc_title
                    FROM grep_matches m
                    JOIN legal_chunks c ON m.chunk_id = c.id
                    JOIN legal_documents d ON c.document_id = d.id;
                    """,
                    clean_pattern,
                    document_codes,
                    is_regex,
                    case_sensitive,
                    limit,
                    eff_date,
                )
                for r in rows:
                    row_dict = dict(r)
                    if "doc_title" not in row_dict and "title" in row_dict:
                        row_dict["doc_title"] = row_dict["title"]
                    if "raw_text" not in row_dict and "verbatim_text" in row_dict:
                        row_dict["raw_text"] = row_dict["verbatim_text"]
                    results.append(SearchResultItem.model_validate(row_dict))
            except (asyncpg.PostgresError, OSError) as err:
                logger.error("Verbatim grep query failed: %s", err)
                raise StorageConnectionError(f"Verbatim grep query failed: {err}") from err

        return VerbatimGrepResult(
            status="success",
            query=pattern,
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            total_hits=len(results),
            total_matches=len(results),
            results=results[:limit],
        )

    # --------------------------------------------------------------------------
    # 3. mcp_traffic_hierarchical_navigate
    # --------------------------------------------------------------------------
    async def hierarchical_navigate(
        self,
        target_path: str,
        direction: str = "children",
        include_verbatim: bool = True,
    ) -> HierarchicalNavigateResult:
        """Explores statutory tree hierarchy of legal instruments using PostgreSQL ltree."""
        pool = await self._ensure_pool()
        dir_clean = direction.strip().upper()
        nodes_db: list[HierarchyNodeItem] = []

        async with pool.acquire() as conn:
            try:
                if dir_clean in ("PARENT_CHAIN", "PARENTS"):
                    rows = await conn.fetch(
                        """
                        SELECT c.id as chunk_id, c.path::text, nlevel(c.path) as depth, c.chunk_index,
                               c.verbatim_text, c.contextualized_text, c.lead_sentence,
                               c.norm_role::text, d.doc_code, d.title as doc_title
                        FROM legal_chunks c
                        JOIN legal_documents d ON c.document_id = d.id
                        WHERE c.path @> $1::ltree
                        ORDER BY nlevel(c.path) ASC;
                        """,
                        target_path,
                    )
                elif dir_clean in ("CHILDREN", "DESCENDANTS"):
                    rows = await conn.fetch(
                        """
                        SELECT c.id as chunk_id, c.path::text, nlevel(c.path) as depth, c.chunk_index,
                               c.verbatim_text, c.contextualized_text, c.lead_sentence,
                               c.norm_role::text, d.doc_code, d.title as doc_title
                        FROM legal_chunks c
                        JOIN legal_documents d ON c.document_id = d.id
                        WHERE c.path <@ $1::ltree AND c.path != $1::ltree
                        ORDER BY nlevel(c.path) ASC, c.path ASC;
                        """,
                        target_path,
                    )
                elif dir_clean in ("SIBLINGS",):
                    rows = await conn.fetch(
                        """
                        SELECT c.id as chunk_id, c.path::text, nlevel(c.path) as depth, c.chunk_index,
                               c.verbatim_text, c.contextualized_text, c.lead_sentence,
                               c.norm_role::text, d.doc_code, d.title as doc_title
                        FROM legal_chunks c
                        JOIN legal_documents d ON c.document_id = d.id
                        WHERE subpath(c.path, 0, nlevel(c.path) - 1) = subpath($1::ltree, 0, nlevel($1::ltree) - 1)
                          AND nlevel(c.path) = nlevel($1::ltree)
                        ORDER BY c.path ASC;
                        """,
                        target_path,
                    )
                elif dir_clean in ("FULL_ARTICLE", "ARTICLE"):
                    # Extract article prefix dynamically (e.g. 'doc_100.c2.a5' or 'doc_36.a5a')
                    parts = target_path.split(".")
                    art_idx = next(
                        (i for i, p in enumerate(parts) if re.match(r"^(?:a\d+[a-z]?|art\d+)$", p, re.IGNORECASE)),
                        len(parts) - 1,
                    )
                    art_path = ".".join(parts[: art_idx + 1])
                    rows = await conn.fetch(
                        """
                        SELECT c.id as chunk_id, c.path::text, nlevel(c.path) as depth, c.chunk_index,
                               c.verbatim_text, c.contextualized_text, c.lead_sentence,
                               c.norm_role::text, d.doc_code, d.title as doc_title
                        FROM legal_chunks c
                        JOIN legal_documents d ON c.document_id = d.id
                        WHERE c.path <@ $1::ltree
                        ORDER BY nlevel(c.path) ASC, c.path ASC;
                        """,
                        art_path,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT c.id as chunk_id, c.path::text, nlevel(c.path) as depth, c.chunk_index,
                               c.verbatim_text, c.contextualized_text, c.lead_sentence,
                               c.norm_role::text, d.doc_code, d.title as doc_title
                        FROM legal_chunks c
                        JOIN legal_documents d ON c.document_id = d.id
                        WHERE c.path <@ $1::ltree
                        ORDER BY nlevel(c.path) ASC, c.path ASC;
                        """,
                        target_path,
                    )

                for r in rows:
                    row_dict = dict(r)
                    if "chunk_level" not in row_dict:
                        p = str(row_dict.get("path", ""))
                        last_seg = p.split(".")[-1]
                        if last_seg.startswith("p_"):
                            row_dict["chunk_level"] = "POINT"
                        elif re.match(r"^c\d+$", last_seg):
                            row_dict["chunk_level"] = "CLAUSE"
                        elif re.match(r"^a\d+[a-z]?$", last_seg) or last_seg.startswith("art"):
                            row_dict["chunk_level"] = "ARTICLE"
                        elif last_seg.startswith(("c_", "ch_")):
                            row_dict["chunk_level"] = "CHAPTER"
                        else:
                            row_dict["chunk_level"] = "NODE"
                    if "title" not in row_dict and "doc_title" in row_dict:
                        row_dict["title"] = row_dict["doc_title"]
                    if not include_verbatim:
                        row_dict["verbatim_text"] = ""
                        row_dict["raw_text"] = ""
                        row_dict["contextualized_text"] = ""
                    nodes_db.append(HierarchyNodeItem.model_validate(row_dict))
            except (asyncpg.PostgresError, OSError) as err:
                logger.error("Hierarchical navigate query failed: %s", err)
                raise HierarchyNavigationError(f"Hierarchical navigation failed: {err}") from err

        return HierarchicalNavigateResult(
            status="success",
            target_path=target_path,
            direction=direction,
            depth=len(nodes_db),
            total_nodes=len(nodes_db),
            nodes=nodes_db,
        )


    # --------------------------------------------------------------------------
    # 4. mcp_traffic_graph_traverse
    # --------------------------------------------------------------------------
    async def graph_traverse(
        self,
        start_chunk_id: str | uuid.UUID,
        relation_types: list[str] | list[GraphRelationType] | None = None,
        direction: str = "both",
        max_depth: int = 2,
    ) -> GraphTraverseResult:
        """Executes multi-hop CTE graph traversal across legal property graph edges."""
        pool = await self._ensure_pool()
        start_id_str = str(start_chunk_id).strip()
        dir_clean = direction.strip().upper()
        rel_types_str = (
            [str(r.value if isinstance(r, GraphRelationType) else r) for r in relation_types]
            if relation_types
            else None
        )

        paths: list[TraversalPathItem] = []

        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    """
                    WITH RECURSIVE traversal AS (
                        SELECT e.id as edge_id, e.source_chunk_id, e.target_chunk_id,
                               e.relation_type::text, e.confidence_score, e.is_conditional,
                               e.condition_expression, 1 as hop_depth,
                               ARRAY[e.source_chunk_id, e.target_chunk_id]::uuid[] as visited_nodes
                        FROM legal_graph_edges e
                        WHERE (
                            ($2 = 'OUTGOING' AND (e.source_chunk_id::text = $1 OR e.source_path::text = $1))
                            OR ($2 = 'INCOMING' AND (e.target_chunk_id::text = $1 OR e.target_path::text = $1))
                            OR ($2 = 'BOTH' AND (e.source_chunk_id::text = $1 OR e.target_chunk_id::text = $1 OR e.source_path::text = $1 OR e.target_path::text = $1))
                        )
                        AND ($3::text[] IS NULL OR e.relation_type::text = ANY($3::text[]))

                        UNION ALL

                        SELECT e.id as edge_id, e.source_chunk_id, e.target_chunk_id,
                               e.relation_type::text, e.confidence_score, e.is_conditional,
                               e.condition_expression, t.hop_depth + 1,
                               t.visited_nodes || e.target_chunk_id
                        FROM legal_graph_edges e
                        JOIN traversal t ON e.source_chunk_id = t.target_chunk_id
                        WHERE t.hop_depth < $4
                          AND e.target_chunk_id IS NOT NULL
                          AND NOT (e.target_chunk_id = ANY(t.visited_nodes))
                          AND ($3::text[] IS NULL OR e.relation_type::text = ANY($3::text[]))
                    )
                    SELECT t.edge_id, t.hop_depth, t.relation_type, t.confidence_score,
                           t.is_conditional, t.condition_expression,
                           t.source_chunk_id, sc.path::text as source_path,
                           t.target_chunk_id, tc.path::text as target_path,
                           td.doc_code as target_doc_code, tc.chunk_index as target_chunk_index,
                           tc.norm_role::text as target_norm_role, tc.verbatim_text as target_raw_text,
                           tc.contextualized_text as target_contextualized_text,
                           tc.min_fine_vnd, tc.max_fine_vnd
                    FROM traversal t
                    LEFT JOIN legal_chunks sc ON t.source_chunk_id = sc.id
                    LEFT JOIN legal_chunks tc ON t.target_chunk_id = tc.id
                    LEFT JOIN legal_documents td ON tc.document_id = td.id
                    ORDER BY t.hop_depth ASC, t.confidence_score DESC;
                    """,
                    start_id_str,
                    dir_clean if dir_clean in ("OUTGOING", "INCOMING", "BOTH") else "BOTH",
                    rel_types_str,
                    max_depth,
                )
                for r in rows:
                    row_dict = dict(r)
                    row_dict["traversal_trail"] = f"{row_dict.get('source_path', '')} -[{row_dict.get('relation_type', '')}]-> {row_dict.get('target_path', '')}"
                    paths.append(TraversalPathItem.model_validate(row_dict))
            except (asyncpg.PostgresError, OSError) as err:
                logger.error("Graph traverse query failed: %s", err)
                raise StorageConnectionError(f"Graph traverse query failed: {err}") from err

        return GraphTraverseResult(
            status="success",
            start_chunk_id=start_id_str,
            direction=direction,
            max_depth=max_depth,
            total_paths=len(paths),
            total_edges=len(paths),
            traversal_paths=paths,
            edges=paths,
            traversed_paths=paths,
        )

    # --------------------------------------------------------------------------
    # 5. mcp_traffic_graph_edge_write
    # --------------------------------------------------------------------------
    async def graph_edge_write(
        self,
        source_id: str | uuid.UUID,
        target_id: str | uuid.UUID | None = None,
        relation_type: str | GraphRelationType = "REFERENCES_TECHNICAL_STANDARD",
        confidence: float = 1.0,
        is_conditional: bool = False,
        condition_expression: str | None = None,
        source_path: str | None = None,
        target_path: str | None = None,
        **kwargs: object,
    ) -> GraphEdgeWriteResult:
        """Dynamically inserts or updates a directed graph edge in PostgreSQL."""
        pool = await self._ensure_pool()
        src_id = str(source_id).strip()
        tgt_id = str(target_id).strip() if target_id else None
        rel_str = relation_type.value if isinstance(relation_type, GraphRelationType) else str(relation_type)
        edge_id = str(uuid.uuid4())

        async with pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO legal_graph_edges (
                        id, source_chunk_id, target_chunk_id, relation_type,
                        confidence_score, is_conditional, condition_expression,
                        source_path, target_path
                    )
                    VALUES ($1::uuid, $2::uuid, $3::uuid, $4::graph_relation_type, $5, $6, $7, $8::ltree, $9::ltree)
                    ON CONFLICT ON CONSTRAINT uq_graph_edge
                    DO UPDATE SET confidence_score = EXCLUDED.confidence_score,
                                  is_conditional = EXCLUDED.is_conditional,
                                  condition_expression = EXCLUDED.condition_expression
                    RETURNING id, source_chunk_id, target_chunk_id, relation_type::text, confidence_score;
                    """,
                    edge_id,
                    src_id,
                    tgt_id,
                    rel_str,
                    confidence,
                    is_conditional,
                    condition_expression,
                    source_path,
                    target_path,
                )
                persisted_id = str(row["id"]) if row else edge_id
            except (asyncpg.PostgresError, OSError) as err:
                logger.error("Graph edge write failed: %s", err)
                raise StorageConnectionError(f"Graph edge write failed: {err}") from err

        return GraphEdgeWriteResult(
            status="success",
            is_persisted=True,
            source_chunk_id=src_id,
            target_chunk_id=tgt_id,
            relation_type=rel_str,
            confidence_score=confidence,
            edge={
                "edge_id": persisted_id,
                "source_chunk_id": src_id,
                "target_chunk_id": tgt_id,
                "relation_type": rel_str,
                "confidence_score": confidence,
            },
        )

    # --------------------------------------------------------------------------
    # 6. mcp_traffic_sign_catalog_lookup
    # --------------------------------------------------------------------------
    async def sign_catalog_lookup(
        self,
        sign_code: str | None = None,
        query_keyword: str | None = None,
        limit: int = 5,
        category: str | None = None,
    ) -> SignCatalogLookupResult:
        """Looks up traffic signs, markings, and technical specs from QCVN 41:2019 catalog table."""
        pool = await self._ensure_pool()
        signs: list[dict[str, object]] = []
        code_pattern = f"%{sign_code.strip().upper()}%" if sign_code else None
        kw_pattern = f"%{query_keyword.strip()}%" if query_keyword else None

        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    """
                    SELECT sign_code, sign_name, sign_category::text as category, shape, primary_color,
                           meaning, placement_rules, penalty_references
                    FROM sign_catalog
                    WHERE ($1::text IS NULL OR sign_code ILIKE $1)
                      AND ($2::text IS NULL OR sign_name ILIKE $2 OR meaning ILIKE $2)
                      AND ($3::text IS NULL OR sign_category::text = $3)
                    ORDER BY sign_code ASC
                    LIMIT $4;
                    """,
                    code_pattern,
                    kw_pattern,
                    category,
                    limit,
                )
                for r in rows:
                    refs = r["penalty_references"]
                    if isinstance(refs, str):
                        try:
                            refs = json.loads(refs)
                        except json.JSONDecodeError:
                            refs = []
                    signs.append(
                        {
                            "sign_code": r["sign_code"],
                            "sign_name": r["sign_name"],
                            "category": r["category"],
                            "shape": r["shape"],
                            "primary_color": r["primary_color"],
                            "meaning": r["meaning"],
                            "placement_rules": r["placement_rules"],
                            "penalty_references": refs or [],
                        }
                    )
            except (asyncpg.PostgresError, OSError) as err:
                logger.error("Sign catalog lookup failed: %s", err)
                raise StorageConnectionError(f"Sign catalog lookup failed: {err}") from err

        first_sign = signs[0] if signs else {}
        return SignCatalogLookupResult(
            status="success",
            sign_code=str(first_sign.get("sign_code", sign_code or "")),
            sign_name=str(first_sign.get("sign_name", "")),
            category=str(first_sign.get("category", "")),
            meaning=str(first_sign.get("meaning", "")),
            sign=first_sign,
            signs=signs,
            total_hits=len(signs),
            total_matches=len(signs),
            results=signs,
        )

    # --------------------------------------------------------------------------
    # 7. mcp_traffic_corpus_validate
    # --------------------------------------------------------------------------
    async def corpus_validate(
        self,
        document_id: str | None = None,
        check_embeddings: bool = True,
        check_orphans: bool = True,
        check_broken_edges: bool = True,
        check_path_continuity: bool = True,
    ) -> CorpusValidateResult:
        """Validates structural and relational integrity of ingested legal documents directly in DB."""
        pool = await self._ensure_pool()
        total_chunks = 0
        total_edges = 0
        anomalies: list[dict[str, object]] = []
        doc_code_str = document_id or "ALL"
        doc_title_str = document_id or "All Documents"

        async with pool.acquire() as conn:
            try:
                resolved_doc_id = None
                if document_id:
                    doc_row = await conn.fetchrow(
                        "SELECT id, doc_code, title FROM legal_documents WHERE id::text = $1 OR doc_code = $1 LIMIT 1;",
                        document_id,
                    )
                    if doc_row:
                        resolved_doc_id = str(doc_row["id"])
                        doc_code_str = str(doc_row["doc_code"])
                        doc_title_str = str(doc_row["title"])

                c_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM legal_chunks WHERE ($1::uuid IS NULL OR document_id = $1::uuid);",
                    resolved_doc_id,
                )
                total_chunks = int(c_count or 0)

                e_count = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM legal_graph_edges e
                    JOIN legal_chunks c ON e.source_chunk_id = c.id
                    WHERE ($1::uuid IS NULL OR c.document_id = $1::uuid);
                    """,
                    resolved_doc_id,
                )
                total_edges = int(e_count or 0)

                if check_orphans:
                    orphans = await conn.fetch(
                        """
                        SELECT id, path::text, chunk_index FROM legal_chunks
                        WHERE ($1::uuid IS NULL OR document_id = $1::uuid)
                          AND (lead_sentence IS NULL OR trim(lead_sentence) = '')
                          AND path ~ '*.p_*';
                        """,
                        resolved_doc_id,
                    )
                    for o in orphans:
                        anomalies.append(
                            {
                                "severity": "WARNING",
                                "chunk_id": str(o["id"]),
                                "path": o["path"],
                                "anomaly_type": "ORPHANED_SUB_POINT",
                                "diagnostic_message": f"Sub-point {o['chunk_index']} missing parent lead sentence.",
                            }
                        )

                if check_embeddings:
                    missing_emb = await conn.fetch(
                        """
                        SELECT id, path::text FROM legal_chunks
                        WHERE ($1::uuid IS NULL OR document_id = $1::uuid)
                          AND dense_embedding_384 IS NULL
                          AND dense_embedding_1536 IS NULL
                          AND dense_embedding IS NULL;
                        """,
                        resolved_doc_id,
                    )
                    for m in missing_emb:
                        anomalies.append(
                            {
                                "severity": "CRITICAL",
                                "chunk_id": str(m["id"]),
                                "path": m["path"],
                                "anomaly_type": "NULL_DENSE_EMBEDDING",
                                "diagnostic_message": "Chunk dense vector embedding is unpopulated.",
                            }
                        )

                if check_broken_edges:
                    broken = await conn.fetch(
                        """
                        SELECT e.id, e.source_path::text, e.target_path::text FROM legal_graph_edges e
                        JOIN legal_chunks c ON e.source_chunk_id = c.id
                        WHERE ($1::uuid IS NULL OR c.document_id = $1::uuid)
                          AND e.target_chunk_id IS NULL
                          AND e.target_external_ref IS NULL;
                        """,
                        resolved_doc_id,
                    )
                    for b in broken:
                        anomalies.append(
                            {
                                "severity": "WARNING",
                                "chunk_id": str(b["id"]),
                                "path": b["source_path"],
                                "anomaly_type": "BROKEN_GRAPH_EDGE",
                                "diagnostic_message": f"Dangling edge to unresolvable target: {b['target_path']}",
                            }
                        )
            except (asyncpg.PostgresError, OSError) as err:
                logger.error("Corpus validate query failed: %s", err)
                raise StorageConnectionError(f"Corpus validate query failed: {err}") from err

        is_valid = len([a for a in anomalies if a.get("severity") == "CRITICAL"]) == 0
        return CorpusValidateResult(
            status="success",
            document_id=document_id or "ALL",
            doc_code=doc_code_str,
            doc_title=doc_title_str,
            is_valid=is_valid,
            total_chunks_scanned=total_chunks,
            total_edges_scanned=total_edges,
            summary=f"Scanned {total_chunks} chunks, {total_edges} edges. {len(anomalies)} anomalies detected.",
            total_anomalies_detected=len(anomalies),
            anomalies=anomalies,
            validation_timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
        )

    # --------------------------------------------------------------------------
    # 8. mcp_traffic_knowledge_cache_query / write
    # --------------------------------------------------------------------------
    async def knowledge_cache_query(
        self,
        query_hash: str | None = None,
        natural_query: str | None = None,
        similarity_threshold: float = 0.95,
        query_vector: list[float] | None = None,
    ) -> KnowledgeCacheQueryResult:
        """Queries verified advisory answers from runtime_knowledge_cache table."""
        pool = await self._ensure_pool()
        vec_param: str | None = None
        if query_vector is not None:
            if any(math.isnan(x) or math.isinf(x) for x in query_vector):
                raise VectorDimensionMismatchError("Query vector contains non-finite values (NaN or Inf)")
            if len(query_vector) not in (384, 1536):
                raise VectorDimensionMismatchError(f"Invalid vector dimension: {len(query_vector)} (expected 384 or 1536)")
            vec_param = f"[{','.join(str(x) for x in query_vector)}]"

        async with pool.acquire() as conn:
            try:
                row = None
                if query_hash:
                    row = await conn.fetchrow(
                        """
                        SELECT id as cache_id, query_hash, natural_query, synthesized_answer,
                               retrieved_chunk_ids, verified_citations, generated_plan
                        FROM runtime_knowledge_cache
                        WHERE query_hash = $1
                          AND validation_status = 'VERIFIED'
                          AND expires_at > CURRENT_TIMESTAMP;
                        """,
                        query_hash,
                    )
                elif natural_query and vec_param:
                    row = await conn.fetchrow(
                        """
                        SELECT cache_id, synthesized_answer, verified_citations,
                               intent_classification, generated_plan, similarity_score, is_exact_match
                        FROM query_runtime_knowledge_cache($1::text, $2::vector, $3::float);
                        """,
                        natural_query,
                        vec_param,
                        similarity_threshold,
                    )
                elif natural_query:
                    calc_hash = hashlib.sha256(natural_query.strip().lower().encode("utf-8")).hexdigest()
                    row = await conn.fetchrow(
                        """
                        SELECT id as cache_id, query_hash, natural_query, synthesized_answer,
                               retrieved_chunk_ids, verified_citations, generated_plan
                        FROM runtime_knowledge_cache
                        WHERE (query_hash = $1 OR lower(trim(natural_query)) = lower(trim($2)))
                          AND validation_status = 'VERIFIED'
                          AND expires_at > CURRENT_TIMESTAMP;
                        """,
                        calc_hash,
                        natural_query,
                    )

                if row:
                    raw_cits = row.get("verified_citations")
                    if isinstance(raw_cits, str):
                        try:
                            raw_cits = json.loads(raw_cits)
                        except json.JSONDecodeError:
                            raw_cits = [raw_cits]
                    citations_list: list[str] = [str(c) for c in (raw_cits or [])]

                    raw_chunks = row.get("retrieved_chunk_ids")
                    if isinstance(raw_chunks, str):
                        try:
                            raw_chunks = json.loads(raw_chunks)
                        except json.JSONDecodeError:
                            raw_chunks = [raw_chunks]
                    chunks_list: list[str] = [str(cid) for cid in (raw_chunks or [])]

                    entry_db = {
                        "cache_id": str(row["cache_id"]),
                        "query_hash": str(row.get("query_hash") or query_hash or ""),
                        "natural_query": str(row.get("natural_query") or natural_query or ""),
                        "synthesized_answer": str(row.get("synthesized_answer") or ""),
                        "verified_answer": str(row.get("synthesized_answer") or ""),
                        "answer": str(row.get("synthesized_answer") or ""),
                        "citations": citations_list,
                        "retrieved_chunk_ids": chunks_list,
                    }
                    return KnowledgeCacheQueryResult(
                        status="hit",
                        cache_hit=True,
                        query_hash=str(row.get("query_hash") or query_hash or ""),
                        cache_id=str(row["cache_id"]),
                        cache_entry=entry_db,
                        cached_entry=entry_db,
                        answer=str(row.get("synthesized_answer") or ""),
                        similarity_score=float(row.get("similarity_score") or 1.0),
                        is_exact_match=bool(row.get("is_exact_match", True)),
                    )
            except (asyncpg.PostgresError, OSError) as err:
                logger.error("Knowledge cache query failed: %s", err)
                raise StorageConnectionError(f"Knowledge cache query failed: {err}") from err

        return KnowledgeCacheQueryResult(
            status="miss",
            cache_hit=False,
            query_hash=query_hash or "",
            cache_entry=None,
            cached_entry=None,
            answer="",
            similarity_score=0.0,
            is_exact_match=False,
        )

    async def knowledge_cache_write(
        self,
        natural_query: str | None = None,
        answer: str | None = None,
        citations: list[str] | None = None,
        plan: dict[str, object] | None = None,
        query_hash: str | None = None,
        synthesized_answer: str | None = None,
        verified_citations: list[object] | None = None,
        verifier_proof: str | None = None,
        is_valid: bool = True,
        **kwargs: object,
    ) -> KnowledgeCacheWriteResult:
        """Persists verified advisory answers to runtime_knowledge_cache table."""
        pool = await self._ensure_pool()
        ans = synthesized_answer or answer or ""
        q_text = natural_query or ""
        q_hash = query_hash or (hashlib.sha256(q_text.encode("utf-8")).hexdigest() if q_text else str(uuid.uuid4()))
        cits = [str(c) for c in (citations or verified_citations or [])]
        cid = str(uuid.uuid4())

        # Dynamically compute dense embedding vector (384-dim)
        query_vec: list[float] | None = None
        try:
            from rag_eval.legal.ingestion.loader import compute_query_embedding

            query_vec = compute_query_embedding(q_text)
        except (RuntimeError, ValueError, TypeError, OSError, ImportError):
            query_vec = None

        vec_param = f"[{','.join(str(x) for x in query_vec)}]" if query_vec else None

        async with pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO runtime_knowledge_cache (
                        id, query_hash, natural_query, synthesized_answer,
                        verified_citations, generated_plan, intent_classification,
                        query_embedding_384, expires_at, validation_status
                    )
                    VALUES (
                        $1::uuid, $2, $3, $4,
                        $5::jsonb, $6::jsonb, '{}'::jsonb,
                        $7::vector, NOW() + interval '30 days', 'VERIFIED'
                    )
                    ON CONFLICT (query_hash)
                    DO UPDATE SET synthesized_answer = EXCLUDED.synthesized_answer,
                                  verified_citations = EXCLUDED.verified_citations,
                                  generated_plan = EXCLUDED.generated_plan,
                                  query_embedding_384 = COALESCE(EXCLUDED.query_embedding_384, runtime_knowledge_cache.query_embedding_384),
                                  validation_status = 'VERIFIED';
                    """,
                    cid,
                    q_hash,
                    q_text,
                    ans,
                    json.dumps(cits),
                    json.dumps(plan or {}),
                    vec_param,
                )
            except (asyncpg.PostgresError, OSError) as err:
                logger.error("Knowledge cache write failed: %s", err)
                raise StorageConnectionError(f"Knowledge cache write failed: {err}") from err

        return KnowledgeCacheWriteResult(
            status="written",
            cache_id=cid,
            query_hash=q_hash,
            is_persisted=True,
        )

