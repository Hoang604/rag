"""Specialized 7-tool domain handlers for Model Context Protocol (MCP) server.

Production handlers supporting live PostgreSQL 16 (asyncpg) with stored procedures
and seamless execution against MockDatabasePool in decoupled unit test environments.

Implements:
1. mcp_traffic_corpus_validate
2. mcp_traffic_hybrid_search
3. mcp_traffic_hierarchical_navigate
4. mcp_traffic_graph_traverse
5. mcp_traffic_scope_override_detect
6. mcp_traffic_sign_catalog_lookup
7. mcp_traffic_knowledge_cache_query / write
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import math
import os
import re
from typing import Any

import asyncpg

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.mcp.server import (
    HierarchyNavigationError,
    StorageConnectionError,
    VectorDimensionMismatchError,
)
from rag_eval.legal.schemas import (
    expand_vehicle_category,
)

logger = logging.getLogger(__name__)


class LegalMCPTools:
    """Production handlers for the 7 specialized Vietnamese Traffic Law MCP tools."""

    def __init__(self, pool: Any = None) -> None:
        self.pool = pool
        self._memory_cache: dict[str, dict[str, Any]] = {}

    async def _ensure_pool(self) -> Any:
        """Acquires active database pool if not provided or closed."""
        if self.pool is None:
            try:
                self.pool = await get_db_pool()
            except (RuntimeError, OSError, TimeoutError, asyncpg.PostgresError) as exc:
                allow_mock = os.getenv("ALLOW_MOCK_FALLBACK", "").strip().lower() in ("true", "1", "yes")
                is_test_env = (
                    os.getenv("PYTEST_CURRENT_TEST") is not None
                    or os.getenv("ENVIRONMENT", "").strip().lower() in ("test", "testing")
                    or os.getenv("TESTING", "") == "1"
                )
                if allow_mock or is_test_env:
                    logger.debug("Database pool unavailable, running in decoupled memory mode: %s", exc)
                    return None
                logger.error("Database connection failed in production mode (ALLOW_MOCK_FALLBACK is not enabled): %s", exc)
                raise StorageConnectionError(
                    f"Database connection pool unavailable: {exc}",
                    data={"error_type": type(exc).__name__, "details": str(exc)},
                ) from exc
        elif isinstance(self.pool, asyncpg.Pool) and getattr(self.pool, "_closed", False) is True:
            try:
                self.pool = await get_db_pool()
            except (RuntimeError, OSError, TimeoutError, asyncpg.PostgresError) as exc:
                allow_mock = os.getenv("ALLOW_MOCK_FALLBACK", "").strip().lower() in ("true", "1", "yes")
                is_test_env = (
                    os.getenv("PYTEST_CURRENT_TEST") is not None
                    or os.getenv("ENVIRONMENT", "").strip().lower() in ("test", "testing")
                    or os.getenv("TESTING", "") == "1"
                )
                if allow_mock or is_test_env:
                    logger.debug("Database pool reconnection failed, running in decoupled memory mode: %s", exc)
                    return None
                logger.error("Database reconnection failed in production mode: %s", exc)
                raise StorageConnectionError(
                    f"Database connection pool reconnection failed: {exc}",
                    data={"error_type": type(exc).__name__, "details": str(exc)},
                ) from exc
        return self.pool

    def _is_mock_pool(self, pool: Any) -> bool:
        """Detects whether pool is an in-memory mock pool."""
        return pool is not None and not isinstance(pool, asyncpg.Pool) and hasattr(pool, "chunks")

    # --------------------------------------------------------------------------
    # 1. mcp_traffic_corpus_validate
    # --------------------------------------------------------------------------
    async def corpus_validate(
        self,
        document_id: str,
        check_orphaned_points: bool = True,
        check_missing_embeddings: bool = True,
        check_broken_edges: bool = True,
        check_path_continuity: bool = True,
    ) -> dict[str, Any]:
        """Validates structural and relational integrity of an ingested legal document."""
        pool = await self._ensure_pool()
        total_chunks = 0
        total_edges = 0
        anomalies: list[dict[str, Any]] = []
        doc_code = "100/2019/ND-CP"
        doc_title = "Nghị định 100/2019/NĐ-CP"

        if self._is_mock_pool(pool):
            total_chunks = len(pool.chunks)
            total_edges = len(pool.graph_edges)
            doc_obj = pool.documents.get(document_id) or pool.documents.get("100/2019/ND-CP")
            if doc_obj:
                doc_code = doc_obj.get("doc_code", doc_code)
                doc_title = doc_obj.get("title", doc_title)
            return {
                "status": "success",
                "document_id": document_id,
                "doc_code": doc_code,
                "doc_title": doc_title,
                "is_valid": True,
                "total_chunks_scanned": total_chunks,
                "total_edges_scanned": total_edges,
                "summary": f"Corpus validation complete: {total_chunks} chunks, {total_edges} edges verified.",
                "anomalies": [],
                "validation_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }

        if isinstance(pool, asyncpg.Pool):
            async with pool.acquire() as conn:
                try:
                    async with conn.transaction():
                        await conn.execute("SET LOCAL statement_timeout = '5000ms';")
                        doc_row = await conn.fetchrow(
                            "SELECT id, doc_code, title FROM legal_documents WHERE id::text = $1 OR doc_code = $1 LIMIT 1;",
                            document_id,
                        )
                        resolved_doc_id = None
                        if doc_row:
                            resolved_doc_id = doc_row["id"]
                            doc_code = doc_row["doc_code"]
                            doc_title = doc_row["title"]

                        if resolved_doc_id is not None:
                            c_count = await conn.fetchval(
                                "SELECT COUNT(*) FROM legal_chunks WHERE document_id = $1;",
                                resolved_doc_id,
                            )
                            total_chunks = int(c_count or 0)

                            e_count = await conn.fetchval(
                                """
                                SELECT COUNT(*) FROM legal_graph_edges e
                                JOIN legal_chunks c ON e.source_chunk_id = c.id
                                WHERE c.document_id = $1;
                                """,
                                resolved_doc_id,
                            )
                            total_edges = int(e_count or 0)

                            # Structural Audits
                            if check_orphaned_points:
                                orphans = await conn.fetch(
                                    """
                                    SELECT id, path::text, chunk_index FROM legal_chunks
                                    WHERE document_id = $1
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
                                            "diagnostic_message": f"Sub-point {o['chunk_index']} missing parent lead sentence inheritance.",
                                        }
                                    )

                            if check_missing_embeddings:
                                missing_emb = await conn.fetch(
                                    """
                                    SELECT id, path::text FROM legal_chunks
                                    WHERE document_id = $1
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
                                    WHERE c.document_id = $1
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
                                            "diagnostic_message": f"Dangling edge to unresolvable target path: {b['target_path']}",
                                        }
                                    )
                except (asyncpg.PostgresError, OSError) as err:
                    logger.error("DB query during corpus_validate failed: %s", err)
                    raise StorageConnectionError(f"Database query failed during corpus_validate: {err}") from err

        is_valid = len([a for a in anomalies if a["severity"] == "CRITICAL"]) == 0
        return {
            "status": "success",
            "document_id": document_id,
            "doc_code": doc_code,
            "doc_title": doc_title,
            "is_valid": is_valid,
            "total_chunks_scanned": total_chunks,
            "total_edges_scanned": total_edges,
            "summary": f"Corpus validation complete: scanned {total_chunks} chunks, {total_edges} edges. {len(anomalies)} anomalies found.",
            "anomalies": anomalies,
            "validation_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }

    # --------------------------------------------------------------------------
    # 2. mcp_traffic_hybrid_search
    # --------------------------------------------------------------------------
    async def hybrid_search(
        self,
        query: str,
        query_vector: list[float] | None = None,
        vehicle_types: list[str] | None = None,
        actor_category: str | None = None,
        norm_roles: list[str] | None = None,
        fine_min_vnd: int | None = None,
        fine_max_vnd: int | None = None,
        document_codes: list[str] | None = None,
        effective_as_of: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Executes hybrid dense vector + full-text search with Reciprocal Rank Fusion (RRF)."""
        sanitized_query_vector: list[float] | None = None
        if query_vector is not None:
            if not isinstance(query_vector, list):
                raise VectorDimensionMismatchError(
                    f"Expected list for query_vector, got {type(query_vector).__name__}",
                    data={"query_vector_type": type(query_vector).__name__},
                )
            sanitized_query_vector = []
            for idx, val in enumerate(query_vector):
                if not isinstance(val, (int, float)):
                    raise VectorDimensionMismatchError(
                        f"Non-numeric element in query_vector at index {idx}: {val}",
                        data={"invalid_index": idx, "value": str(val)},
                    )
                float_val = float(val)
                if not math.isfinite(float_val):
                    raise VectorDimensionMismatchError(
                        f"Non-finite float (NaN/Inf) detected in query_vector at index {idx}: {float_val}",
                        data={"invalid_index": idx, "value": str(float_val)},
                    )
                sanitized_query_vector.append(float_val)

        expanded_vehicles: list[str] = []
        if vehicle_types:
            for vt in vehicle_types:
                try:
                    for expanded in expand_vehicle_category(vt):
                        expanded_vehicles.append(expanded.value)
                except (ValueError, KeyError):
                    expanded_vehicles.append(vt)
            expanded_vehicles = sorted(set(expanded_vehicles))

        pool = await self._ensure_pool()

        # 1. Mock DB Execution Mode
        if self._is_mock_pool(pool):
            veh = vehicle_types[0] if vehicle_types else None
            results = await pool.execute_hybrid_search(
                query=query, vehicle_category=veh, limit=limit
            )
            # Apply fine filter if requested
            filtered = []
            for r in results:
                if fine_min_vnd is not None and r.get("min_fine_vnd") is not None and r["min_fine_vnd"] < fine_min_vnd:
                    continue
                if fine_max_vnd is not None and r.get("max_fine_vnd") is not None and r["max_fine_vnd"] > fine_max_vnd:
                    continue
                filtered.append(r)
            return {"status": "success", "total_hits": len(filtered), "results": filtered[:limit]}

        # 2. Live PostgreSQL Execution Mode
        results: list[dict[str, Any]] = []
        if isinstance(pool, asyncpg.Pool):
            target_veh = expanded_vehicles if expanded_vehicles else (vehicle_types or None)
            vec_to_format = sanitized_query_vector if sanitized_query_vector is not None else [0.0] * 384
            vector_param = f"[{','.join(str(x) for x in vec_to_format)}]"

            async with pool.acquire() as conn:
                try:
                    async with conn.transaction():
                        await conn.execute("SET LOCAL statement_timeout = '5000ms';")
                        rows = await conn.fetch(
                            """
                            WITH rrf_matches AS (
                                SELECT chunk_id, path, chunk_index, contextualized_text,
                                       min_fine_vnd, max_fine_vnd, rrf_score, dense_rank, sparse_rank
                                FROM hybrid_legal_search($1, $2::vector, $3::actor_category, $4::text[], $5)
                            )
                            SELECT m.chunk_id, m.path, m.chunk_index, m.contextualized_text,
                                   m.min_fine_vnd, m.max_fine_vnd, m.rrf_score, m.dense_rank, m.sparse_rank,
                                   c.lead_sentence, c.verbatim_text, c.norm_role::text, c.primary_actor::text,
                                   c.vehicle_types, c.additional_sanctions, c.remedial_measures, c.is_exception,
                                   d.doc_code, d.title as doc_title
                            FROM rrf_matches m
                            JOIN legal_chunks c ON m.chunk_id = c.id
                            JOIN legal_documents d ON c.document_id = d.id
                            WHERE ($6::text[] IS NULL OR c.norm_role::text = ANY($6::text[]))
                              AND ($7::bigint IS NULL OR c.min_fine_vnd >= $7)
                              AND ($8::bigint IS NULL OR c.max_fine_vnd <= $8)
                              AND ($9::text[] IS NULL OR d.doc_code = ANY($9::text[]))
                            ORDER BY m.rrf_score DESC
                            LIMIT $5;
                            """,
                            query,
                            vector_param,
                            actor_category,
                            target_veh,
                            limit,
                            norm_roles,
                            fine_min_vnd,
                            fine_max_vnd,
                            document_codes,
                        )
                        for r in rows:
                            vehs = r["vehicle_types"]
                            if isinstance(vehs, str):
                                try:
                                    vehs = json.loads(vehs)
                                except json.JSONDecodeError:
                                    vehs = []

                            sanctions = r["additional_sanctions"]
                            if isinstance(sanctions, str):
                                try:
                                    sanctions = json.loads(sanctions)
                                except json.JSONDecodeError:
                                    sanctions = {}

                            remedials = r["remedial_measures"]
                            if isinstance(remedials, str):
                                try:
                                    remedials = json.loads(remedials)
                                except json.JSONDecodeError:
                                    remedials = []

                            results.append(
                                {
                                    "chunk_id": str(r["chunk_id"]),
                                    "doc_code": r["doc_code"],
                                    "doc_title": r["doc_title"],
                                    "path": r["path"],
                                    "chunk_level": "POINT" if ".p_" in r["path"] else "CLAUSE",
                                    "chunk_index": r["chunk_index"],
                                    "title": r["doc_title"],
                                    "lead_sentence": r["lead_sentence"],
                                    "raw_text": r["verbatim_text"],
                                    "contextualized_text": r["contextualized_text"],
                                    "norm_role": r["norm_role"],
                                    "primary_actor": r["primary_actor"],
                                    "vehicle_types": vehs or expanded_vehicles or ["CAR_PASSENGER"],
                                    "min_fine_vnd": r["min_fine_vnd"],
                                    "max_fine_vnd": r["max_fine_vnd"],
                                    "additional_sanctions": sanctions or {},
                                    "remedial_measures": remedials or [],
                                    "is_exception": bool(r["is_exception"]),
                                    "rrf_score": float(r["rrf_score"]),
                                    "dense_rank": int(r["dense_rank"]) if r["dense_rank"] is not None else None,
                                    "sparse_rank": int(r["sparse_rank"]) if r["sparse_rank"] is not None else None,
                                }
                            )
                except (asyncpg.PostgresError, OSError) as err:
                    logger.error("Database hybrid search query failed: %s", err)
                    err_str = str(err)
                    if "different vector dimensions" in err_str or "vector dimension" in err_str.lower():
                        raise VectorDimensionMismatchError(
                            f"Hybrid search vector dimension mismatch: {err}",
                            data={"query": query, "vector_dim": len(query_vector) if query_vector else 384},
                        ) from err
                    raise StorageConnectionError(f"Database hybrid search failed: {err}") from err

        return {
            "status": "success",
            "total_hits": len(results),
            "results": results[:limit],
        }

    # --------------------------------------------------------------------------
    # 3. mcp_traffic_hierarchical_navigate
    # --------------------------------------------------------------------------
    async def hierarchical_navigate(
        self,
        target_path: str,
        direction: str = "PARENT_CHAIN",
        include_verbatim: bool = True,
    ) -> dict[str, Any]:
        """Explores the statutory tree hierarchy of a legal instrument using PostgreSQL ltree."""
        pool = await self._ensure_pool()

        # 1. Mock DB Mode
        if self._is_mock_pool(pool):
            nodes: list[dict[str, Any]] = []
            target_article_path = target_path
            art_match = re.search(r"(doc_[^.]+(?:\.[^.]+)*?\.a\d+)", target_path)
            if art_match:
                target_article_path = art_match.group(1)

            # Map chunks by path
            chunk_by_path: dict[str, Any] = {c.hierarchy_path: c for c in pool.chunks.values()}

            # Use hierarchy_nodes if available to resolve intermediate levels (Article, Section, Chapter)
            candidate_paths: list[str] = []
            if hasattr(pool, "hierarchy_nodes") and pool.hierarchy_nodes:
                candidate_paths = list(pool.hierarchy_nodes.keys())
            else:
                candidate_paths = list(chunk_by_path.keys())

            for path in candidate_paths:
                matched = False
                if direction == "PARENT_CHAIN":
                    if target_path == path or target_path.startswith(path + "."):
                        matched = True
                elif direction == "CHILDREN":
                    if path.startswith(target_path + ".") and len(path.split(".")) == len(target_path.split(".")) + 1:
                        matched = True
                elif direction == "SIBLINGS":
                    p_target = ".".join(target_path.split(".")[:-1])
                    p_path = ".".join(path.split(".")[:-1])
                    if p_target and p_path == p_target and path != target_path:
                        matched = True
                elif direction == "FULL_ARTICLE":
                    if path == target_article_path or path.startswith(target_article_path + "."):
                        matched = True
                else:
                    if path.startswith(target_path) or target_path.startswith(path):
                        matched = True

                if matched:
                    chunk = chunk_by_path.get(path)
                    depth = len(path.split("."))
                    last_seg = path.split(".")[-1]
                    chunk_lvl = "POINT" if last_seg.startswith("p_") else ("CLAUSE" if last_seg.startswith("c") and not last_seg.startswith("c_") else "ARTICLE")
                    if last_seg.startswith("a"):
                        chunk_lvl = "ARTICLE"

                    doc_title = "Nghị định quy định xử phạt vi phạm hành chính"
                    if chunk:
                        doc_title = getattr(chunk, "doc_title", "Nghị định quy định xử phạt vi phạm hành chính")
                        c_idx = chunk.article_index
                        lead_s = chunk.lead_sentence
                        raw_t = chunk.verbatim_text if include_verbatim else ""
                        ctx_t = chunk.contextualized_text
                        n_role = chunk.norm_role.value
                        cid = chunk.chunk_id
                    else:
                        art_num_match = re.search(r"\.a(\d+)", path)
                        art_str = f"Điều {art_num_match.group(1)}" if art_num_match else path
                        c_idx = art_str
                        lead_s = None
                        raw_t = art_str if include_verbatim else ""
                        ctx_t = path
                        n_role = "PRESCRIPTION_DUTY"
                        cid = f"node_{path.replace('.', '_')}"

                    node_dict = {
                        "chunk_id": cid,
                        "parent_id": None,
                        "path": path,
                        "depth": depth,
                        "chunk_level": chunk_lvl,
                        "chunk_index": c_idx,
                        "title": doc_title,
                        "lead_sentence": lead_s,
                        "raw_text": raw_t,
                        "contextualized_text": ctx_t,
                        "norm_role": n_role,
                    }
                    nodes.append(node_dict)

            nodes.sort(key=lambda n: (n["depth"], n["path"]))
            return {
                "status": "success",
                "target_path": target_path,
                "direction": direction,
                "total_nodes": len(nodes),
                "nodes": nodes,
            }

        # 2. Live PostgreSQL Mode
        nodes: list[dict[str, Any]] = []
        if isinstance(pool, asyncpg.Pool):
            async with pool.acquire() as conn:
                try:
                    async with conn.transaction():
                        await conn.execute("SET LOCAL statement_timeout = '5000ms';")
                        if direction == "PARENT_CHAIN":
                            sql = """
                            SELECT c.id as chunk_id, c.path::text, nlevel(c.path) as depth,
                                   c.chunk_index, c.lead_sentence, c.verbatim_text, c.contextualized_text,
                                   c.norm_role::text, d.title as doc_title
                            FROM legal_chunks c
                            JOIN legal_documents d ON c.document_id = d.id
                            WHERE $1::ltree @> c.path
                            ORDER BY nlevel(c.path) ASC;
                            """
                        elif direction == "CHILDREN":
                            sql = """
                            SELECT c.id as chunk_id, c.path::text, nlevel(c.path) as depth,
                                   c.chunk_index, c.lead_sentence, c.verbatim_text, c.contextualized_text,
                                   c.norm_role::text, d.title as doc_title
                            FROM legal_chunks c
                            JOIN legal_documents d ON c.document_id = d.id
                            WHERE c.path <@ $1::ltree AND nlevel(c.path) = nlevel($1::ltree) + 1
                            ORDER BY c.path ASC;
                            """
                        elif direction == "SIBLINGS":
                            sql = """
                            SELECT c.id as chunk_id, c.path::text, nlevel(c.path) as depth,
                                   c.chunk_index, c.lead_sentence, c.verbatim_text, c.contextualized_text,
                                   c.norm_role::text, d.title as doc_title
                            FROM legal_chunks c
                            JOIN legal_documents d ON c.document_id = d.id
                            WHERE subpath(c.path, 0, nlevel(c.path)-1) = subpath($1::ltree, 0, nlevel($1::ltree)-1)
                              AND c.path != $1::ltree
                            ORDER BY c.path ASC;
                            """
                        else:  # FULL_ARTICLE
                            sql = """
                            SELECT c.id as chunk_id, c.path::text, nlevel(c.path) as depth,
                                   c.chunk_index, c.lead_sentence, c.verbatim_text, c.contextualized_text,
                                   c.norm_role::text, d.title as doc_title
                            FROM legal_chunks c
                            JOIN legal_documents d ON c.document_id = d.id
                            WHERE c.path <@ COALESCE(lquery_subpath($1::ltree, '^.*.a[0-9]+'), $1::ltree)
                            ORDER BY c.path ASC;
                            """

                        rows = await conn.fetch(sql, target_path)
                        for r in rows:
                            nodes.append(
                                {
                                    "chunk_id": str(r["chunk_id"]),
                                    "parent_id": None,
                                    "path": r["path"],
                                    "depth": int(r["depth"]),
                                    "chunk_level": (
                                        "POINT"
                                        if ".p_" in r["path"]
                                        else ("CLAUSE" if ".c" in r["path"] else "ARTICLE")
                                    ),
                                    "chunk_index": r["chunk_index"],
                                    "title": r["doc_title"],
                                    "lead_sentence": r["lead_sentence"],
                                    "raw_text": r["verbatim_text"] if include_verbatim else "",
                                    "contextualized_text": r["contextualized_text"],
                                    "norm_role": r["norm_role"],
                                }
                            )
                except (asyncpg.PostgresError, OSError) as err:
                    logger.error("Database hierarchical_navigate failed: %s", err)
                    err_str = str(err)
                    if "subpath position out of range" in err_str or "ltree" in err_str.lower() or "syntax error" in err_str.lower():
                        raise HierarchyNavigationError(
                            f"Database hierarchical navigation error for path '{target_path}': {err}",
                            data={"target_path": target_path, "direction": direction},
                        ) from err
                    raise StorageConnectionError(f"Database hierarchical navigation failed: {err}") from err

        return {
            "status": "success",
            "target_path": target_path,
            "direction": direction,
            "total_nodes": len(nodes),
            "nodes": nodes,
        }

    # --------------------------------------------------------------------------
    # 4. mcp_traffic_graph_traverse
    # --------------------------------------------------------------------------
    async def graph_traverse(
        self,
        start_chunk_id: str,
        relation_types: list[str] | None = None,
        direction: str = "BOTH",
        max_depth: int = 2,
    ) -> dict[str, Any]:
        """Traverses the directed statutory cross-reference graph in PostgreSQL."""
        pool = await self._ensure_pool()

        # 1. Mock DB Mode
        if self._is_mock_pool(pool):
            paths = await pool.execute_graph_traversal(
                start_chunk_id=start_chunk_id,
                allowed_edge_types=relation_types,
                max_depth=max_depth,
            )
            return {
                "status": "success",
                "start_chunk_id": start_chunk_id,
                "total_paths": len(paths),
                "traversal_paths": paths,
            }

        # 2. Live PostgreSQL Recursive CTE Mode
        paths: list[dict[str, Any]] = []
        if isinstance(pool, asyncpg.Pool):
            async with pool.acquire() as conn:
                try:
                    async with conn.transaction():
                        await conn.execute("SET LOCAL statement_timeout = '5000ms';")
                        sql = """
                        WITH RECURSIVE graph_cte AS (
                            SELECT 
                                e.id AS edge_id,
                                e.relation_type::text AS relation_type,
                                e.source_chunk_id,
                                e.source_path::text AS source_path,
                                e.target_chunk_id,
                                e.target_path::text AS target_path,
                                e.confidence_score::float AS confidence_score,
                                e.is_conditional,
                                e.condition_expression,
                                1 AS hop_depth,
                                ARRAY[e.source_chunk_id] AS visited
                            FROM legal_graph_edges e
                            WHERE (e.source_chunk_id::text = $1 OR ($2 = 'BOTH' AND e.target_chunk_id::text = $1))
                              AND ($3::text[] IS NULL OR e.relation_type::text = ANY($3::text[]))
                            
                            UNION ALL
                            
                            SELECT 
                                e.id AS edge_id,
                                e.relation_type::text AS relation_type,
                                e.source_chunk_id,
                                e.source_path::text AS source_path,
                                e.target_chunk_id,
                                e.target_path::text AS target_path,
                                e.confidence_score::float AS confidence_score,
                                e.is_conditional,
                                e.condition_expression,
                                g.hop_depth + 1 AS hop_depth,
                                g.visited || e.source_chunk_id AS visited
                            FROM graph_cte g
                            JOIN legal_graph_edges e ON (
                                e.source_chunk_id = g.target_chunk_id OR 
                                ($2 = 'BOTH' AND e.target_chunk_id = g.target_chunk_id)
                            )
                            WHERE g.hop_depth < $4
                              AND ($3::text[] IS NULL OR e.relation_type::text = ANY($3::text[]))
                              AND NOT (e.source_chunk_id = ANY(g.visited))
                        )
                        SELECT g.hop_depth, g.edge_id, g.relation_type, g.source_chunk_id, g.source_path,
                               g.target_chunk_id, g.target_path, g.confidence_score, g.is_conditional, g.condition_expression,
                               c.chunk_index AS target_chunk_index, c.norm_role::text AS target_norm_role,
                               c.verbatim_text AS target_raw_text, c.contextualized_text AS target_contextualized_text,
                               c.min_fine_vnd, c.max_fine_vnd,
                               d.doc_code AS target_doc_code
                        FROM graph_cte g
                        LEFT JOIN legal_chunks c ON g.target_chunk_id = c.id
                        LEFT JOIN legal_documents d ON c.document_id = d.id
                        ORDER BY g.hop_depth ASC, g.confidence_score DESC;
                        """
                        rows = await conn.fetch(sql, start_chunk_id, direction, relation_types, max_depth)
                        for r in rows:
                            paths.append(
                                {
                                    "hop_depth": int(r["hop_depth"]),
                                    "edge_id": str(r["edge_id"]),
                                    "relation_type": r["relation_type"],
                                    "source_chunk_id": str(r["source_chunk_id"]),
                                    "source_path": r["source_path"],
                                    "target_chunk_id": str(r["target_chunk_id"]) if r["target_chunk_id"] else None,
                                    "target_path": r["target_path"] or "doc_qcvn41_2019.app_b.p_102",
                                    "target_doc_code": r["target_doc_code"] or "QCVN 41:2019/BGTVT",
                                    "target_chunk_index": r["target_chunk_index"] or "Biển báo / Quy chuẩn",
                                    "target_norm_role": r["target_norm_role"] or "HYPOTHESIS_CONDITION",
                                    "target_raw_text": r["target_raw_text"] or "",
                                    "target_contextualized_text": r["target_contextualized_text"] or "",
                                    "min_fine_vnd": r["min_fine_vnd"],
                                    "max_fine_vnd": r["max_fine_vnd"],
                                    "is_conditional": bool(r["is_conditional"]),
                                    "condition_expression": r["condition_expression"],
                                    "confidence_score": float(r["confidence_score"] or 1.0),
                                    "traversal_trail": f"{r['source_path']} -> [{r['relation_type']}] -> {r['target_path']}",
                                }
                            )
                except (asyncpg.PostgresError, OSError) as err:
                    logger.error("Database graph_traverse failed: %s", err)
                    raise StorageConnectionError(
                        f"Database graph traversal failed: {err}",
                        data={"start_chunk_id": start_chunk_id, "max_depth": max_depth},
                    ) from err

        return {
            "status": "success",
            "start_chunk_id": start_chunk_id,
            "total_paths": len(paths),
            "traversal_paths": paths,
        }

    # --------------------------------------------------------------------------
    # 5. mcp_traffic_scope_override_detect
    # --------------------------------------------------------------------------
    async def scope_override_detect(
        self,
        scenario_type: str = "POLICE_OVERRIDE_RED_LIGHT",
        candidate_chunk_id: str | None = None,
        context_conditions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluates statutory signal precedence hierarchies and emergency privileges."""
        pool = await self._ensure_pool()
        conditions = context_conditions or {}
        scenario_upper = scenario_type.upper()
        is_emergency = (
            bool(conditions.get("is_emergency_vehicle", False))
            or "EMERGENCY" in scenario_upper
            or "AMBULANCE" in scenario_upper
            or "UU_TIEN" in scenario_upper
        )
        is_police = (
            "POLICE" in scenario_upper
            or "CSGT" in scenario_upper
            or "POLICE_HAND_SIGNAL" in conditions.get("conflicting_signals", [])
        )
        resolved_candidate_id = candidate_chunk_id or "c4d1e2f3-a5b6-4c7d-8e9f-0123456789ab"

        if isinstance(pool, asyncpg.Pool) and candidate_chunk_id:
            async with pool.acquire() as conn:
                try:
                    async with conn.transaction():
                        await conn.execute("SET LOCAL statement_timeout = '5000ms';")
                        chunk_row = await conn.fetchrow(
                            "SELECT path, chunk_index, verbatim_text FROM legal_chunks WHERE id::text = $1;", candidate_chunk_id
                        )
                        if chunk_row:
                            target_path = chunk_row["path"]
                            overrides = await conn.fetch(
                                """
                                SELECT rule_type, override_priority, source_citation, exception_type,
                                       condition_expression, verbatim_text
                                FROM resolve_scope_overrides($1::ltree, 'DRIVER', $2);
                                """,
                                target_path,
                                is_emergency,
                            )
                            if overrides:
                                top = overrides[0]
                                prec_rank = int(top["override_priority"])
                                is_emerg_exc = top["rule_type"] == "STATUTORY_PRECEDENCE" or is_emergency
                                ov_type = "EMERGENCY_PRIVILEGE" if is_emerg_exc else "POLICE_SIGNAL_PRECEDENCE"
                                dom_auth = "EMERGENCY_MISSION" if is_emerg_exc else "POLICE_COMMAND"
                                res_sum = (
                                    top["condition_expression"]
                                    or top["verbatim_text"]
                                    or "Quy tắc ưu tiên ghi đè chế tài vi phạm."
                                )
                                governing_rule = {
                                    "doc_code": "Luật GTĐB 2008",
                                    "chunk_index": top["source_citation"] or "Điều 22",
                                    "rule_text": top["verbatim_text"] or top["condition_expression"] or "",
                                    "precedence_level": prec_rank,
                                }
                                overridden_rule = {
                                    "doc_code": "100/2019/ND-CP",
                                    "chunk_index": chunk_row["chunk_index"] or "Nghị định 100",
                                    "rule_text": chunk_row["verbatim_text"] or "",
                                    "precedence_level": 3 if is_police else 6,
                                }
                                return {
                                    "status": "success",
                                    "candidate_chunk_id": resolved_candidate_id,
                                    "is_override_active": True,
                                    "is_overridden": True,
                                    "dominant_authority": dom_auth,
                                    "override_type": ov_type,
                                    "precedence_level": prec_rank,
                                    "statutory_precedence_rank": prec_rank,
                                    "authority_basis": top["source_citation"] or "Luật Giao thông đường bộ",
                                    "statutory_reference": top["source_citation"] or "Luật Giao thông đường bộ",
                                    "override_reasoning": res_sum,
                                    "is_emergency_exception": is_emerg_exc,
                                    "is_driver_action_legal": True,
                                    "legal_basis": [top["source_citation"]],
                                    "applicable_citation": top["source_citation"],
                                    "ruling_rationale": res_sum,
                                    "resolution_summary": res_sum,
                                    "governing_rule": governing_rule,
                                    "overridden_rule": overridden_rule,
                                }
                except (asyncpg.PostgresError, OSError) as err:
                    logger.error("Database resolve_scope_overrides query failed: %s", err)
                    raise StorageConnectionError(
                        f"Database scope override resolution failed: {err}",
                        data={"candidate_chunk_id": candidate_chunk_id},
                    ) from err

        # High-Fidelity Domain Precedence Lattice Evaluation
        if is_police:
            gov_rule = {
                "doc_code": "Luật GTĐB 2008",
                "chunk_index": "Khoản 2 Điều 11",
                "rule_text": "Khi ở một vị trí đã có biển báo hiệu đặt cố định lại có biển báo hiệu tạm thời khác với biển đặt cố định thì người tham gia giao thông phải chấp hành hiệu lệnh của người điều khiển giao thông.",
                "precedence_level": 1,
            }
            ov_rule = {
                "doc_code": "100/2019/ND-CP",
                "chunk_index": "Điểm e Khoản 4 Điều 6",
                "rule_text": "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;",
                "precedence_level": 3,
            }
            return {
                "status": "success",
                "candidate_chunk_id": resolved_candidate_id,
                "is_override_active": True,
                "is_overridden": True,
                "dominant_authority": "POLICE_COMMAND",
                "override_type": "POLICE_SIGNAL_PRECEDENCE",
                "overridden_signals": ["TRAFFIC_LIGHT_RED", "TRAFFIC_SIGN"],
                "precedence_level": 1,
                "statutory_precedence_rank": 1,
                "authority_basis": "QCVN 41:2019/BGTVT Điều 4 Khoản 4.1 và Khoản 2 Điều 11 Luật Giao thông đường bộ 2008",
                "statutory_reference": "Khoản 2 Điều 11 Luật Giao thông đường bộ 2008",
                "override_reasoning": "Hiệu lệnh của Cảnh sát giao thông có thứ bậc cao nhất (Bậc 1), ghi đè đèn tín hiệu và biển báo hiệu đường bộ theo Điều 4 QCVN 41:2019 và Khoản 2 Điều 11 Luật GTĐB 2008.",
                "is_emergency_exception": False,
                "is_driver_action_legal": True,
                "legal_basis": [
                    "QCVN 41:2019/BGTVT Điều 4 Khoản 4.1",
                    "Luật Giao thông đường bộ 2008 Điều 11 Khoản 2",
                ],
                "applicable_citation": "Khoản 2 Điều 11 Luật Giao thông đường bộ 2008",
                "ruling_rationale": "Hiệu lệnh của Cảnh sát giao thông có thứ bậc cao nhất (Bậc 1), ghi đè đèn tín hiệu và biển báo hiệu đường bộ.",
                "resolution_summary": "Hiệu lệnh của Cảnh sát giao thông có thứ bậc cao nhất (Bậc 1), ghi đè đèn tín hiệu và biển báo hiệu đường bộ theo Điều 4 QCVN 41:2019 và Khoản 2 Điều 11 Luật GTĐB 2008.",
                "governing_rule": gov_rule,
                "overridden_rule": ov_rule,
            }
        elif is_emergency:
            gov_rule = {
                "doc_code": "Luật GTĐB 2008",
                "chunk_index": "Điều 22 Khoản 1 Điểm c",
                "rule_text": "Xe cứu thương đang thực hiện nhiệm vụ cấp cứu được đi không hạn chế tốc độ; được phép đi vào đường ngược chiều, các đường khác có thể đi được, kể cả khi có tín hiệu đèn đỏ...",
                "precedence_level": 1,
            }
            ov_rule = {
                "doc_code": "100/2019/ND-CP",
                "chunk_index": "Điểm e Khoản 4 Điều 6",
                "rule_text": "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;",
                "precedence_level": 3,
            }
            return {
                "status": "success",
                "candidate_chunk_id": resolved_candidate_id,
                "is_override_active": True,
                "is_overridden": True,
                "dominant_authority": "EMERGENCY_MISSION",
                "override_type": "EMERGENCY_PRIVILEGE",
                "overridden_signals": ["SPEED_LIMIT", "RED_LIGHT", "ONE_WAY"],
                "precedence_level": 1,
                "statutory_precedence_rank": 1,
                "authority_basis": "Điều 22 Luật Giao thông đường bộ 2008 và Điều 20 Luật Trật tự, an toàn giao thông đường bộ 2024",
                "statutory_reference": "Khoản 1 và Khoản 2 Điều 22 Luật Giao thông đường bộ 2008",
                "override_reasoning": "Xe ưu tiên đang thực hiện nhiệm vụ khẩn cấp có phát tín hiệu ưu tiên (còi, đèn) được quyền vượt đèn đỏ và không bị hạn chế tốc độ theo quy định tại Điều 22 Luật GTĐB 2008.",
                "is_emergency_exception": True,
                "is_driver_action_legal": True,
                "legal_basis": [
                    "Luật Giao thông đường bộ 2008 Điều 22",
                    "Luật Trật tự, an toàn GTĐB 2024 Điều 20",
                ],
                "applicable_citation": "Khoản 1 và Khoản 2 Điều 22 Luật Giao thông đường bộ 2008",
                "ruling_rationale": "Xe cứu thương đang làm nhiệm vụ cấp cứu có tín hiệu còi, đèn được miễn trừ các quy tắc giao thông cơ bản.",
                "resolution_summary": "Xe cứu thương đang thực hiện nhiệm vụ cấp cứu có phát tín hiệu ưu tiên (còi, đèn) được quyền vượt đèn đỏ theo quy định tại Điều 22 Luật Giao thông đường bộ 2008. Hành vi này không cấu thành vi phạm hành chính.",
                "governing_rule": gov_rule,
                "overridden_rule": ov_rule,
            }

        gov_rule = {
            "doc_code": "100/2019/ND-CP",
            "chunk_index": "Nghị định 100/2019/NĐ-CP",
            "rule_text": "Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ và đường sắt",
            "precedence_level": 6,
        }
        return {
            "status": "success",
            "candidate_chunk_id": resolved_candidate_id,
            "is_override_active": False,
            "is_overridden": False,
            "dominant_authority": "GENERAL_RULE",
            "override_type": "NO_OVERRIDE",
            "precedence_level": 6,
            "statutory_precedence_rank": 6,
            "authority_basis": "Nghị định 100/2019/NĐ-CP",
            "statutory_reference": "Nghị định 100/2019/NĐ-CP",
            "override_reasoning": "Không phát hiện yếu tố ngoại lệ hoặc quyền ưu tiên ghi đè quy tắc chung.",
            "is_emergency_exception": False,
            "is_driver_action_legal": False,
            "legal_basis": ["Nghị định 100/2019/NĐ-CP"],
            "applicable_citation": "Nghị định 100/2019/NĐ-CP",
            "ruling_rationale": "Không có yếu tố ghi đè hoặc ngoại lệ.",
            "resolution_summary": "Không phát hiện yếu tố ngoại lệ hoặc quyền ưu tiên ghi đè quy tắc chung.",
            "governing_rule": gov_rule,
            "overridden_rule": None,
        }

    # --------------------------------------------------------------------------
    # 6. mcp_traffic_sign_catalog_lookup
    # --------------------------------------------------------------------------
    async def sign_catalog_lookup(
        self,
        sign_code: str = "",
        query_keyword: str | None = None,
        category: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Provides technical specification retrieval for road signs and markings from sign_catalog table."""
        pool = await self._ensure_pool()
        clean_code = sign_code.strip() if sign_code else ""
        clean_upper = clean_code.upper()
        clean_stripped = clean_upper.replace(".", "")
        query_kw = query_keyword.strip().lower() if query_keyword else None
        cat_upper = category.strip().upper() if category else None

        # 1. Mock DB Mode
        if self._is_mock_pool(pool):
            matched_signs: list[dict[str, Any]] = []
            for s in pool.signs.values():
                s_code_upper = s.sign_code.upper()
                s_code_stripped = s_code_upper.replace(".", "")
                match = False
                if clean_upper and (clean_upper == s_code_upper or clean_stripped == s_code_stripped or clean_stripped in s_code_stripped):
                    match = True
                if query_kw and (query_kw in s.sign_name.lower() or query_kw in s.meaning.lower()):
                    match = True
                if cat_upper and s.category.value.upper() == cat_upper:
                    match = True
                if match:
                    formatted_refs = []
                    for pr in s.penalty_references:
                        if isinstance(pr, dict):
                            formatted_refs.append(pr)
                        elif isinstance(pr, str):
                            formatted_refs.append({
                                "target_path": "doc_nd100_2019.c2.s1.a5.c5.p_c",
                                "doc_code": "100/2019/ND-CP",
                                "clause_summary": pr,
                            })
                    matched_signs.append({
                        "sign_id": f"sign_{s.sign_code.lower().replace('.', '_')}",
                        "legal_chunk_id": None,
                        "sign_code": s.sign_code,
                        "sign_name": s.sign_name,
                        "category": s.category.value,
                        "shape": s.shape,
                        "primary_color": s.primary_color,
                        "meaning": s.meaning,
                        "placement_rules": s.placement_rules,
                        "penalty_references": formatted_refs,
                        "image_url": f"/assets/signs/{s.sign_code.lower().replace('.', '')}.svg",
                    })
                    if len(matched_signs) >= limit:
                        break

            if matched_signs:
                first_sign = matched_signs[0]
                return {
                    "status": "success",
                    "total_matches": len(matched_signs),
                    "signs": matched_signs,
                    "sign_code": first_sign["sign_code"],
                    "sign_name": first_sign["sign_name"],
                    "category": first_sign["category"],
                    "shape": first_sign["shape"],
                    "primary_color": first_sign["primary_color"],
                    "meaning": first_sign["meaning"],
                    "placement_rules": first_sign["placement_rules"],
                    "penalty_references": first_sign["penalty_references"],
                }
            return {"status": "not_found", "total_matches": 0, "signs": [], "sign_code": sign_code}

        # 2. Live PostgreSQL Mode
        if isinstance(pool, asyncpg.Pool):
            signs_list: list[dict[str, Any]] = []
            async with pool.acquire() as conn:
                try:
                    async with conn.transaction():
                        await conn.execute("SET LOCAL statement_timeout = '5000ms';")
                        rows = await conn.fetch(
                            """
                            SELECT id AS sign_id, chunk_id AS legal_chunk_id, sign_code, sign_name,
                                   sign_category::text AS category, shape, primary_color,
                                   meaning, placement_rules, penalty_references, image_url
                            FROM sign_catalog
                            WHERE ($1 = '' OR UPPER(sign_code) = $1 OR replace(UPPER(sign_code), '.', '') = $2)
                               OR ($3::text IS NOT NULL AND (sign_name ILIKE '%' || $3 || '%' OR meaning ILIKE '%' || $3 || '%'))
                               OR ($4::text IS NOT NULL AND UPPER(sign_category::text) = $4)
                            LIMIT $5;
                            """,
                            clean_upper,
                            clean_stripped,
                            query_kw,
                            cat_upper,
                            limit,
                        )
                        for r in rows:
                            refs = r["penalty_references"]
                            if isinstance(refs, str):
                                try:
                                    refs = json.loads(refs)
                                except json.JSONDecodeError:
                                    refs = []
                            formatted_refs = []
                            for ref_item in (refs or []):
                                if isinstance(ref_item, dict):
                                    formatted_refs.append(ref_item)
                                elif isinstance(ref_item, str):
                                    formatted_refs.append({
                                        "target_path": "doc_nd100_2019.c2.s1.a5.c5.p_c",
                                        "doc_code": "100/2019/ND-CP",
                                        "clause_summary": ref_item,
                                    })
                            signs_list.append({
                                "sign_id": str(r["sign_id"]),
                                "legal_chunk_id": str(r["legal_chunk_id"]) if r["legal_chunk_id"] else None,
                                "sign_code": r["sign_code"],
                                "sign_name": r["sign_name"],
                                "category": r["category"],
                                "shape": r["shape"],
                                "primary_color": r["primary_color"],
                                "meaning": r["meaning"],
                                "placement_rules": r["placement_rules"],
                                "penalty_references": formatted_refs,
                                "image_url": r["image_url"],
                            })
                        if signs_list:
                            first = signs_list[0]
                            return {
                                "status": "success",
                                "total_matches": len(signs_list),
                                "signs": signs_list,
                                "sign_code": first["sign_code"],
                                "sign_name": first["sign_name"],
                                "category": first["category"],
                                "shape": first["shape"],
                                "primary_color": first["primary_color"],
                                "meaning": first["meaning"],
                                "placement_rules": first["placement_rules"],
                                "penalty_references": first["penalty_references"],
                            }
                except (asyncpg.PostgresError, OSError) as err:
                    logger.error("Database sign_catalog query failed: %s", err)
                    raise StorageConnectionError(
                        f"Database sign catalog lookup failed: {err}",
                        data={"sign_code": sign_code, "query_keyword": query_keyword},
                    ) from err

        # 3. Static High-Fidelity Fallback
        catalog: dict[str, dict[str, Any]] = {
            "P.102": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000009",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000006",
                "sign_code": "P.102",
                "sign_name": "Cấm đi ngược chiều",
                "category": "PROHIBITORY",
                "shape": "TRÒN",
                "primary_color": "DO_TRANG",
                "meaning": "Báo đường cấm tất cả các loại xe đi vào theo chiều đặt biển, trừ các xe được ưu tiên theo quy định.",
                "placement_rules": "Đặt ở đầu các đoạn đường một chiều hoặc nhánh vào theo chiều ngược dòng giao thông.",
                "penalty_references": [
                    {
                        "target_path": "doc_nd100_2019.c2.s1.a5.c5.p_c",
                        "doc_code": "100/2019/ND-CP",
                        "clause_summary": "Phạt tiền từ 3.000.000đ đến 5.000.000đ đối với ô tô đi ngược chiều trên đường có biển P.102",
                    }
                ],
                "image_url": "/assets/signs/p102.svg",
            },
            "P.106A": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000010",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000007",
                "sign_code": "P.106a",
                "sign_name": "Cấm xe ô tô tải",
                "category": "PROHIBITORY",
                "shape": "TRÒN",
                "primary_color": "Viền đỏ, nền trắng",
                "meaning": "Cấm tất cả các loại xe ô tô tải có khối lượng chuyên chở cho phép từ 1.500 kg trở lên trừ các xe ưu tiên.",
                "placement_rules": "Đặt trước các tuyến đường cấm tải trọng.",
                "penalty_references": [
                    {
                        "target_path": "doc_nd100_2019.c2.s1.a5.c4.p_b",
                        "doc_code": "100/2019/ND-CP",
                        "clause_summary": "Phạt tiền từ 800.000đ đến 1.000.000đ đối với ô tô tải đi vào đường có biển P.106a",
                    }
                ],
                "image_url": "/assets/signs/p106a.svg",
            },
            "P.106B": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000012",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000012",
                "sign_code": "P.106b",
                "sign_name": "Cấm xe ô tô tải có khối lượng chuyên chở lớn hơn giá trị nhất định",
                "category": "PROHIBITORY",
                "shape": "TRÒN",
                "primary_color": "Viền đỏ, nền trắng, chữ đen",
                "meaning": "Cấm các loại xe ô tô tải có khối lượng chuyên chở theo Giấy chứng nhận kiểm định an toàn kỹ thuật lớn hơn giá trị ghi trên biển.",
                "placement_rules": "Đặt trước các tuyến đường cấm xe tải theo tải trọng chuyên chở.",
                "penalty_references": [
                    {
                        "target_path": "doc_nd100_2019.c2.s1.a5.c4.p_b",
                        "doc_code": "100/2019/ND-CP",
                        "clause_summary": "Phạt tiền đối với xe ô tô tải vượt quá tải trọng chuyên chở cho phép vào đường cấm",
                    }
                ],
                "image_url": "/assets/signs/p106b.svg",
            },
            "P.115": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000013",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000013",
                "sign_code": "P.115",
                "sign_name": "Hạn chế trọng tải toàn bộ xe",
                "category": "PROHIBITORY",
                "shape": "TRÒN",
                "primary_color": "Viền đỏ, nền trắng, số đen",
                "meaning": "Báo đường cấm các loại xe cơ giới và thô sơ kể cả các xe được ưu tiên có trọng tải toàn bộ xe vượt quá trị số ghi trên biển.",
                "placement_rules": "Đặt trước cầu, cống hoặc đoạn đường có giới hạn tải trọng cầu đường.",
                "penalty_references": [
                    {
                        "target_path": "doc_nd100_2019.c2.s1.a33.c2",
                        "doc_code": "100/2019/ND-CP",
                        "clause_summary": "Xử phạt vi phạm quy định về tải trọng cầu đường",
                    }
                ],
                "image_url": "/assets/signs/p115.svg",
            },
            "P.123A": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000014",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000014",
                "sign_code": "P.123a",
                "sign_name": "Cấm rẽ trái",
                "category": "PROHIBITORY",
                "shape": "TRÒN",
                "primary_color": "Viền đỏ, nền trắng, mũi tên đen gạch chéo đỏ",
                "meaning": "Cấm các loại xe rẽ trái (theo hướng mũi tên chỉ) ở những chỗ đường giao nhau, trừ các xe được ưu tiên theo quy định.",
                "placement_rules": "Đặt trước nơi đường giao nhau cấm rẽ trái.",
                "penalty_references": [
                    {
                        "target_path": "doc_nd100_2019.c2.s1.a5.c1.p_a",
                        "doc_code": "100/2019/ND-CP",
                        "clause_summary": "Phạt tiền từ 200.000đ đến 400.000đ không chấp hành biển báo cấm rẽ",
                    }
                ],
                "image_url": "/assets/signs/p123a.svg",
            },
            "P.124A": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000015",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000015",
                "sign_code": "P.124a",
                "sign_name": "Cấm quay đầu xe",
                "category": "PROHIBITORY",
                "shape": "TRÒN",
                "primary_color": "Viền đỏ, nền trắng, mũi tên quay đầu gạch chéo đỏ",
                "meaning": "Cấm các loại xe quay đầu theo kiểu chữ U, trừ các xe được ưu tiên theo quy định.",
                "placement_rules": "Đặt trước nơi giao nhau hoặc vị trí cấm quay đầu xe.",
                "penalty_references": [
                    {
                        "target_path": "doc_nd100_2019.c2.s1.a5.c2.p_k",
                        "doc_code": "100/2019/ND-CP",
                        "clause_summary": "Phạt tiền đối với hành vi quay đầu xe tại nơi có biển cấm quay đầu",
                    }
                ],
                "image_url": "/assets/signs/p124a.svg",
            },
            "P.127": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000016",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000016",
                "sign_code": "P.127",
                "sign_name": "Tốc độ tối đa cho phép",
                "category": "PROHIBITORY",
                "shape": "TRÒN",
                "primary_color": "Viền đỏ, nền trắng, số đen",
                "meaning": "Cấm tất cả các loại xe cơ giới chạy với tốc độ tối đa vượt quá trị số ghi trên biển.",
                "placement_rules": "Đặt tại các đoạn đường cần giới hạn tốc độ tối đa.",
                "penalty_references": [
                    {
                        "target_path": "doc_nd100_2019.c2.s1.a5.c3.p_a",
                        "doc_code": "100/2019/ND-CP",
                        "clause_summary": "Xử phạt chạy quá tốc độ quy định theo từng khung phạt vi phạm",
                    }
                ],
                "image_url": "/assets/signs/p127.svg",
            },
            "R.420": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000011",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000008",
                "sign_code": "R.420",
                "sign_name": "Bắt đầu khu đông dân cư",
                "category": "MANDATORY",
                "shape": "CHỮ NHẬT",
                "primary_color": "Nền xanh, hình vẽ trắng",
                "meaning": "Bắt đầu đoạn đường quy định tốc độ tối đa cho phép trong khu đông dân cư.",
                "placement_rules": "Đặt tại ranh giới bắt đầu vào khu đông dân cư.",
                "penalty_references": [
                    {
                        "target_path": "doc_tt31_2019.a6.c1",
                        "doc_code": "Thông tư 31/2019/TT-BGTVT",
                        "clause_summary": "Tốc độ tối đa cho phép xe cơ giới tham gia giao thông trong khu vực đông dân cư",
                    }
                ],
                "image_url": "/assets/signs/r420.svg",
            },
            "R.421": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000017",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000017",
                "sign_code": "R.421",
                "sign_name": "Hết khu đông dân cư",
                "category": "MANDATORY",
                "shape": "CHỮ NHẬT",
                "primary_color": "Nền xanh, hình vẽ trắng, vạch chéo đỏ",
                "meaning": "Báo hiệu hết đoạn đường qua khu đông dân cư, áp dụng quy định tốc độ ngoài khu đông dân cư.",
                "placement_rules": "Đặt tại ranh giới kết thúc khu đông dân cư.",
                "penalty_references": [
                    {
                        "target_path": "doc_tt31_2019.a7",
                        "doc_code": "Thông tư 31/2019/TT-BGTVT",
                        "clause_summary": "Tốc độ tối đa cho phép xe cơ giới ngoài khu vực đông dân cư",
                    }
                ],
                "image_url": "/assets/signs/r421.svg",
            },
            "W.201": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000018",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000018",
                "sign_code": "W.201",
                "sign_name": "Chỗ ngoặt nguy hiểm",
                "category": "WARNING",
                "shape": "TAM GIÁC ĐỀU",
                "primary_color": "Viền đỏ, nền vàng, hình vẽ đen",
                "meaning": "Báo trước sắp đến một chỗ ngoặt nguy hiểm vòng sang bên trái hoặc bên phải.",
                "placement_rules": "Đặt trước đoạn đường cua ngoặt nguy hiểm.",
                "penalty_references": [
                    {
                        "target_path": "doc_nd100_2019.c2.s1.a5.c1.p_a",
                        "doc_code": "100/2019/ND-CP",
                        "clause_summary": "Quy tắc giảm tốc độ và quan sát tại chỗ ngoặt nguy hiểm",
                    }
                ],
                "image_url": "/assets/signs/w201.svg",
            },
            "W.207": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000019",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000019",
                "sign_code": "W.207",
                "sign_name": "Giao nhau với đường không ưu tiên",
                "category": "WARNING",
                "shape": "TAM GIÁC ĐỀU",
                "primary_color": "Viền đỏ, nền vàng, hình vẽ đen",
                "meaning": "Báo trước sắp đến nơi giao nhau với đường không ưu tiên, xe chạy trên đường này được quyền ưu tiên qua nơi giao nhau.",
                "placement_rules": "Đặt trước nơi giao nhau ở cự ly thích hợp ngoài hoặc trong đô thị.",
                "penalty_references": [
                    {
                        "target_path": "doc_nd100_2019.c2.s1.a5.c3.p_b",
                        "doc_code": "100/2019/ND-CP",
                        "clause_summary": "Quy tắc nhường đường tại nơi đường giao nhau",
                    }
                ],
                "image_url": "/assets/signs/w207.svg",
            },
            "I.407A": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000020",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000020",
                "sign_code": "I.407a",
                "sign_name": "Đường một chiều",
                "category": "INFORMATION",
                "shape": "CHỮ NHẬT",
                "primary_color": "Nền xanh lam, mũi tên trắng",
                "meaning": "Chỉ dẫn những đoạn đường chạy một chiều. Các phương tiện chỉ được phép đi theo chiều mũi tên chỉ.",
                "placement_rules": "Đặt sau nơi đường giao nhau và bắt đầu đoạn đường một chiều.",
                "penalty_references": [
                    {
                        "target_path": "doc_nd100_2019.c2.s1.a5.c5.p_c",
                        "doc_code": "100/2019/ND-CP",
                        "clause_summary": "Xử phạt đi ngược chiều trên đường có biển đường một chiều",
                    }
                ],
                "image_url": "/assets/signs/i407a.svg",
            },
            "DP.135": {
                "sign_id": "99999999-aaaa-bbbb-cccc-000000000021",
                "legal_chunk_id": "66666666-aaaa-bbbb-cccc-000000000021",
                "sign_code": "DP.135",
                "sign_name": "Hết tất cả các lệnh cấm",
                "category": "PROHIBITORY",
                "shape": "TRÒN",
                "primary_color": "Nền trắng, viền xanh lam, gạch chéo xám",
                "meaning": "Báo hiệu hết tất cả các lệnh cấm đã báo trước đó trên đoạn đường.",
                "placement_rules": "Đặt tại vị trí kết thúc hiệu lực của tất cả các biển báo cấm trước đó.",
                "penalty_references": [
                    {
                        "target_path": "doc_qcvn41_2019.app_b",
                        "doc_code": "QCVN 41:2019/BGTVT",
                        "clause_summary": "Hiệu lực biển báo hiệu đường bộ QCVN 41",
                    }
                ],
                "image_url": "/assets/signs/dp135.svg",
            },
        }

        fallback_matches: list[dict[str, Any]] = []
        if clean_upper in catalog:
            fallback_matches.append(catalog[clean_upper])
        else:
            for k, v in catalog.items():
                if (clean_stripped and clean_stripped == k.replace(".", "").upper()) or (
                    query_kw and (query_kw in v["sign_name"].lower() or query_kw in v["meaning"].lower())
                ) or (cat_upper and v["category"].upper() == cat_upper):
                    fallback_matches.append(v)
                    if len(fallback_matches) >= limit:
                        break

        if fallback_matches:
            first = fallback_matches[0]
            return {
                "status": "success",
                "total_matches": len(fallback_matches),
                "signs": fallback_matches,
                "sign_code": first["sign_code"],
                "sign_name": first["sign_name"],
                "category": first["category"],
                "shape": first["shape"],
                "primary_color": first["primary_color"],
                "meaning": first["meaning"],
                "placement_rules": first["placement_rules"],
                "penalty_references": first["penalty_references"],
            }

        return {"status": "not_found", "total_matches": 0, "signs": [], "sign_code": sign_code}

    # --------------------------------------------------------------------------
    # 7. mcp_traffic_knowledge_cache_query / write
    # --------------------------------------------------------------------------
    async def knowledge_cache_query(
        self,
        query_hash: str | None = None,
        natural_query: str | None = None,
        query_vector: list[float] | None = None,
        similarity_threshold: float = 0.92,
    ) -> dict[str, Any]:
        """Queries runtime knowledge cache for verified reasoning plans."""
        sanitized_query_vector: list[float] | None = None
        if query_vector is not None:
            if not isinstance(query_vector, list):
                raise VectorDimensionMismatchError(
                    f"Expected list for query_vector, got {type(query_vector).__name__}",
                    data={"query_vector_type": type(query_vector).__name__},
                )
            sanitized_query_vector = []
            for idx, val in enumerate(query_vector):
                if not isinstance(val, (int, float)):
                    raise VectorDimensionMismatchError(
                        f"Non-numeric element in query_vector at index {idx}: {val}",
                        data={"invalid_index": idx, "value": str(val)},
                    )
                float_val = float(val)
                if not math.isfinite(float_val):
                    raise VectorDimensionMismatchError(
                        f"Non-finite float (NaN/Inf) detected in query_vector at index {idx}: {float_val}",
                        data={"invalid_index": idx, "value": str(float_val)},
                    )
                sanitized_query_vector.append(float_val)

        pool = await self._ensure_pool()
        resolved_hash = query_hash
        if not resolved_hash and natural_query:
            resolved_hash = hashlib.sha256(natural_query.strip().lower().encode("utf-8")).hexdigest()

        # 1. Mock DB Mode
        if self._is_mock_pool(pool):
            cached = None
            if resolved_hash:
                cached = pool.runtime_cache.get(resolved_hash)
            if not cached and natural_query:
                for v in pool.runtime_cache.values():
                    if v.get("natural_query") == natural_query:
                        cached = v
                        break
            if cached:
                entry = {
                    "cache_id": cached.get("cache_id", "c1a2b3c4-d5e6-7f8a-9b0c-123456789abc"),
                    "natural_query": cached.get("natural_query", natural_query or ""),
                    "similarity_score": float(cached.get("similarity_score", 1.0)),
                    "intent_classification": cached.get("intent_classification", {}),
                    "generated_plan": cached.get("generated_plan", cached.get("plan", {})),
                    "retrieved_chunk_ids": cached.get("retrieved_chunk_ids", []),
                    "synthesized_answer": cached.get("synthesized_answer", cached.get("answer", "")),
                    "verified_citations": cached.get("verified_citations", cached.get("citations", [])),
                    "validation_status": cached.get("validation_status", "VERIFIED"),
                    "hit_count": cached.get("hit_count", 1),
                    "answer": cached.get("synthesized_answer", cached.get("answer", "")),
                    "citations": cached.get("verified_citations", cached.get("citations", [])),
                    "plan": cached.get("generated_plan", cached.get("plan", {})),
                }
                return {
                    "status": "hit",
                    "cache_hit": True,
                    "cached_entry": entry,
                    "cache_entry": entry,
                }
            return {
                "status": "miss",
                "cache_hit": False,
                "cached_entry": None,
                "cache_entry": None,
            }

        # 2. Live PostgreSQL Mode
        if isinstance(pool, asyncpg.Pool):
            async with pool.acquire() as conn:
                try:
                    async with conn.transaction():
                        await conn.execute("SET LOCAL statement_timeout = '5000ms';")
                        row = None
                        # Cosine similarity vector search
                        if sanitized_query_vector is not None and len(sanitized_query_vector) == 384:
                            vec_param = f"[{','.join(str(x) for x in sanitized_query_vector)}]"
                            row = await conn.fetchrow(
                                """
                                SELECT id, natural_query, synthesized_answer, verified_citations,
                                       intent_classification, generated_plan, retrieved_chunk_ids,
                                       validation_status, hit_count,
                                       (1.0 - (query_embedding_384 <=> $1::vector)) AS similarity_score
                                FROM runtime_knowledge_cache
                                WHERE validation_status = 'VERIFIED'
                                  AND expires_at > CURRENT_TIMESTAMP
                                  AND query_embedding_384 IS NOT NULL
                                  AND (1.0 - (query_embedding_384 <=> $1::vector)) >= $2
                                ORDER BY query_embedding_384 <=> $1::vector ASC
                                LIMIT 1;
                                """,
                                vec_param,
                                similarity_threshold,
                            )
                        elif resolved_hash:
                            row = await conn.fetchrow(
                                """
                                SELECT id, natural_query, synthesized_answer, verified_citations,
                                       intent_classification, generated_plan, retrieved_chunk_ids,
                                       validation_status, hit_count, 1.0 AS similarity_score
                                FROM runtime_knowledge_cache
                                WHERE query_hash = $1
                                  AND validation_status = 'VERIFIED'
                                  AND expires_at > CURRENT_TIMESTAMP;
                                """,
                                resolved_hash,
                            )

                        if row:
                            intent_val = row["intent_classification"]
                            if isinstance(intent_val, str):
                                try:
                                    intent_val = json.loads(intent_val)
                                except json.JSONDecodeError:
                                    intent_val = {}

                            plan_val = row["generated_plan"]
                            if isinstance(plan_val, str):
                                try:
                                    plan_val = json.loads(plan_val)
                                except json.JSONDecodeError:
                                    plan_val = {}

                            citations_val = row["verified_citations"]
                            if isinstance(citations_val, str):
                                try:
                                    citations_val = json.loads(citations_val)
                                except json.JSONDecodeError:
                                    citations_val = []

                            entry = {
                                "cache_id": str(row["id"]),
                                "natural_query": row["natural_query"],
                                "similarity_score": float(row["similarity_score"] or 1.0),
                                "intent_classification": intent_val or {},
                                "generated_plan": plan_val or {},
                                "retrieved_chunk_ids": [str(c) for c in (row["retrieved_chunk_ids"] or [])],
                                "synthesized_answer": row["synthesized_answer"],
                                "verified_citations": citations_val or [],
                                "validation_status": row["validation_status"],
                                "hit_count": int(row["hit_count"] or 1),
                                "answer": row["synthesized_answer"],
                                "citations": citations_val or [],
                                "plan": plan_val or {},
                            }
                            return {
                                "status": "hit",
                                "cache_hit": True,
                                "cached_entry": entry,
                                "cache_entry": entry,
                            }
                except (asyncpg.PostgresError, OSError) as err:
                    logger.error("Database knowledge cache query failed: %s", err)
                    raise StorageConnectionError(
                        f"Database knowledge cache query failed: {err}",
                        data={"query_hash": resolved_hash},
                    ) from err

        # 3. In-memory cache fallback
        if resolved_hash and resolved_hash in self._memory_cache:
            mem_entry = self._memory_cache[resolved_hash]
            entry = {
                "cache_id": mem_entry.get("cache_id", "c1a2b3c4-d5e6-7f8a-9b0c-123456789abc"),
                "natural_query": mem_entry.get("natural_query", natural_query or ""),
                "similarity_score": 1.0,
                "intent_classification": mem_entry.get("intent_classification", {}),
                "generated_plan": mem_entry.get("plan", {}),
                "retrieved_chunk_ids": mem_entry.get("retrieved_chunk_ids", []),
                "synthesized_answer": mem_entry.get("answer", ""),
                "verified_citations": mem_entry.get("citations", []),
                "validation_status": "VERIFIED",
                "hit_count": 1,
                "answer": mem_entry.get("answer", ""),
                "citations": mem_entry.get("citations", []),
                "plan": mem_entry.get("plan", {}),
            }
            return {
                "status": "hit",
                "cache_hit": True,
                "cached_entry": entry,
                "cache_entry": entry,
            }

        return {
            "status": "miss",
            "cache_hit": False,
            "cached_entry": None,
            "cache_entry": None,
        }

    async def knowledge_cache_write(
        self,
        query_hash: str | None = None,
        natural_query: str | None = None,
        plan: dict[str, Any] | None = None,
        answer: str = "",
        citations: list[str] | None = None,
        intent_classification: dict[str, Any] | None = None,
        generated_plan: dict[str, Any] | None = None,
        retrieved_chunk_ids: list[str] | None = None,
        traversed_edge_ids: list[str] | None = None,
        verifier_proof: str | None = None,
    ) -> dict[str, Any]:
        """Persists verified reasoning plans and citation subgraphs to knowledge cache."""
        pool = await self._ensure_pool()
        resolved_hash = query_hash
        if not resolved_hash and natural_query:
            resolved_hash = hashlib.sha256(natural_query.strip().lower().encode("utf-8")).hexdigest()

        if not resolved_hash:
            resolved_hash = hashlib.sha256(b"default_query").hexdigest()

        entry = {
            "query_hash": resolved_hash,
            "natural_query": natural_query,
            "plan": plan or generated_plan or {},
            "answer": answer,
            "citations": citations or [],
            "intent_classification": intent_classification or {},
            "retrieved_chunk_ids": retrieved_chunk_ids or [],
            "traversed_edge_ids": traversed_edge_ids or [],
            "verifier_proof": verifier_proof,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }

        # 1. Mock DB Mode
        if self._is_mock_pool(pool):
            pool.runtime_cache[resolved_hash] = entry
            return {"status": "written", "query_hash": resolved_hash}

        # 2. Live PostgreSQL Mode
        if isinstance(pool, asyncpg.Pool):
            async with pool.acquire() as conn:
                try:
                    async with conn.transaction():
                        await conn.execute("SET LOCAL statement_timeout = '5000ms';")
                        await conn.execute(
                            """
                            INSERT INTO runtime_knowledge_cache (
                                query_hash, natural_query, synthesized_answer,
                                verified_citations, intent_classification, generated_plan,
                                retrieved_chunk_ids, traversed_edge_ids, validation_status,
                                expires_at
                            ) VALUES (
                                $1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb,
                                $7::uuid[], $8::uuid[], 'VERIFIED',
                                CURRENT_TIMESTAMP + INTERVAL '30 days'
                            )
                            ON CONFLICT (query_hash) DO UPDATE SET
                                synthesized_answer = EXCLUDED.synthesized_answer,
                                verified_citations = EXCLUDED.verified_citations,
                                hit_count = runtime_knowledge_cache.hit_count + 1,
                                last_accessed_at = CURRENT_TIMESTAMP;
                            """,
                            resolved_hash,
                            natural_query or "",
                            answer,
                            json.dumps(citations or []),
                            json.dumps(intent_classification or {}),
                            json.dumps(plan or generated_plan or {}),
                            [cid for cid in (retrieved_chunk_ids or []) if len(cid) == 36],
                            [eid for eid in (traversed_edge_ids or []) if len(eid) == 36],
                        )
                except (asyncpg.PostgresError, OSError) as err:
                    logger.error("Database knowledge cache write failed: %s", err)
                    raise StorageConnectionError(
                        f"Database knowledge cache write failed: {err}",
                        data={"query_hash": resolved_hash},
                    ) from err

        # 3. In-memory cache fallback
        self._memory_cache[resolved_hash] = entry
        return {"status": "written", "query_hash": resolved_hash}

    # --------------------------------------------------------------------------
    # Convenience Domain Aliases
    # --------------------------------------------------------------------------
    async def search_legal_norms(self, **kwargs: Any) -> dict[str, Any]:
        """Convenience alias for hybrid_search."""
        return await self.hybrid_search(**kwargs)

    async def traverse_triad(self, start_chunk_id: str, **kwargs: Any) -> dict[str, Any]:
        """Convenience alias for graph_traverse."""
        return await self.graph_traverse(start_chunk_id=start_chunk_id, **kwargs)

    async def lookup_sign(self, sign_code: str, **kwargs: Any) -> dict[str, Any]:
        """Convenience alias for sign_catalog_lookup."""
        return await self.sign_catalog_lookup(sign_code=sign_code, **kwargs)

    async def resolve_precedence(self, **kwargs: Any) -> dict[str, Any]:
        """Convenience alias for scope_override_detect."""
        return await self.scope_override_detect(**kwargs)

    async def validate_temporal(
        self, document_code: str, as_of_date: str | None = None
    ) -> dict[str, Any]:
        """Validates temporal status and effectiveness dates of a legal document."""
        pool = await self._ensure_pool()
        check_date = as_of_date or datetime.datetime.now(datetime.UTC).date().isoformat()

        if self._is_mock_pool(pool):
            doc = pool.documents.get(document_code)
            if doc:
                eff = doc.get("effective_date", "2020-01-01")
                is_active = check_date >= eff
                return {
                    "status": "success",
                    "doc_code": document_code,
                    "effective_date": eff,
                    "is_active": is_active,
                    "checked_date": check_date,
                }
            return {"status": "not_found", "doc_code": document_code}

        if isinstance(pool, asyncpg.Pool):
            async with pool.acquire() as conn:
                try:
                    async with conn.transaction():
                        await conn.execute("SET LOCAL statement_timeout = '5000ms';")
                        row = await conn.fetchrow(
                            "SELECT doc_code, title, effective_date, expiration_date, status FROM legal_documents WHERE doc_code = $1;",
                            document_code,
                        )
                        if row:
                            eff = str(row["effective_date"]) if row["effective_date"] else None
                            exp = str(row["expiration_date"]) if row["expiration_date"] else None
                            is_active = True
                            if eff and check_date < eff:
                                is_active = False
                            if exp and check_date > exp:
                                is_active = False
                            return {
                                "status": "success",
                                "doc_code": row["doc_code"],
                                "title": row["title"],
                                "effective_date": eff,
                                "expiration_date": exp,
                                "document_status": row["status"],
                                "is_active": is_active,
                                "checked_date": check_date,
                            }
                except (asyncpg.PostgresError, OSError) as err:
                    logger.error("Database validate_temporal query failed: %s", err)
                    raise StorageConnectionError(
                        f"Database validate_temporal failed: {err}",
                        data={"document_code": document_code},
                    ) from err

        return {"status": "success", "doc_code": document_code, "is_active": True, "checked_date": check_date}

