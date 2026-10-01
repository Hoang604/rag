"""Scores article-level aggregation of hybrid_search hits against the flat ranking.

    uv run python scripts/tree_fusion.py

A provision is only evidence for its article, so chunks sharing a Điều are
pooled before ranking. No parameter is tuned: the score of an article is the
sum of the fused scores of its chunks inside the top `POOL` hits.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from typing import Final

from bench import SETS, CachedEmbedder, answerable, corpus_hits, load_items

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool
from rag_eval.legal.eval.smoke_runner import GroundTruth, _check_article_match
from rag_eval.legal.mcp.tools import LegalMCPTools, SearchHit
from rag_eval.legal.schemas import address_of_path

POOL: Final = 30


def article_key(hit: SearchHit) -> tuple[str, str | None]:
    return hit.doc_code, address_of_path(hit.path).dieu


def pooled(hits: list[SearchHit], mode: str) -> list[SearchHit]:
    scores: dict[tuple[str, str | None], float] = defaultdict(float)
    best: dict[tuple[str, str | None], SearchHit] = {}
    for rank, hit in enumerate(hits, 1):
        key = article_key(hit)
        scores[key] += hit.score if mode == "sum" else 1.0 / (60 + rank)
        best.setdefault(key, hit)
    return [best[k] for k in sorted(scores, key=scores.__getitem__, reverse=True)]


def rank_of(hits: list[SearchHit], truth: GroundTruth) -> int | None:
    return next((i for i, h in enumerate(hits, 1) if _check_article_match(h, truth)), None)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sets", nargs="+", default=list(SETS), choices=list(SETS))
    args = parser.parse_args()

    tools = LegalMCPTools.build(embedding_engine=CachedEmbedder())
    corpus = await corpus_hits()
    try:
        print(f"{'set':11s} {'n':>4s} {'flat@1':>7s} {'pool@1':>7s} {'flat@3':>7s} {'pool@3':>7s}  +/-@1")
        for name in args.sets:
            items = [i for i in load_items(SETS[name]) if answerable(i.ground_truth, corpus)]
            flat: list[int | None] = []
            pool: list[int | None] = []
            for item in items:
                hits = (await tools.hybrid_search(query=item.query, limit=POOL)).hits
                flat.append(rank_of(hits, item.ground_truth))
                pool.append(rank_of(pooled(hits, "sum"), item.ground_truth))

            def at(ranks: list[int | None], k: int) -> float:
                return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)

            wins = sum(1 for a, b in zip(flat, pool, strict=True) if b == 1 and a != 1)
            losses = sum(1 for a, b in zip(flat, pool, strict=True) if a == 1 and b != 1)
            print(
                f"{name:11s} {len(items):4d} {at(flat, 1):7.1%} {at(pool, 1):7.1%}"
                f" {at(flat, 3):7.1%} {at(pool, 3):7.1%}  +{wins}/-{losses}",
                flush=True,
            )
    finally:
        await close_db_pool()
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
