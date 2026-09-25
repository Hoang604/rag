"""Production sensors executing queries and knowledge graph mutations via WAL proposals."""

from __future__ import annotations

import datetime
import logging
import re
import uuid
from typing import Any, Final

import asyncpg

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.ingestion.facets import classify_intent, classify_query
from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.mcp.tools.embedder import QueryEmbedder
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
    VerbatimGrepResult,
    extract_metadata_dict,
)
from rag_eval.legal.retrieval.annotations import ANSWERS, AnnotationStore
from rag_eval.legal.retrieval.lexicon import expand_query, phrase_variants
from rag_eval.legal.retrieval.relatedness import Relatedness
from rag_eval.legal.retrieval.reranker import CrossEncoderReranker
from rag_eval.legal.schemas import (
    E_AST_GROUNDING_VALIDATION,
    E_INVALID_DOCUMENT_HIERARCHY,
    E_STORAGE_CONNECTION,
    LegalDomainError,
    get_vietnam_today,
    parse_flexible_date,
    validate_ltree_path,
)
from rag_eval.legal.text import is_unaccented

logger = logging.getLogger("rag_eval.legal.mcp.tools.sensors")


_WINDOW_SUFFIX: Final = re.compile(r"\.w_(\d+)$")


_ELISION: Final = "| ... | (lược bớt phần khác của bảng) |"


def _merge_table_windows(bodies: list[str], max_chars: int, focus: int = 0) -> str:
    """Reassembles the windows of one provision, centred on the retrieved one.

    Every window repeats the same opening block -- caption, unit note, column
    header -- because each has to be readable alone. Concatenating them raw
    would restate that block between every few rows, which reads worse than
    the split did and wastes the prompt. So the shared opening is found by
    comparing the windows to each other rather than by re-parsing Markdown:
    whatever leading lines they all agree on is the header, by construction.

    `focus` is the window retrieval actually matched, and it is the whole
    point of the second version of this function. The first filled the budget
    from `w_1` forward and truncated when it ran out. For a short provision
    that is the same thing; for `Phụ lục G.1.1`, whose ten windows open with
    six of prose, it meant the answer to "tầm nhìn vượt xe ứng với 60 km/h"
    -- a table in `w_10`, the window retrieval had returned -- was dropped in
    favour of prose about lane markings, and the merged text ended in a
    truncation marker where the table should have been. Expansion made three
    questions unanswerable that plain retrieval got right.

    So the retrieved window is kept first, then neighbours outward while the
    budget allows, and the result is emitted in document order with a marker
    wherever something was left out. Windows are added nearest-first and the
    walk stops at the first that does not fit, which keeps the kept set
    contiguous: a table read from rows 4-9 is still a table, one read from
    rows 4-5 and 11-12 invites reading a value off the wrong row.
    """
    split = [body.split("\n") for body in bodies if body.strip()]
    if not split:
        return ""
    focus = min(max(focus, 0), len(split) - 1)

    shared = 0
    while all(
        len(lines) > shared and lines[shared] == split[0][shared] for lines in split
    ):
        shared += 1

    header = split[0][:shared]
    tails = [lines[shared:] for lines in split]

    def cost(lines: list[str]) -> int:
        return sum(len(line) + 1 for line in lines)

    whole = "\n".join([*header, *(line for tail in tails for line in tail)])
    if len(whole) <= max_chars:
        return whole

    budget = max_chars - len(_ELISION) - 2
    kept = {focus}
    used = cost(header) + cost(tails[focus])
    # Nearest-first, stopping at the first window that does not fit, so the
    for step in range(1, len(tails)):
        fitted = False
        for index in (focus - step, focus + step):
            if index in kept or not 0 <= index < len(tails):
                continue
            if used + cost(tails[index]) > budget:
                continue
            kept.add(index)
            used += cost(tails[index])
            fitted = True
        if not fitted:
            break

    out = list(header)
    order = sorted(kept)
    if order[0] > 0:
        out.append(_ELISION)
    for position, index in enumerate(order):
        if position and index != order[position - 1] + 1:
            out.append(_ELISION)
        out.extend(tails[index])
    if order[-1] < len(tails) - 1:
        out.append(_ELISION)
    return "\n".join(out)


class LegalRuntimeSensors:
    """Encapsulates production database sensors with write-protected WAL routing."""

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        embedding_engine: QueryEmbedder | None = None,
        staging_manager: StagingManager | None = None,
        reranker: CrossEncoderReranker | None = None,
        rerank_by_default: bool = False,
        use_relatedness: bool = False,
    ) -> None:
        self._pool = pool
        self._embedding_engine = embedding_engine
        self._staging_manager = staging_manager
        # Holding a reranker and using one are separate decisions.
        self._reranker = reranker
        self._rerank_by_default = rerank_by_default
        # Learned expansion is off until a measurement says otherwise: on the
        # held-out set it scored 80.0 against 81.2 for the hand lexicon alone.
        self._use_relatedness = use_relatedness
        self._relatedness: Relatedness | None = None

    async def _embed_query(self, query: str) -> list[float] | None:
        """Encodes a query into a dense vector via the injected embedder.

        No embedder means sparse-only retrieval, logged at warning level: a
        silent None is indistinguishable from merely poor ranking, which is how
        a dead dense path stays invisible.
        """
        if self._embedding_engine is None:
            logger.warning(
                "No query embedder configured; hybrid_search is running sparse-only"
            )
            return None
        try:
            return await self._embedding_engine.embed_query(query)
        except (RuntimeError, ValueError, TypeError, OSError, AttributeError) as exc:
            logger.warning(
                "Query embedding failed, falling back to sparse-only: %s", exc
            )
            return None

    async def _get_relatedness(self) -> Relatedness:
        """Loads the relatedness table once per process."""
        if self._relatedness is None:
            self._relatedness = await Relatedness.load(await self._get_pool())
        return self._relatedness

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
        rerank: bool | None = None,
        rerank_pool: int = RERANK_POOL,
        doc_codes: list[str] | None = None,
    ) -> HybridSearchResult:
        """Executes Reciprocal Rank Fusion (RRF) search over chunks and documents."""
        pool = await self._get_pool()
        t_date = get_vietnam_today()
        if temporal_violation_date:
            parsed_d = parse_flexible_date(temporal_violation_date)
            if parsed_d is not None:
                t_date = parsed_d

        # Auto-compute dense vector via injected embedder
        computed_vector = await self._embed_query(query)

        # The pgvector codec encodes the list; a JSON string is rejected.
        vector_param = computed_vector

        # Điều 6/7/8 of ND 168 differ only by vehicle class; the embedding cannot
        vehicle_class = classify_query(query)
        provision_role = classify_intent(query)
        # Only the sparse half sees the expansion: the vector is still computed
        sparse_text = expand_query(query)
        variants = phrase_variants(query)
        # Only where the hand lexicon stayed silent. A verified statutory
        if self._use_relatedness and sparse_text == query:
            learned = (await self._get_relatedness()).expand(query)
            if learned:
                sparse_text = " ".join([query, *learned])
        # An unaccented query lands far from its answer in vector space while
        dense_weight = 0.2 if is_unaccented(query) else 1.0

        # Reranking reorders; it cannot retrieve. So the fusion is asked for a
        want_rerank = self._rerank_by_default if rerank is None else rerank
        want_rerank = want_rerank and self._reranker is not None
        # Not for a query typed without tone marks. The cross-encoder was
        if want_rerank and is_unaccented(query):
            want_rerank = False
        fetch_limit = max(limit, rerank_pool) if want_rerank else limit

        sql = """
        SELECT 
            chunk_id, doc_code, doc_title, path, verbatim_text,
            contextualized_text, metadata, effective_date, expiration_date, rrf_score,
            sparse_rank, dense_similarity
        FROM hybrid_search(
            $1, $2::vector, $3::date, $4::int, 60, $5, $6, $7, $8, NULL, $9
        );
        """
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    sql,
                    sparse_text,
                    vector_param,
                    t_date,
                    fetch_limit,
                    vehicle_class,
                    provision_role,
                    variants,
                    dense_weight,
                    # NULL, not an empty array: an empty list would resolve to
                    doc_codes or None,
                )
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
                        expiration_date=str(r["expiration_date"])
                        if r["expiration_date"]
                        else None,
                        score=float(r["rrf_score"]),
                        dense_similarity=float(r["dense_similarity"]),
                        # 999 is the sentinel for "the keyword side never
                        keyword_matched=int(r["sparse_rank"]) < 999,
                    )
                    for r in rows
                ]
                if want_rerank and self._reranker is not None and len(hits) > 1:
                    # The expanded query, not what the user typed. The
                    hits = await self._reranker.rerank(sparse_text, hits, top_k=limit)
                else:
                    hits = hits[:limit]

                return HybridSearchResult(
                    total_hits=len(hits),
                    hits=hits,
                    temporal_as_of=t_date.isoformat(),
                    dense_is_informative=dense_weight == 1.0,
                    expanded_query=sparse_text,
                )
        except (
            OSError,
            RuntimeError,
            asyncpg.PostgresError,
            TypeError,
            ValueError,
        ) as exc:
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

    async def add_metadata(
        self,
        chunk_id: str,
        query: str,
        relation: str = ANSWERS,
        note: str | None = None,
        session_id: str | None = None,
    ) -> AddMetadataResult:
        """Records that a chunk answered a question, for later overlay work.

        Write-only for now: nothing here changes what `hybrid_search` returns.
        That is deliberate. The annotation is an agent's belief that it found
        the right provision, and an unverified belief promoted straight into
        ranking would steer every later retrieval toward it -- the model's own
        guess fed back as evidence. Sprint 3 evaluates whether to act on this
        with the overlay on and off; until then the log accumulates and the
        ranking stays a pure function of the corpus.
        """
        pool = await self._get_pool()
        store = AnnotationStore(pool)
        try:
            annotation_id = await store.record(
                chunk_id=chunk_id,
                query_text=query,
                relation=relation,
                note=note,
                session_id=session_id,
            )
            counts = await store.counts()
        except ValueError as exc:
            raise LegalDomainError(
                message=str(exc), error_code=E_AST_GROUNDING_VALIDATION
            ) from exc
        except asyncpg.ForeignKeyViolationError as exc:
            raise LegalDomainError(
                message=f"Chunk không tồn tại: {chunk_id}",
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
            ) from exc
        except asyncpg.PostgresError as exc:
            raise LegalDomainError(
                message=f"Không ghi được annotation: {exc}",
                error_code=E_STORAGE_CONNECTION,
            ) from exc

        return AddMetadataResult(
            annotation_id=annotation_id,
            chunk_id=chunk_id,
            recorded_at=datetime.datetime.now(datetime.UTC).isoformat(),
            total_annotations=sum(counts.values()),
        )

    async def expand_windows(
        self, hits: list[SearchHit], max_chars: int = 5_000
    ) -> list[SearchHit]:
        """Rejoins a provision that chunking split, for the layer that answers.

        A provision longer than the embedding budget is stored as sibling
        windows. That is right for retrieval -- each window is independently
        findable and independently readable -- and wrong for answering,
        because the model is handed a fragment and the sentence it needs is
        often in a different fragment.

        Tables are the sharpest case: `Bảng 5` occupies `.w_2` through `.w_9`,
        each repeating the caption and column header over a few rows. But the
        problem is not table-specific and the first version of this method was
        wrong to treat it as such. Asked about that very table, retrieval
        returned `.w_1` -- the *prose* window of the same Điểm -- so a
        table-only rule expanded nothing at all. Whether the retrieved
        fragment happens to contain pipes says nothing about whether the rest
        of the provision is missing.

        Deliberately not applied to `/search`. A reviewer looking at results
        is checking what retrieval actually returned, and silently showing
        something larger than the retrieved chunk would misrepresent that.

        Rebuilt from the siblings' own stored text, so the merged provision is
        still nothing but statute -- the citation and the grounding check keep
        working on it unchanged.
        """
        windowed = [
            (index, hit)
            for index, hit in enumerate(hits)
            if _WINDOW_SUFFIX.search(hit.path)
        ]
        if not windowed:
            return hits

        parents = {_WINDOW_SUFFIX.sub("", hit.path) for _, hit in windowed}
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT path::text AS path, verbatim_text
                FROM chunks
                WHERE regexp_replace(path::text, '\\.w_[0-9]+$', '') = ANY($1::text[])
                ORDER BY path
                """,
                sorted(parents),
            )

        # Sorted numerically: `ORDER BY path` is lexical, so w_10 lands between
        siblings: dict[str, list[tuple[int, str]]] = {}
        for row in rows:
            path = str(row["path"])
            match = _WINDOW_SUFFIX.search(path)
            parent = _WINDOW_SUFFIX.sub("", path)
            siblings.setdefault(parent, []).append(
                (int(match.group(1)) if match else 0, str(row["verbatim_text"]))
            )

        merged = list(hits)
        for index, hit in windowed:
            parts = sorted(siblings.get(_WINDOW_SUFFIX.sub("", hit.path), []))
            if len(parts) < 2:
                continue
            own = _WINDOW_SUFFIX.search(hit.path)
            own_number = int(own.group(1)) if own else 0
            focus = next(
                (i for i, (number, _) in enumerate(parts) if number == own_number), 0
            )
            text = _merge_table_windows(
                [body for _, body in parts], max_chars, focus=focus
            )
            merged[index] = hit.model_copy(
                update={
                    "verbatim_text": text,
                    "contextualized_text": text,
                }
            )
        return merged

    async def chunk_backlog_poll(
        self,
        finalization_state: str | None = None,
        doc_code: str | None = None,
        limit: int = 50,
    ) -> ChunkBacklogResult:
        """Polls statutory provisions with unfinalized status or open caveats."""
        pool = await self._get_pool()
        query = """
        SELECT 
            c.id, d.doc_code, c.path::text AS path, c.finalization_state, c.verbatim_text,
            dep.dependency_text, dep.dependency_type, dep.suggested_target_doc
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        LEFT JOIN chunk_dangling_dependencies dep ON c.id = dep.chunk_id
        WHERE c.finalization_state LIKE 'UNFINALIZED_%'
          AND ($1::text IS NULL OR c.finalization_state = $1::text)
          AND ($2::text IS NULL OR d.doc_code = $2::text)
        ORDER BY c.created_at DESC
        LIMIT $3::int;
        """
        count_query = """
        SELECT count(*)
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.finalization_state LIKE 'UNFINALIZED_%'
          AND ($1::text IS NULL OR c.finalization_state = $1::text)
          AND ($2::text IS NULL OR d.doc_code = $2::text);
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, finalization_state, doc_code, limit)
            total = await conn.fetchval(count_query, finalization_state, doc_code)

        items = [
            DanglingBacklogItem(
                chunk_id=str(r["id"]),
                doc_code=str(r["doc_code"]),
                path=str(r["path"]),
                finalization_state=str(r["finalization_state"]),
                verbatim_text=str(r["verbatim_text"])[:200],
                dependency_text=r["dependency_text"],
                dependency_type=r["dependency_type"],
                suggested_target_doc=r["suggested_target_doc"],
            )
            for r in rows
        ]
        return ChunkBacklogResult(
            total_unfinalized=int(total or 0),
            returned=len(items),
            items=items,
        )

