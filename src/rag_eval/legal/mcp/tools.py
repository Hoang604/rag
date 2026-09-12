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

import asyncio
import datetime
import json
import logging
import re
import uuid
from typing import Any, Final, Protocol, final

import asyncpg
from pydantic import BaseModel, ConfigDict, Field, computed_field

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.ingestion.facets import classify_intent, classify_query
from rag_eval.legal.ingestion.loader import (
    compute_chunk_embeddings,
)
from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingGrepHit,
    StagingManager,
    StagingMutationRecord,
    StagingStatus,
    StgReparentResult,
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
    # The magnitudes the fused score is computed from and then discards.
    dense_similarity: float = 0.0
    keyword_matched: bool = True
    # Set when a cross-encoder reordered these hits. `score` stays the fused
    rerank_score: float | None = None


# Below this cosine similarity the answer is usually unrelated to the question.
LOW_SIMILARITY: float = 0.86

# Cross-encoder logit below which the reranker's own best candidate is a
LOW_RERANK: float = -1.0

# How many candidates the cross-encoder is given when reranking is on. Depth is
RERANK_POOL: int = 10


class AddMetadataResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    annotation_id: str
    chunk_id: str
    recorded_at: str
    total_annotations: int


class HybridSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_hits: int
    hits: list[SearchHit]
    temporal_as_of: str | None = None
    # False when the query carries no tone marks. The corpus is embedded from
    dense_is_informative: bool = True
    # The text the sparse ranker actually matched on, which is not the text the
    expanded_query: str = ""

    # A plain @property is invisible to `model_dump`, so this was computed on
    @computed_field  # type: ignore[prop-decorator]
    @property
    def confidence(self) -> str:
        """Reports how much the caller should trust these hits.

        Three signals, each catching a failure the others miss.

        "none" means the keyword side matched nothing at all, which over 400
        answerable questions was wrong 0 times and caught 25 of 25 meaningless
        ones.

        A very negative cross-encoder score means the reranker judged even its
        best candidate irrelevant. This catches the case the other two cannot:
        a question in this domain whose answer is outside this corpus. Asked
        how many years in prison a fatal accident carries, retrieval returned
        five helmet provisions at `high` -- "xe máy" and "phạt" matched
        keywords and cosine sat at 0.88 -- while every hit carried a rerank
        score near -3. The reranker had the answer and it was discarded.
        Measured over 99 answerable, 25 out-of-scope and 16 junk questions,
        a cut at -1.0 flags 90.2% of the unanswerable at a 7.1% false-warning
        rate; the two distributions overlap, so this is a warning and never a
        suppression. See `evidence/abstain_sweep.txt` for the full sweep.

        "low" is also the softer cosine signal, withheld where cosine is known
        to be depressed for reasons other than relevance: unaccented queries
        were 100% of the false warnings before this exception, and 0.5% of
        real questions after it.
        """
        if not self.hits:
            return "none"
        if not any(hit.keyword_matched for hit in self.hits):
            return "none"
        scores = [h.rerank_score for h in self.hits if h.rerank_score is not None]
        if scores and max(scores) < LOW_RERANK:
            return "low"
        if not self.dense_is_informative:
            return "high"
        if max(hit.dense_similarity for hit in self.hits) < LOW_SIMILARITY:
            return "low"
        return "high"


class VerbatimGrepResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pattern: str
    is_regex: bool
    total_matches: int
    """Uncapped number of matching chunks in the corpus, not the number returned."""
    returned: int
    truncated: bool
    """True when total_matches exceeds the requested limit."""
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
    char_length: int = 0
    is_truncated: bool = False
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


class StgGetChunkResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    chunk: StagingChunk


class StgGetRawResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    start_line: int
    end_line: int
    total_lines: int
    content: str


class StgGrepResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    pattern: str
    is_regex: bool
    total_matches: int
    matches: list[StagingGrepHit]


class StgPatchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    status: str = "SUCCESS"
    updated_count: int = 0
    cascaded_count: int = 0
    removed_count: int = 0
    total_chunks_after_patch: int
    fields_modified: list[str] = Field(default_factory=list)


class StgAddEdgesResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    status: str
    total_edges: int


class StgCommitResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    status: str = "AGENT_COMMITTED"
    total_chunks: int
    total_edges: int
    committed_at: str
    message: str


# ------------------------------------------------------------------------------
class QueryEmbedder(Protocol):
    """Encodes a search query into a dense vector for hybrid_search."""

    async def embed_query(self, query: str) -> list[float] | None: ...


@final
class SentenceTransformerQueryEmbedder:
    """Default embedder: same model and asymmetric prefix as ingestion.

    Documents are embedded as "passage: <text>" by the ingestion loader. e5
    models are trained on that asymmetry, so a query embedded without the
    "query: " prefix lands in the wrong region of the space and dense recall
    degrades silently. Reusing compute_chunk_embeddings keeps the two paths from
    drifting apart, including L2 normalisation.
    """

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        max_cache_size: int = 1024,
    ) -> None:
        self._model_name = model_name
        self._cache: dict[str, list[float]] = {}
        self._max_cache_size = max_cache_size

    async def embed_query(self, query: str) -> list[float] | None:
        norm_query = query.strip()
        if norm_query in self._cache:
            return self._cache[norm_query]

        vectors = await asyncio.to_thread(
            compute_chunk_embeddings,
            [norm_query],
            model_name=self._model_name,
            is_query=True,
        )
        if not vectors or vectors[0] is None:
            return None
        res = vectors[0]
        if len(self._cache) >= self._max_cache_size:
            try:
                first_key = next(iter(self._cache))
                del self._cache[first_key]
            except StopIteration:
                pass
        self._cache[norm_query] = res
        return res


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


class LegalMCPTools:
    """Atomic Sensor & Staging MCP Tools for LLM Agent orchestration over PostgreSQL."""

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        staging_manager: StagingManager | None = None,
        embedding_engine: QueryEmbedder | None = None,
        reranker: CrossEncoderReranker | None = None,
        rerank_by_default: bool = False,
        use_relatedness: bool = False,
    ) -> None:
        self._pool = pool
        self._staging = staging_manager or StagingManager()
        self._embedding_engine = embedding_engine
        # Holding a reranker and using one are separate decisions. The web app
        self._reranker = reranker
        self._rerank_by_default = rerank_by_default
        # Learned expansion is off until a measurement says otherwise. The
        self._use_relatedness = use_relatedness
        self._relatedness: Relatedness | None = None

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

    async def _get_relatedness(self) -> Relatedness:
        """Loads the relatedness table once per process."""
        if self._relatedness is None:
            self._relatedness = await Relatedness.load(await self._get_pool())
        return self._relatedness

    async def _embed_query(self, query: str) -> list[float] | None:
        """Encodes a search query into a dense vector via the injected embedder.

        No embedder means sparse-only retrieval, logged at warning level: a
        silent None is indistinguishable from merely poor ranking, which is how
        a dead dense path stays invisible. The embedder is supplied by the
        server so unit tests holding a mock pool never load a real model.
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

        lines: list[str] = [
            f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})"
        ]
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
                lines.append(
                    f"- `[{doc_code}]` {title} (Hiệu lực từ: {eff}) — [CÒN HIỆU LỰC TOÀN BỘ]"
                )
            elif status == "PARTIALLY_MODIFIED":
                mod_txt = f" (Sửa đổi, bổ sung bởi: `[{mod_code}]`)" if mod_code else ""
                lines.append(
                    f"- `[{doc_code}]` {title} (Hiệu lực từ: {eff}) — [CÒN HIỆU LỰC MỘT PHẦN]{mod_txt}"
                )
            else:  # EXPIRED
                exp = (
                    r["expiration_date"].strftime("%d/%m/%Y")
                    if isinstance(
                        r["expiration_date"], (datetime.date, datetime.datetime)
                    )
                    else str(r["expiration_date"])
                )
                rep_txt = f" (Thay thế bởi: `[{mod_code}]`)" if mod_code else ""
                lines.append(
                    f"- `[{doc_code}]` {title} (Hiệu lực từ: {eff}, Hết hiệu lực: {exp}) — [HẾT HIỆU LỰC]{rep_txt}"
                )

        return "\n".join(lines)

    # 1. HYBRID SEARCH
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
                        metadata=_extract_metadata_dict(r["metadata"]),
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
        except (
            OSError,
            RuntimeError,
            asyncpg.PostgresError,
            TypeError,
            ValueError,
        ) as exc:
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
                issues.append(
                    f"Detected {orphan_cnt} orphan chunks without valid document FK"
                )

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
                preview_text=c.verbatim_text[:120]
                + ("..." if len(c.verbatim_text) > 120 else ""),
                char_length=c.char_length or len(c.verbatim_text),
                is_truncated=len(c.verbatim_text) > 120,
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

    # 7.1 STG GET CHUNK
    async def stg_get_chunk(self, doc_code: str, path: str) -> StgGetChunkResult:
        """Retrieves complete, untruncated chunk detail by path from staging session."""
        session = self._staging.load_session(doc_code)
        clean_path = validate_ltree_path(path)
        chunk = session.get_chunk(clean_path)
        if chunk is None:
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=f"Đoạn quy phạm '{clean_path}' không tồn tại trong phiên làm việc cho văn bản '{doc_code}'.",
                data={"doc_code": doc_code, "path": clean_path},
            )
        return StgGetChunkResult(doc_code=doc_code, chunk=chunk)

    # 7.2 STG GET RAW
    async def stg_get_raw(
        self, doc_code: str, start_line: int = 1, end_line: int = 100
    ) -> StgGetRawResult:
        """Retrieves bounded line window of raw source statutory text from staging session."""
        session = self._staging.load_session(doc_code)
        window = session.get_raw_window(start_line=start_line, end_line=end_line)
        return StgGetRawResult(
            doc_code=window.doc_code,
            start_line=window.start_line,
            end_line=window.end_line,
            total_lines=window.total_lines,
            content=window.content,
        )

    # 7.3 STG GREP
    async def stg_grep(
        self,
        doc_code: str,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        search_in: str = "ALL",
        limit: int = 50,
    ) -> StgGrepResult:
        """Executes in-memory keyword or regex search over candidate chunks in staging session."""
        session = self._staging.load_session(doc_code)
        matches = session.grep(
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            search_in=search_in,
            limit=limit,
        )
        return StgGrepResult(
            doc_code=doc_code,
            pattern=pattern,
            is_regex=is_regex,
            total_matches=len(matches),
            matches=matches,
        )

    # 8. STG PATCH
    async def stg_patch(
        self,
        doc_code: str,
        updated_chunks: list[dict[str, Any]] | None = None,
        removed_paths: list[str] | None = None,
        cascade_breadcrumbs: bool = True,
    ) -> StgPatchResult:
        """Applies surgical partial updates (deltas) or removals to candidate chunks in staging."""
        session = self._staging.patch_chunks(
            doc_code=doc_code,
            updated_chunks=updated_chunks,
            removed_paths=removed_paths,
            cascade_breadcrumbs=cascade_breadcrumbs,
            actor="AGENT",
        )
        last_diff = (
            session.mutation_history[-1].diff_payload
            if session.mutation_history and session.mutation_history[-1].diff_payload
            else {}
        )
        return StgPatchResult(
            doc_code=doc_code,
            status="SUCCESS",
            updated_count=int(
                last_diff.get("updated_count", len(updated_chunks or []))
            ),
            cascaded_count=int(last_diff.get("cascaded_count", 0)),
            removed_count=int(last_diff.get("removed_count", len(removed_paths or []))),
            total_chunks_after_patch=len(session.chunks),
            fields_modified=list(last_diff.get("fields_modified", [])),
        )

    # 9. STG ADD EDGES
    async def stg_add_edges(
        self,
        doc_code: str,
        edges: list[dict[str, Any]],
    ) -> StgAddEdgesResult:
        """Attaches and pre-commit lints relational graph edges in staging."""
        session = self._staging.add_edges(
            doc_code=doc_code,
            edges=edges,
            actor="AGENT",
        )
        return StgAddEdgesResult(
            doc_code=doc_code,
            status="SUCCESS",
            total_edges=len(session.edges),
        )

    # 10. STG REPARENT
    async def stg_reparent(
        self,
        doc_code: str,
        old_path_prefix: str,
        new_path_prefix: str,
        dry_run: bool = False,
    ) -> StgReparentResult:
        """Atomically migrates an entire statutory subtree and its edges to a new parent prefix in staging."""
        _session, result = self._staging.reparent_node(
            doc_code=doc_code,
            old_path_prefix=old_path_prefix,
            new_path_prefix=new_path_prefix,
            dry_run=dry_run,
            actor="AGENT",
        )
        return result

    # 11. STG COMMIT (Agent Staging Commit Gate)
    async def stg_commit(self, doc_code: str) -> StgCommitResult:
        """Validates staging edge referential integrity and transitions session status to AGENT_COMMITTED."""
        session = self._staging.load_session(doc_code)

        # Validate that internal edge source_path entries reference valid staged chunks
        chunk_paths = {c.path for c in session.chunks}
        for edge in session.edges:
            if edge.source_path not in chunk_paths:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=f"Invalid edge source path '{edge.source_path}': chunk path does not exist in document '{doc_code}'.",
                    data={"doc_code": doc_code, "source_path": edge.source_path},
                )

        now = datetime.datetime.now(datetime.UTC)
        session.status = StagingStatus.AGENT_COMMITTED
        session.committed_at = now
        session.updated_at = now
        session.mutation_history.append(
            StagingMutationRecord(
                actor="AGENT",
                action_type="AGENT_COMMITTED",
                description=f"Agent completed staging session review and committed for {doc_code}.",
                timestamp=now,
                diff_payload={
                    "total_chunks": len(session.chunks),
                    "total_edges": len(session.edges),
                },
            )
        )
        self._staging.save_session(session)

        return StgCommitResult(
            doc_code=session.doc_code,
            status=StagingStatus.AGENT_COMMITTED.value,
            total_chunks=len(session.chunks),
            total_edges=len(session.edges),
            committed_at=now.isoformat(),
            message=f"Phiên làm việc cho văn bản '{doc_code}' đã được chuyển sang trạng thái AGENT_COMMITTED. Dữ liệu được lưu trữ an toàn trong staging và sẵn sàng cho chuyên viên pháp lý thẩm định, phê duyệt.",
        )
