"""Scores each retrieval component separately across all three evaluation sets.

A single accuracy figure cannot tell a fix that generalises from one that
memorises the set it was written against. This can: it reports every component
on the set it was built for (tuned), on the set spent designing the second facet
(dev), and on the set retrieval work has never been allowed to look at (test).

A change that lifts `tuned` and leaves `test` flat has bought nothing. A change
that lifts `tuned` and lowers `dev` or `test` has cost something.
"""

from __future__ import annotations

import argparse
import asyncio
import json
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
from rag_eval.legal.schemas import get_vietnam_today
from rag_eval.legal.text import is_unaccented

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SETS = {
    "tuned": FIXTURES / "smoke_queries.jsonl",
    "dev": FIXTURES / "smoke_queries_holdout.jsonl",
    "test": FIXTURES / "smoke_queries_test.jsonl",
    # 200 agent-written questions at clause level, added in Sprint 2. Large
    # enough that a five-point move is ten questions rather than two.
    "qrels200": FIXTURES / "qrels_dev.jsonl",
}

# (label, use lexicon, use vehicle facet, use provision-role facet)
CONFIGS: tuple[tuple[str, bool, bool, bool], ...] = (
    ("baseline", False, False, False),
    ("+ lexicon", True, False, False),
    ("+ vehicle facet", False, True, False),
    ("+ role facet", False, False, True),
    ("both facets", False, True, True),
    ("full", True, True, True),
)

SQL = (
    "SELECT chunk_id, doc_code, doc_title, path, verbatim_text, contextualized_text,"
    " metadata, effective_date, expiration_date, rrf_score"
    " FROM hybrid_search($1,$2::vector,$3::date,$4::int,60,$5,$6,$7,$8)"
)


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


async def _score(
    conn: Any,
    items: list[dict[str, Any]],
    vectors: dict[str, list[float]],
    today: Any,
    use_lexicon: bool,
    use_vehicle: bool,
    use_role: bool,
    limit: int,
) -> dict[str, float]:
    hit1 = hit3 = hit5 = exact = 0
    reciprocal = 0.0
    for item in items:
        query = item["query"]
        rows = await conn.fetch(
            SQL,
            expand_query(query) if use_lexicon else query,
            vectors[query],
            today,
            limit,
            classify_query(query) if use_vehicle else None,
            classify_intent(query) if use_role else None,
            phrase_variants(query) if use_lexicon else None,
            0.2 if is_unaccented(query) else 1.0,
        )
        truth = GroundTruth.model_validate(item["ground_truth"])
        best = 0.0
        is_exact = False
        for rank, row in enumerate(rows, start=1):
            hit = _as_hit(row)
            if not _check_article_match(hit, truth):
                continue
            if rank == 1:
                hit1 += 1
            if best == 0.0:
                if rank <= 3:
                    hit3 += 1
                if rank <= 5:
                    hit5 += 1
                best = 1.0 / rank
            if _check_citation_exactness(hit, truth):
                is_exact = True
        reciprocal += best
        exact += 1 if is_exact else 0

    total = len(items)
    return {
        "hit1": hit1 / total,
        "hit3": hit3 / total,
        "hit5": hit5 / total,
        "mrr": reciprocal / total,
        "exact": exact / total,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--full-only",
        action="store_true",
        help="Score only the shipped configuration, skipping the ablation rows.",
    )
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
        vectors: dict[str, list[float]] = {}
        for item in items:
            vectors[item["query"]] = await embedder.embed_query(item["query"]) or []
        loaded[name] = (items, vectors)

    configs = CONFIGS[-1:] if args.full_only else CONFIGS
    header = "".join(f"{name:>26s}" for name in SETS)
    print(f"{'configuration':22s}{header}")
    print("-" * (22 + 26 * len(SETS)))

    async with pool.acquire() as conn:
        for label, use_lexicon, use_vehicle, use_role in configs:
            cells: list[str] = []
            for name in SETS:
                items, vectors = loaded[name]
                scores = await _score(
                    conn,
                    items,
                    vectors,
                    today,
                    use_lexicon,
                    use_vehicle,
                    use_role,
                    args.limit,
                )
                cells.append(
                    f"{scores['hit1'] * 100:5.1f} /{scores['hit3'] * 100:6.1f} / {scores['mrr']:.3f}"
                )
            print(f"{label:22s}" + "".join(f"{cell:>26s}" for cell in cells))

    print("\nHit@1 / Hit@3 / MRR per set.")
    print("Quote `test`. `tuned` and `dev` were both spent tuning retrieval.")
    await close_db_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
