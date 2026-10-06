from __future__ import annotations

import datetime
import logging
import re
import uuid
from typing import Final

import asyncpg

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.db.repositories import LegalRepository
from rag_eval.legal.errors import (
    E_AST_GROUNDING_VALIDATION,
    E_INVALID_DOCUMENT_HIERARCHY,
    LegalDomainError,
)
from rag_eval.legal.ingestion.staging.backlog import StatutoryBacklogResolver
from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.mcp.tools.embedder import QueryEmbedder
from rag_eval.legal.retrieval.reranker import LegalReranker
from rag_eval.legal.schemas.domain import (
    FinalizationState,
    GraphDirection,
    HierarchicalDirection,
)
from rag_eval.legal.schemas.retrieval import (
    RERANK_POOL,
    GraphTraverseResult,
    GrepResult,
    HierarchicalNavigateResult,
    SearchHit,
    SearchResult,
)
from rag_eval.legal.schemas.staging import (
    UnresolvedBacklogResult,
)
from rag_eval.legal.text import (
    get_vietnam_today,
    is_unaccented,
    parse_flexible_date,
    validate_ltree_path,
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


class LegalRuntimeSensors:
    """Encapsulates production database sensors with write-protected WAL routing."""

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        repo: LegalRepository | None = None,
        embedding_engine: QueryEmbedder | None = None,
        staging_manager: StagingManager | None = None,
        reranker: LegalReranker | None = None,
        rerank_by_default: bool = False,
        backlog_resolver: StatutoryBacklogResolver | None = None,
    ) -> None:
        self._pool = pool
        self._repo = repo
        self._embedding_engine = embedding_engine
        self._staging_manager = staging_manager
        self._reranker = reranker
        self._rerank_by_default = rerank_by_default
        self._backlog = backlog_resolver or StatutoryBacklogResolver(
            staging_manager=staging_manager, pool=pool
        )

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await get_db_pool()
        return self._pool

    async def _get_repo(self) -> LegalRepository:
        if self._repo is None:
            pool = await self._get_pool()
            self._repo = LegalRepository(pool)
        return self._repo

    async def _embed_query(self, query: str) -> list[float] | None:
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
        t_date = get_vietnam_today()
        if temporal_violation_date:
            parsed_d = parse_flexible_date(temporal_violation_date)
            if parsed_d is not None:
                t_date = parsed_d

        computed_vector = await self._embed_query(query)
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
                only_resolved=False,
                ts_config="simple",
            )
            if want_rerank and self._reranker is not None and hits:
                hits = await self._reranker.rerank(query, hits, top_k=limit)
            else:
                hits = hits[:limit]

            return SearchResult(
                query=query,
                total_hits=len(hits),
                hits=hits,
                violation_date=t_date.isoformat(),
                dense_is_informative=not is_unaccented(query),
                expanded_query=query,
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

    async def verbatim_grep(
        self,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        temporal_violation_date: str | None = None,
        limit: int = 20,
    ) -> GrepResult:
        parsed_date = parse_flexible_date(temporal_violation_date) if temporal_violation_date else None
        target_date = parsed_date if parsed_date is not None else get_vietnam_today()

        repo = await self._get_repo()
        hits, full_count = await repo.chunks.verbatim_grep(
            query_pattern=pattern,
            target_documents=None,
            path_prefix=None,
            only_resolved=False,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            t_violation=target_date,
            match_limit=limit,
        )

        return GrepResult(
            pattern=pattern,
            is_regex=is_regex,
            total_matches=full_count,
            returned=len(hits),
            truncated=full_count > len(hits),
            matches=hits,
        )

    async def hierarchical_navigate(
        self,
        path: str | None = None,
        chunk_id: str | None = None,
        direction: HierarchicalDirection = HierarchicalDirection.FULL_ARTICLE,
    ) -> HierarchicalNavigateResult:
        repo = await self._get_repo()
        origin_path: str
        if chunk_id:
            try:
                c_uuid = uuid.UUID(chunk_id)
            except ValueError as err:
                raise LegalDomainError(
                    error_code=E_INVALID_DOCUMENT_HIERARCHY,
                    message=f"Định danh chunk_id '{chunk_id}' không phải là UUID hợp lệ.",
                ) from err
            found_chunk = await repo.chunks.get_by_id(c_uuid)
            if not found_chunk:
                raise LegalDomainError(
                    error_code=E_INVALID_DOCUMENT_HIERARCHY,
                    message=f"Không tìm thấy đoạn quy phạm tương ứng với chunk_id='{chunk_id}'.",
                )
            origin_path = found_chunk.path
        elif path:
            origin_path = validate_ltree_path(path)
        else:
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message="Bắt buộc phải cung cấp 'path' (chuỗi ltree) hoặc 'chunk_id' (UUID) để điều hướng.",
            )

        nodes = await repo.chunks.navigate_hierarchy(
            anchor_path=origin_path,
            direction=direction,
        )
        dir_val = direction.value
        return HierarchicalNavigateResult(
            anchor_path=origin_path,
            direction=dir_val,
            total_nodes=len(nodes),
            nodes=nodes,
        )

    async def graph_traverse(
        self,
        source_path: str,
        direction: GraphDirection = "OUTGOING",
        max_depth: int = 2,
    ) -> GraphTraverseResult:
        repo = await self._get_repo()
        clean_path = validate_ltree_path(source_path)
        steps = await repo.graph.traverse(
            source=clean_path,
            nav_direction=direction,
            depth_limit=max_depth,
        )
        return GraphTraverseResult(
            source_path=source_path,
            total_paths=len(steps),
            paths=steps,
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

    async def corpus_backlog_poll(
        self,
        finalization_state: FinalizationState | None = None,
        doc_code: str | None = None,
        limit: int = 50,
    ) -> UnresolvedBacklogResult:
        """Polls statutory provisions with unfinalized status or open caveats."""
        return await self._backlog.resolve_backlog(
            doc_code=doc_code or None,
            finalization_state=finalization_state,
            limit=limit,
        )


