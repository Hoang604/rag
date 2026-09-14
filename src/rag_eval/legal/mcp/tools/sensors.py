"""PostgreSQL runtime sensor tools executing legal queries, RRF search, and graph traversals."""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import Any

import asyncpg

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.mcp.tools.embedder import QueryEmbedder
from rag_eval.legal.mcp.tools.schemas import (
    CorpusValidateResult,
    GraphEdgeWriteResult,
    GraphTraversalStep,
    GraphTraverseResult,
    HierarchicalNavigateResult,
    HierarchyNode,
    HybridSearchResult,
    SearchHit,
    VerbatimGrepResult,
    extract_metadata_dict,
)
from rag_eval.legal.schemas import (
    E_AST_GROUNDING_VALIDATION,
    E_INVALID_DOCUMENT_HIERARCHY,
    E_STORAGE_CONNECTION,
    LegalDomainError,
    get_vietnam_today,
    parse_flexible_date,
    validate_ltree_path,
)

logger = logging.getLogger(__name__)


class LegalRuntimeSensors:
    """Encapsulates production database sensors (RRF search, verbatim grep, ltree hierarchy, CTE graph)."""

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        embedding_engine: QueryEmbedder | None = None,
    ) -> None:
        self._pool = pool
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

    async def _embed_query(self, query: str) -> list[float] | None:
        if self._embedding_engine is None:
            logger.warning(
                "No query embedder configured; hybrid_search is running sparse-only"
            )
            return None
        try:
            return await self._embedding_engine.embed_query(query)
        except (RuntimeError, ValueError, TypeError, OSError, AttributeError) as exc:
            logger.warning("Query embedding failed, falling back to sparse-only: %s", exc)
            return None

    async def build_dynamic_corpus_manifest(
        self,
        as_of_date: datetime.date | None = None,
    ) -> str:
        """Dynamically constructs a Markdown manifest of legal documents, their validity status, and modification lineages."""
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

    async def hybrid_search(
        self,
        query: str,
        temporal_violation_date: str | None = None,
        limit: int = 10,
    ) -> HybridSearchResult:
        pool = await self._get_pool()
        t_date = get_vietnam_today()
        if temporal_violation_date:
            parsed_d = parse_flexible_date(temporal_violation_date)
            if parsed_d is not None:
                t_date = parsed_d

        computed_vector = await self._embed_query(query)
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
                        metadata=extract_metadata_dict(r["metadata"]),
                        effective_date=str(r["effective_date"]),
                        expiration_date=str(r["expiration_date"]) if r["expiration_date"] else None,
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

    async def verbatim_grep(
        self,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        temporal_violation_date: str | None = None,
        limit: int = 20,
    ) -> VerbatimGrepResult:
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
                rows = await conn.fetch(sql, pattern, is_regex, case_sensitive, t_date, limit)
                matches = [
                    SearchHit(
                        chunk_id=str(r["chunk_id"]),
                        doc_code=str(r["doc_code"]),
                        doc_title=str(r["doc_title"]),
                        path=str(r["path"]),
                        verbatim_text=str(r["verbatim_text"]),
                        contextualized_text=str(r["contextualized_text"]),
                        metadata=extract_metadata_dict(r["metadata"]),
                        effective_date=str(r["effective_date"]),
                        expiration_date=str(r["expiration_date"]) if r["expiration_date"] else None,
                        score=float(r["similarity_score"]),
                    )
                    for r in rows
                ]
                total = await conn.fetchval(
                    "SELECT verbatim_grep_count($1, NULL, $2::boolean, $3::boolean, $4::date);",
                    pattern,
                    is_regex,
                    case_sensitive,
                    t_date,
                )
                total_matches = int(total) if total is not None else len(matches)
                return VerbatimGrepResult(
                    pattern=pattern,
                    is_regex=is_regex,
                    total_matches=total_matches,
                    returned=len(matches),
                    truncated=total_matches > len(matches),
                    matches=matches,
                )
        except (OSError, RuntimeError, asyncpg.PostgresError, TypeError, ValueError) as exc:
            logger.error("verbatim_grep failed: %s", exc)
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=f"Verbatim grep execution error: {exc}",
            ) from exc

    async def hierarchical_navigate(
        self,
        path: str | None = None,
        chunk_id: str | None = None,
        direction: str = "FULL_ARTICLE",
    ) -> HierarchicalNavigateResult:
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
                    metadata=extract_metadata_dict(r["metadata"]),
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

    async def graph_traverse(
        self,
        source_chunk_id: str,
        direction: str = "OUTGOING",
        max_depth: int = 2,
    ) -> GraphTraverseResult:
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
                    target_chunk_id=str(r["target_chunk_id"]) if r["target_chunk_id"] else None,
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

    async def graph_edge_write(
        self,
        source_chunk_id: str,
        relation_type: str,
        target_chunk_id: str | None = None,
        target_external_ref: str | None = None,
        citation_text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GraphEdgeWriteResult:
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

    async def corpus_validate(self) -> CorpusValidateResult:
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
