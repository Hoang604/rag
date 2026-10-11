from __future__ import annotations

import datetime
import logging
import re
from typing import Final

import asyncpg

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.db.repositories import LegalRepository
from rag_eval.legal.errors import (
    E_AST_GROUNDING_VALIDATION,
    E_INVALID_PARAMS,
    LegalDomainError,
)
from rag_eval.legal.mcp.tools.embedder import QueryEmbedder
from rag_eval.legal.retrieval.amendments import AmendmentIndex
from rag_eval.legal.retrieval.reranker import LegalReranker
from rag_eval.legal.schemas.domain import (
    GraphDirection,
    StatutoryRelationType,
)
from rag_eval.legal.schemas.retrieval import (
    RERANK_POOL,
    GraphStep,
    GraphTraverseResult,
    HierarchicalNavigateResult,
    LegalSearchResult,
    ProvisionMatch,
    SearchHit,
    SearchResult,
    documents_of,
)
from rag_eval.legal.text import (
    LTREE_PATH_REGEX,
    get_vietnam_today,
    is_unaccented,
    parse_flexible_date,
)

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


def _violation_date(raw: str | None) -> datetime.date:
    if not raw:
        return get_vietnam_today()
    message = f"temporal_violation_date không đọc được: '{raw}' (dùng YYYY-MM-DD hoặc 'ngày DD tháng MM năm YYYY')"
    try:
        parsed = parse_flexible_date(raw)
    except ValueError as exc:
        raise LegalDomainError(error_code=E_INVALID_PARAMS, message=message) from exc
    if parsed is None:
        raise LegalDomainError(error_code=E_INVALID_PARAMS, message=message)
    return parsed


def _clean_path(raw: str, field: str) -> str:
    if not LTREE_PATH_REGEX.match(raw):
        raise LegalDomainError(
            error_code=E_INVALID_PARAMS,
            message=f"{field} không phải đường dẫn phân cấp hợp lệ: '{raw}' (chép nguyên văn trường path của kết quả, ví dụ '168_2024_nd_cp.c_ii.s_1.a_6.c_9')",
        )
    return raw


class LegalRuntimeSensors:
    """Read-only DB sensors over the ingested statutory corpus."""

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        repo: LegalRepository | None = None,
        embedding_engine: QueryEmbedder | None = None,
        reranker: LegalReranker | None = None,
        rerank_by_default: bool = False,
    ) -> None:
        self._pool = pool
        self._repo = repo
        self._embedding_engine = embedding_engine
        self._reranker = reranker
        self._rerank_by_default = rerank_by_default
        self._amendments: AmendmentIndex | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await get_db_pool()
        return self._pool

    async def _get_repo(self) -> LegalRepository:
        if self._repo is None:
            pool = await self._get_pool()
            self._repo = LegalRepository(pool)
        return self._repo

    async def annotate_amendments(
        self, hits: list[SearchHit], on_date: datetime.date | None = None
    ) -> list[SearchHit]:
        try:
            if self._amendments is None:
                self._amendments = await AmendmentIndex.load(await self._get_pool())
        except (OSError, RuntimeError, asyncpg.PostgresError) as exc:
            logger.warning("Amendment index unavailable, results are not annotated: %s", exc)
            return hits
        return self._amendments.annotate(hits, on_date or get_vietnam_today())

    async def _embed_query(self, query: str) -> list[float] | None:
        if self._embedding_engine is None:
            logger.warning(
                "No query embedder configured; hybrid_search is running sparse-only"
            )
            return None
        return await self._embedding_engine.embed_query(query)

    async def build_dynamic_corpus_manifest(
        self, as_of_date: datetime.date | None = None
    ) -> str:
        target_date = as_of_date or get_vietnam_today()
        date_str = target_date.strftime("%d/%m/%Y")
        try:
            repo = await self._get_repo()
            docs = await repo.documents.list_active()
            if not docs:
                return ""
            lines = [f"## DANH MỤC VĂN BẢN TRONG CƠ SỞ DỮ LIỆU (TÍNH ĐẾN: {date_str})"]
            for r in docs:
                exp = f", hết hiệu lực: {r.expiration_date}" if r.expiration_date else ""
                lines.append(f"- **{r.doc_code}**: {r.title} (Hiệu lực: {r.effective_date}{exp})")
            return "\n".join(lines)
        except (OSError, RuntimeError, asyncpg.PostgresError, LegalDomainError) as exc:
            logger.warning("Không thể tạo danh mục văn bản động do lỗi kết nối cơ sở dữ liệu: %s", exc)
            return ""

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
        t_date = _violation_date(temporal_violation_date)

        computed_vector = None if is_unaccented(query) else await self._embed_query(query)
        vector_param = computed_vector

        want_rerank = self._rerank_by_default if rerank is None else rerank
        want_rerank = want_rerank and self._reranker is not None
        if want_rerank and is_unaccented(query):
            want_rerank = False
        fetch_limit = max(limit, rerank_pool) if want_rerank else limit

        try:
            repo = await self._get_repo()
            hits = await repo.chunks.hybrid_search(
                query_text=query,
                query_vector=vector_param,
                t_violation=t_date,
                match_limit=fetch_limit,
                rrf_k=60,
                doc_codes=doc_codes or None,
                path_prefix=path_prefix or None,
            )
            if want_rerank and self._reranker is not None and hits:
                hits = await self._reranker.rerank(query, hits, top_k=limit)
            else:
                hits = hits[:limit]
            hits = await self.annotate_amendments(hits, t_date)

            return SearchResult(
                query=query,
                hits=hits,
                violation_date=t_date.isoformat(),
                dense_is_informative=not is_unaccented(query),
            )
        except (
            OSError,
            RuntimeError,
            asyncpg.PostgresError,
            TypeError,
            ValueError,
            LegalDomainError,
        ) as exc:
            logger.error("hybrid_search failed: %s", exc)
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=f"Hybrid search execution error: {exc}",
            ) from exc

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
        t_date = _violation_date(temporal_violation_date)
        clean_prefix = _clean_path(path_prefix, "path_prefix") if path_prefix else None
        semantic = await self.hybrid_search(
            query=query,
            temporal_violation_date=t_date.isoformat(),
            limit=limit,
            rerank=rerank,
            doc_codes=doc_codes,
            path_prefix=clean_prefix,
        )
        repo = await self._get_repo()
        verbatim, verbatim_total = await repo.chunks.verbatim_grep(
            query_pattern=pattern,
            target_documents=doc_codes,
            path_prefix=clean_prefix,
            is_regex=is_regex,
            t_violation=t_date,
            match_limit=limit,
        )
        verbatim = await self.annotate_amendments(verbatim, t_date)
        semantic_paths = [hit.path for hit in semantic.hits]
        matching = await repo.chunks.paths_matching_pattern(semantic_paths, pattern, is_regex)
        seen = set(semantic_paths)

        return LegalSearchResult(
            query=query,
            pattern=pattern,
            violation_date=t_date,
            documents=documents_of([*semantic.hits, *verbatim]),
            both=[ProvisionMatch.from_hit(h) for h in semantic.hits if h.path in matching],
            semantic_only=[ProvisionMatch.from_hit(h) for h in semantic.hits if h.path not in matching],
            verbatim_only=[ProvisionMatch.from_hit(h) for h in verbatim if h.path not in seen],
            verbatim_total=verbatim_total,
            verbatim_truncated=verbatim_total > len(verbatim),
        )

    async def hierarchical_navigate(self, path: str, limit: int = 100) -> HierarchicalNavigateResult:
        clean_path = _clean_path(path, "path")
        repo = await self._get_repo()
        hits, total = await repo.chunks.provisions_under(clean_path, limit)
        if not hits:
            raise LegalDomainError(
                error_code=E_INVALID_PARAMS,
                message=f"Không có đoạn quy phạm nào tại hoặc dưới đường dẫn '{clean_path}'.",
            )
        hits = await self.annotate_amendments(hits)
        return HierarchicalNavigateResult.from_hits(clean_path, hits, total)

    async def graph_traverse(
        self,
        source_path: str,
        direction: GraphDirection = "OUTGOING",
        max_depth: int = 2,
        filter_relations: list[StatutoryRelationType] | None = None,
    ) -> GraphTraverseResult:
        clean_path = _clean_path(source_path, "source_path")
        repo = await self._get_repo()
        steps = await repo.graph.traverse(
            source=clean_path,
            nav_direction=direction,
            depth_limit=max_depth,
            filter_relations=[r.value for r in filter_relations] if filter_relations else None,
        )
        reached = await repo.chunks.get_hits_by_paths([step.to_path for step in steps])
        reached = await self.annotate_amendments(reached)
        by_path = {hit.path: hit for hit in reached}
        return GraphTraverseResult(
            source_path=clean_path,
            documents=documents_of(reached),
            steps=[
                GraphStep(
                    from_path=step.from_path,
                    relation_type=step.relation_type,
                    citation_text=step.citation_text,
                    depth=step.depth,
                    to=ProvisionMatch.from_hit(by_path[step.to_path]),
                )
                for step in steps
            ],
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
        repo = await self._get_repo()
        rows = await repo.chunks.get_sibling_windows(sorted(parents))

        siblings: dict[str, list[tuple[int, str]]] = {}
        for p_str, text_str in rows:
            match = _WINDOW_SUFFIX.search(p_str)
            parent = _WINDOW_SUFFIX.sub("", p_str)
            siblings.setdefault(parent, []).append(
                (int(match.group(1)) if match else 0, text_str)
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


