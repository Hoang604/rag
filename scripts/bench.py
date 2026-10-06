"""Scores retrieval on the fixture sets: dense, sparse, hybrid, and hybrid with rerank.

    uv run python scripts/bench.py
    uv run python scripts/bench.py --sets holdout colloquial --modes hybrid rerank
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

import asyncpg

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.eval.smoke_runner import (
    GroundTruth,
    SmokeQueryItem,
    _check_article_match,
    _check_citation_exactness,
)
from rag_eval.legal.mcp.tools import (
    LegalMCPTools,
    SearchHit,
    SentenceTransformerQueryEmbedder,
)
from rag_eval.legal.text import fold_diacritics, get_vietnam_today

ROOT: Final = Path(__file__).resolve().parents[1]
FIXTURES: Final = ROOT / "tests" / "fixtures"
RUNS: Final = ROOT / "experiments" / "runs"

SETS: Final = {
    "dev": FIXTURES / "qrels_dev.jsonl",
    "holdout": FIXTURES / "qrels_holdout.jsonl",
    "colloquial": FIXTURES / "qrels_colloquial.jsonl",
    "coverage": FIXTURES / "qrels_coverage.jsonl",
    "tables": FIXTURES / "qrels_tables.jsonl",
    "clause": FIXTURES / "qrels_clause.jsonl",
}
MODES: Final = ("dense", "sparse", "hybrid", "rerank")
DEPTH: Final = 10

SQL: Final = """
SELECT chunk_id, doc_code, doc_title, path, verbatim_text, contextualized_text,
       metadata, effective_date, expiration_date, rrf_score, sparse_rank, dense_similarity
FROM hybrid_search($1, $2::vector, $3::date, $4::int, 60, NULL)
"""


class CachedEmbedder:
    def __init__(self) -> None:
        self._inner = SentenceTransformerQueryEmbedder()
        self._cache: dict[str, list[float] | None] = {}

    async def embed_query(self, query: str) -> list[float] | None:
        if query not in self._cache:
            self._cache[query] = await self._inner.embed_query(query)
        return self._cache[query]


@dataclass
class Outcome:
    query_id: str
    query: str
    article_rank: int | None
    exact_rank: int | None
    top_path: str | None
    latency_ms: float


@dataclass
class ModeScore:
    mode: str
    outcomes: list[Outcome] = field(default_factory=list)

    def hit(self, k: int, exact: bool = False) -> float:
        ranks = [o.exact_rank if exact else o.article_rank for o in self.outcomes]
        return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)

    def mrr(self, exact: bool = False) -> float:
        ranks = [o.exact_rank if exact else o.article_rank for o in self.outcomes]
        return sum(1.0 / r for r in ranks if r is not None) / len(ranks)

    def latency(self) -> float:
        return sum(o.latency_ms for o in self.outcomes) / len(self.outcomes)


def load_items(path: Path) -> list[SmokeQueryItem]:
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    return [
        SmokeQueryItem.model_validate(
            {
                "id": f"{path.stem}:{index}",
                "domain": row.get("style", ""),
                **row,
            }
        )
        for index, row in enumerate(rows)
        if row.get("ground_truth")
    ]


async def corpus_hits() -> list[SearchHit]:
    pool = await get_db_pool()
    rows = await pool.fetch(
        "SELECT d.doc_code, c.path::text AS path FROM chunks c "
        "JOIN documents d ON d.id = c.document_id"
    )
    return [
        SearchHit(
            doc_code=str(r["doc_code"]),
            doc_title="",
            path=str(r["path"]),
            start_line=1,
            end_line=1,
            verbatim_text="",
            contextualized_text="",
            effective_date=get_vietnam_today(),
            score=0.0,
        )
        for r in rows
    ]


def answerable(truth: GroundTruth, corpus: list[SearchHit]) -> bool:
    return any(_check_article_match(hit, truth) for hit in corpus)


def first_rank(hits: list[SearchHit], truth: GroundTruth, exact: bool) -> int | None:
    check = _check_citation_exactness if exact else _check_article_match
    return next((i for i, h in enumerate(hits, 1) if check(h, truth)), None)


def to_hit(row: asyncpg.Record) -> SearchHit:
    return SearchHit(
        doc_code=str(row["doc_code"]),
        doc_title=str(row["doc_title"]),
        path=str(row["path"]),
        start_line=int(row["start_line"]) if "start_line" in row and row["start_line"] is not None else 1,
        end_line=int(row["end_line"]) if "end_line" in row and row["end_line"] is not None else 1,
        verbatim_text=str(row["verbatim_text"]),
        contextualized_text=str(row["contextualized_text"]),
        effective_date=str(row["effective_date"]),
        score=float(row["rrf_score"]),
    )


async def run_mode(
    mode: str, item: SmokeQueryItem, tools: LegalMCPTools, embedder: CachedEmbedder
) -> tuple[list[SearchHit], float]:
    started = time.perf_counter()
    if mode in ("hybrid", "rerank"):
        result = await tools.hybrid_search(
            query=item.query, limit=DEPTH, rerank=mode == "rerank"
        )
        hits = result.hits
    else:
        vector = await embedder.embed_query(item.query) if mode == "dense" else None
        text = item.query if mode == "sparse" else ""
        pool = await get_db_pool()
        rows = await pool.fetch(SQL, text, vector, get_vietnam_today(), DEPTH)
        hits = [to_hit(r) for r in rows]
    return hits, (time.perf_counter() - started) * 1000.0


def paired(base: ModeScore, other: ModeScore) -> tuple[int, int]:
    wins = losses = 0
    for a, b in zip(base.outcomes, other.outcomes, strict=True):
        base_ok = a.article_rank == 1
        other_ok = b.article_rank == 1
        wins += other_ok and not base_ok
        losses += base_ok and not other_ok
    return wins, losses


def report(name: str, n: int, dropped: int, scores: dict[str, ModeScore]) -> str:
    title = f"\n== {name}: {n} câu chấm được"
    if dropped:
        title += f", bỏ {dropped} câu có đáp án không còn trong kho"
    header = (
        f"{'mode':8s} {'@1':>6s} {'@3':>6s} {'@5':>6s} {'@10':>6s} {'MRR':>6s}"
        f" | {'K/Đ@1':>6s} {'K/ĐMRR':>6s} | {'ms':>6s} | vs hybrid @1"
    )
    lines = [title, header]
    base = scores.get("hybrid")
    for mode, score in scores.items():
        versus = ""
        if base is not None and mode != "hybrid":
            wins, losses = paired(base, score)
            versus = f"+{wins} / -{losses}"
        lines.append(
            f"{mode:8s} {score.hit(1):6.1%} {score.hit(3):6.1%} {score.hit(5):6.1%}"
            f" {score.hit(10):6.1%} {score.mrr():6.3f}"
            f" | {score.hit(1, True):6.1%} {score.mrr(True):6.3f}"
            f" | {score.latency():6.0f} | {versus}"
        )
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sets", nargs="+", default=list(SETS), choices=list(SETS))
    parser.add_argument("--modes", nargs="+", default=list(MODES), choices=MODES)
    parser.add_argument("--tag", default=time.strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--unaccented", action="store_true")
    args = parser.parse_args()

    from rag_eval.legal.retrieval.reranker import CrossEncoderReranker

    embedder = CachedEmbedder()
    reranker = CrossEncoderReranker() if "rerank" in args.modes else None
    tools = LegalMCPTools.build(embedding_engine=embedder, reranker=reranker)
    corpus = await corpus_hits()
    RUNS.mkdir(parents=True, exist_ok=True)

    printed: list[str] = []
    dump: dict[str, dict[str, list[dict[str, object]]]] = {}
    try:
        for name in args.sets:
            items = load_items(SETS[name])
            if args.unaccented:
                items = [
                    i.model_copy(update={"query": fold_diacritics(i.query)}) for i in items
                ]
            kept = [i for i in items if answerable(i.ground_truth, corpus)]
            scores = {mode: ModeScore(mode) for mode in args.modes}
            for item in kept:
                for mode in args.modes:
                    hits, elapsed = await run_mode(mode, item, tools, embedder)
                    scores[mode].outcomes.append(
                        Outcome(
                            query_id=item.id,
                            query=item.query,
                            article_rank=first_rank(hits, item.ground_truth, False),
                            exact_rank=first_rank(hits, item.ground_truth, True),
                            top_path=hits[0].path if hits else None,
                            latency_ms=elapsed,
                        )
                    )
            block = report(name, len(kept), len(items) - len(kept), scores)
            print(block, flush=True)
            printed.append(block)
            dump[name] = {
                mode: [asdict(o) for o in score.outcomes]
                for mode, score in scores.items()
            }
    finally:
        await close_db_pool()

    (RUNS / f"{args.tag}.txt").write_text("\n".join(printed) + "\n", encoding="utf-8")
    (RUNS / f"{args.tag}.json").write_text(
        json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
