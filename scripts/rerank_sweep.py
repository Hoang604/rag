"""Measures whether cross-encoder reranking earns its place, and at what depth.

A reranker can only reorder what retrieval already found, so it cannot repair
recall -- but it can spend it, by moving a right answer out of the window. So
Hit@5 is reported beside Hit@1 at every setting, at both granularities, on
every split.

Candidates are fetched once at the deepest pool and sliced, so every
configuration is compared against identical retrieval, and each ordering is
scored at both granularities, because reranking is the expensive half and
scoring is free.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.eval.smoke_runner import (
    GroundTruth,
    _check_article_match,
    _check_citation_exactness,
)
from rag_eval.legal.ingestion.facets import classify_intent, classify_query
from rag_eval.legal.mcp.tools import SearchHit, SentenceTransformerQueryEmbedder
from rag_eval.legal.retrieval.lexicon import expand_query, phrase_variants
from rag_eval.legal.retrieval.reranker import CrossEncoderReranker
from rag_eval.legal.schemas import get_vietnam_today
from rag_eval.legal.text import is_unaccented

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SETS = {
    "tuned": FIXTURES / "smoke_queries.jsonl",
    "dev": FIXTURES / "smoke_queries_holdout.jsonl",
    "test": FIXTURES / "smoke_queries_test.jsonl",
    "qrels200": FIXTURES / "qrels_dev.jsonl",
}

SQL = (
    "SELECT chunk_id, doc_code, doc_title, path, verbatim_text, contextualized_text,"
    " metadata, effective_date, expiration_date, rrf_score"
    " FROM hybrid_search($1,$2::vector,$3::date,$4::int,60,$5,$6,$7,$8)"
)

Scored = list[tuple[list[SearchHit], GroundTruth]]


def _as_hit(row: Any) -> SearchHit:
    return SearchHit(
        chunk_id=str(row["chunk_id"]),
        doc_code=str(row["doc_code"]),
        doc_title=str(row["doc_title"]),
        path=str(row["path"]),
        verbatim_text=str(row["verbatim_text"]),
        contextualized_text=str(row["contextualized_text"]),
        metadata={},
        effective_date=str(row["effective_date"]),
        expiration_date=None,
        score=float(row["rrf_score"]),
    )


def _measure(
    ranked: list[SearchHit], truth: GroundTruth, strict: bool
) -> tuple[int, int, float]:
    matches = _check_citation_exactness if strict else _check_article_match
    for rank, hit in enumerate(ranked[:5], start=1):
        if matches(hit, truth):
            return (1 if rank == 1 else 0, 1, 1.0 / rank)
    return (0, 0, 0.0)


def _cell(rows: Scored, strict: bool) -> str:
    hit1 = hit5 = 0
    mrr = 0.0
    for ranked, truth in rows:
        a, b, c = _measure(ranked, truth, strict)
        hit1 += a
        hit5 += b
        mrr += c
    n = len(rows) or 1
    return f"{hit1 / n * 100:5.1f} /{hit5 / n * 100:6.1f} / {mrr / n:.3f}"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pools", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--blends", type=float, nargs="+", default=[1.0, 0.5])
    # 512 makes every pair a quadratic-attention worst case: it turned a
    # 15-minute sweep into an hour with nothing to show. A hierarchy prefix
    # plus one clause fits inside 256.
    parser.add_argument("--max-length", type=int, default=256)
    args = parser.parse_args()

    pool = await get_db_pool()
    embedder = SentenceTransformerQueryEmbedder()
    today = get_vietnam_today()

    loaded: dict[str, tuple[list[dict[str, Any]], dict[str, list[float]]]] = {}
    for name, path in SETS.items():
        items = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        vectors = {
            i["query"]: (await embedder.embed_query(i["query"]) or []) for i in items
        }
        loaded[name] = (items, vectors)

    reranker = CrossEncoderReranker(max_length=args.max_length)
    started = time.perf_counter()
    await reranker.warm()
    print(f"Tải cross-encoder: {time.perf_counter() - started:.0f}s", flush=True)

    results: dict[str, dict[str, Scored]] = {}
    deepest = max(max(args.pools), 5)

    async with pool.acquire() as conn:
        candidates: dict[str, dict[str, list[SearchHit]]] = {}
        for name in SETS:
            items, vectors = loaded[name]
            per_set: dict[str, list[SearchHit]] = {}
            for item in items:
                query = item["query"]
                rows = await conn.fetch(
                    SQL,
                    expand_query(query),
                    vectors[query],
                    today,
                    deepest,
                    classify_query(query),
                    classify_intent(query),
                    phrase_variants(query),
                    0.2 if is_unaccented(query) else 1.0,
                )
                per_set[query] = [_as_hit(r) for r in rows]
            candidates[name] = per_set
        print("Đã lấy candidate cho cả 4 tập", flush=True)

    results["không rerank"] = {
        name: [
            (
                candidates[name][i["query"]][:5],
                GroundTruth.model_validate(i["ground_truth"]),
            )
            for i in loaded[name][0]
        ]
        for name in SETS
    }

    for pool_size in args.pools:
        for blend in args.blends:
            reranker.blend = blend
            label = f"rerank top{pool_size} b={blend:g}"
            started = time.perf_counter()
            per_label: dict[str, Scored] = {}
            for name in SETS:
                rows: Scored = []
                for item in loaded[name][0]:
                    hits = candidates[name][item["query"]][:pool_size]
                    ranked = await reranker.rerank(item["query"], hits, top_k=5)
                    rows.append(
                        (ranked, GroundTruth.model_validate(item["ground_truth"]))
                    )
                per_label[name] = rows
            results[label] = per_label
            print(
                f"  {label} xong trong {time.perf_counter() - started:.0f}s", flush=True
            )

    header = "".join(f"{n:>26s}" for n in SETS)
    for strict in (False, True):
        print(f"\n=== Mức chấm: {'đúng Khoản/Điểm' if strict else 'đúng Điều'} ===")
        print(f"{'cấu hình':24s}{header}")
        print("-" * (24 + 26 * len(SETS)))
        for label, per_set in results.items():
            cells = [_cell(per_set[name], strict) for name in SETS]
            print(f"{label:24s}" + "".join(f"{c:>26s}" for c in cells))

    print("\nHit@1 / Hit@5 / MRR. Trích dẫn cột `test`.")
    await close_db_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
