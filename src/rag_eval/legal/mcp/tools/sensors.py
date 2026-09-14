"""Production sensors executing queries and knowledge graph mutations via WAL proposals."""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

import asyncpg

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.ingestion.staging.manager import StagingManager
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
    LegalDomainError,
    get_vietnam_today,
    parse_flexible_date,
    validate_ltree_path,
)

logger = logging.getLogger("rag_eval.legal.mcp.tools.sensors")


class LegalRuntimeSensors:
    """Encapsulates production database sensors with write-protected WAL routing."""

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        embedding_engine: QueryEmbedder | None = None,
        staging_manager: StagingManager | None = None,
    ) -> None:
        self._pool = pool
        self._embedding_engine = embedding_engine
        self._staging_manager = staging_manager

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await get_db_pool()
        return self._pool

    async def build_dynamic_corpus_manifest(
        self, as_of_date: datetime.date | None = None
    ) -> str:
        """Renders dynamic markdown list of ingested documents from PostgreSQL."""
        target_date = as_of_date or get_vietnam_today()
        date_str = target_date.strftime("%d/%m/%Y")
        pool = await self._get_pool()
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT doc_code, title, effective_date, expiration_date FROM documents ORDER BY effective_date DESC;"
                )
            if not rows:
                return f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})\n- (Cơ sở dữ liệu chưa có văn bản nào)"
            lines = [f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})"]
            for r in rows:
                exp = f", hết hiệu lực: {r['expiration_date']}" if r["expiration_date"] else ""
                lines.append(f"- **{r['doc_code']}**: {r['title']} (Hiệu lực: {r['effective_date']}{exp})")
            return "\n".join(lines)
        except (OSError, RuntimeError, asyncpg.PostgresError):
            return f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})\n- (Cơ sở dữ liệu đang ngoại tuyến hoặc chưa kết nối)"

    async def hybrid_search(
        self,
        query: str,
        temporal_violation_date: str | None = None,
        limit: int = 10,
    ) -> HybridSearchResult:
        pool = await self._get_pool()
        parsed_date = parse_flexible_date(temporal_violation_date) if temporal_violation_date else None
        target_date = parsed_date if parsed_date is not None else get_vietnam_today()

        dense_vector: list[float] | None = None
        if self._embedding_engine is not None:
            dense_vector = await self._embedding_engine.embed_query(query)

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM search_statutory_chunks(
                    $1, $2::vector, $3::date, $4::int, 60, 1.0, 1.0
                );
                """,
                query,
                str(dense_vector) if dense_vector is not None else None,
                target_date,
                limit,
            )

            hits = [
                SearchHit(
                    chunk_id=str(r["chunk_id"]),
                    doc_code=str(r["doc_code"]),
                    doc_title=str(r["doc_title"] if "doc_title" in r else r["doc_code"]),
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
                temporal_as_of=target_date.isoformat(),
            )

    async def verbatim_grep(
        self,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        temporal_violation_date: str | None = None,
        limit: int = 20,
    ) -> VerbatimGrepResult:
        pool = await self._get_pool()
        parsed_date = parse_flexible_date(temporal_violation_date) if temporal_violation_date else None
        target_date = parsed_date if parsed_date is not None else get_vietnam_today()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM grep_statutory_text(
                    $1, $2, $3, $4::date, $5::int
                );
                """,
                pattern,
                is_regex,
                case_sensitive,
                target_date,
                limit,
            )

            hits = [
                SearchHit(
                    chunk_id=str(r["chunk_id"]),
                    doc_code=str(r["doc_code"]),
                    doc_title=str(r["doc_title"] if "doc_title" in r else r["doc_code"]),
                    path=str(r["path"]),
                    verbatim_text=str(r["verbatim_text"]),
                    contextualized_text=str(r["contextualized_text"] if "contextualized_text" in r else r["verbatim_text"]),
                    metadata=extract_metadata_dict(r["metadata"]),
                    effective_date=str(r["effective_date"]),
                    expiration_date=str(r["expiration_date"]) if r["expiration_date"] else None,
                    score=1.0,
                )
                for r in rows
            ]

            return VerbatimGrepResult(
                pattern=pattern,
                is_regex=is_regex,
                total_matches=len(hits),
                returned=len(hits),
                truncated=False,
                matches=hits,
            )

    async def hierarchical_navigate(
        self,
        path: str | None = None,
        chunk_id: str | None = None,
        direction: str = "FULL_ARTICLE",
    ) -> HierarchicalNavigateResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            origin_chunk_id: uuid.UUID | None = None
            origin_path: str | None = None

            if chunk_id:
                try:
                    origin_chunk_id = uuid.UUID(chunk_id)
                except ValueError as err:
                    raise LegalDomainError(
                        error_code=E_INVALID_DOCUMENT_HIERARCHY,
                        message=f"Định danh chunk_id '{chunk_id}' không phải là UUID hợp lệ.",
                    ) from err
            elif path:
                origin_path = validate_ltree_path(path)
            else:
                raise LegalDomainError(
                    error_code=E_INVALID_DOCUMENT_HIERARCHY,
                    message="Bắt buộc phải cung cấp 'path' (chuỗi ltree) hoặc 'chunk_id' (UUID) để điều hướng.",
                )

            row = await conn.fetchrow(
                """
                SELECT c.id, c.path, c.document_id, d.doc_code, d.title
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE ($1::uuid IS NOT NULL AND c.id = $1::uuid)
                   OR ($2::text IS NOT NULL AND c.path = $2::ltree);
                """,
                origin_chunk_id,
                origin_path,
            )

            if not row:
                raise LegalDomainError(
                    error_code=E_INVALID_DOCUMENT_HIERARCHY,
                    message=f"Không tìm thấy đoạn quy phạm tương ứng với chunk_id='{chunk_id}', path='{path}'.",
                )

            found_path: str = row["path"]
            doc_id: uuid.UUID = row["document_id"]
            doc_code: str = row["doc_code"]

            query = ""
            params: list[Any] = []

            if direction == "FULL_ARTICLE":
                segments = found_path.split(".")
                article_subpath = None
                for seg in segments:
                    if seg.startswith("a_"):
                        idx = segments.index(seg)
                        article_subpath = ".".join(segments[: idx + 1])
                        break

                if not article_subpath:
                    article_subpath = found_path

                query = """
                    SELECT c.id, c.path, c.verbatim_text, c.contextualized_text, c.metadata
                    FROM chunks c
                    WHERE c.document_id = $1 AND c.path <@ $2::ltree
                    ORDER BY c.path ASC;
                """
                params = [doc_id, article_subpath]

            elif direction == "CHILDREN":
                query = """
                    SELECT c.id, c.path, c.verbatim_text, c.contextualized_text, c.metadata
                    FROM chunks c
                    WHERE c.document_id = $1 
                      AND c.path <@ $2::ltree 
                      AND c.path != $2::ltree
                      AND nlevel(c.path) = nlevel($2::ltree) + 1
                    ORDER BY c.path ASC;
                """
                params = [doc_id, found_path]

            elif direction == "PARENT_CHAIN":
                query = """
                    SELECT c.id, c.path, c.verbatim_text, c.contextualized_text, c.metadata
                    FROM chunks c
                    WHERE c.document_id = $1 
                      AND c.path @> $2::ltree 
                      AND c.path != $2::ltree
                    ORDER BY nlevel(c.path) ASC;
                """
                params = [doc_id, found_path]

            elif direction == "SIBLINGS":
                query = """
                    SELECT c.id, c.path, c.verbatim_text, c.contextualized_text, c.metadata
                    FROM chunks c
                    WHERE c.document_id = $1 
                      AND subpath(c.path, 0, nlevel(c.path) - 1) = subpath($2::ltree, 0, nlevel($2::ltree) - 1)
                      AND nlevel(c.path) = nlevel($2::ltree)
                      AND c.path != $2::ltree
                    ORDER BY c.path ASC;
                """
                params = [doc_id, found_path]

            result_rows = await conn.fetch(query, *params)
            nodes = [
                HierarchyNode(
                    chunk_id=str(r["id"]),
                    path=str(r["path"]),
                    doc_code=doc_code,
                    verbatim_text=str(r["verbatim_text"]),
                    contextualized_text=str(r["contextualized_text"]),
                    metadata=extract_metadata_dict(r["metadata"]),
                    relative_depth=0,
                )
                for r in result_rows
            ]

            return HierarchicalNavigateResult(
                anchor_path=found_path,
                direction=direction,
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
        async with pool.acquire() as conn:
            try:
                src_uuid = uuid.UUID(source_chunk_id)
            except ValueError as err:
                raise LegalDomainError(
                    error_code=E_INVALID_DOCUMENT_HIERARCHY,
                    message=f"source_chunk_id '{source_chunk_id}' không phải là UUID hợp lệ.",
                ) from err

            rows = await conn.fetch(
                """
                SELECT * FROM traverse_knowledge_graph($1::uuid, $2, $3::int);
                """,
                src_uuid,
                direction,
                max_depth,
            )

            paths = [
                GraphTraversalStep(
                    edge_id=str(r["id"] if "id" in r else uuid.uuid4()),
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
        """Records proposed relational edge into staging WAL journal without modifying PostgreSQL.

        Zero SQL INSERT statements are executed against production PostgreSQL.
        The edge proposal is appended to WAL for human reviewer promotion.
        """
        edge_id = uuid.uuid4()
        mgr = self._staging_manager
        if mgr is None:
            mgr = StagingManager()
            self._staging_manager = mgr

        doc_code: str = ""
        resolved_source_path: str = source_chunk_id
        resolved_target_path: str | None = target_chunk_id

        needs_db = ("." not in source_chunk_id) or (target_chunk_id is not None and "." not in target_chunk_id)
        if needs_db:
            try:
                pool = await self._get_pool()
                async with pool.acquire() as conn:
                    if "." not in source_chunk_id:
                        src_uuid = uuid.UUID(source_chunk_id)
                        row = await conn.fetchrow(
                            "SELECT c.path, d.doc_code FROM chunks c JOIN documents d ON c.document_id = d.id WHERE c.id = $1::uuid;",
                            src_uuid,
                        )
                        if row:
                            resolved_source_path = str(row["path"])
                            doc_code = str(row["doc_code"])

                    if target_chunk_id is not None and "." not in target_chunk_id:
                        tgt_uuid = uuid.UUID(target_chunk_id)
                        tgt_row = await conn.fetchrow(
                            "SELECT path FROM chunks WHERE id = $1::uuid;",
                            tgt_uuid,
                        )
                        if tgt_row:
                            resolved_target_path = str(tgt_row["path"])
            except (OSError, RuntimeError, asyncpg.PostgresError, ValueError, LegalDomainError):
                pass

        if not doc_code and "." in source_chunk_id:
            doc_code = source_chunk_id.split(".")[0]

        if not doc_code:
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=f"Cannot propose graph edge: source chunk '{source_chunk_id}' cannot be grounded to any active statutory document.",
                data={"source_chunk_id": source_chunk_id},
            )

        wal_store = mgr._get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=f"Cannot propose graph edge: staging session for document '{doc_code}' does not exist.",
                data={"doc_code": doc_code, "source_chunk_id": source_chunk_id},
            )

        edge_payload = {
            "source_path": resolved_source_path,
            "target_path": resolved_target_path,
            "target_external_ref": target_external_ref,
            "relation_type": relation_type,
            "citation_text": citation_text,
            "metadata": metadata or {},
        }

        wal_store.append_record(
            actor="AGENT",
            op_type="GRAPH_EDGE_PROPOSED",
            description=f"Agent proposed relation edge '{relation_type}' from '{resolved_source_path}'.",
            payload={"edges": [edge_payload], "edge_id": str(edge_id)},
        )

        return GraphEdgeWriteResult(
            edge_id=str(edge_id),
            status="PROPOSED_IN_WAL",
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
