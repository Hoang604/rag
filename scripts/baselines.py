"""Scores each retrieval mode on its own, so the hybrid has something to beat.

`ablation.py` answers "what does each ranking signal add to the hybrid". This
answers the question underneath it: is the hybrid worth building at all. Both
are needed, and only this one can say whether the dense half, the sparse half,
or their fusion is carrying the system.

Five modes, all sharing the temporal filter so the comparison is about
retrieval and nothing else:

  grep    trigram similarity over the statutory text. The naive baseline a
          reviewer would reach for first.
  sparse  the text index alone, ranked by ts_rank.
  dense   cosine over the embeddings alone.
  hybrid  RRF over both, with every facet, expansion and bonus switched off.
  full    what ships.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.eval.smoke_runner import GroundTruth, _check_article_match
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
}

_LIVE = (
    "c.effective_date <= $2 AND (c.expiration_date IS NULL OR c.expiration_date > $2)"
)

# Ranked by trigram similarity against the raw question. This is what "just
# grep it" amounts to once the question is a sentence rather than a phrase.
SQL_GREP = f"""
SELECT d.doc_code, d.title AS doc_title, c.path::text AS path, c.verbatim_text,
       c.contextualized_text, c.effective_date
FROM chunks c JOIN documents d ON d.id = c.document_id
WHERE {_LIVE}
ORDER BY similarity(c.verbatim_text, $1) DESC
LIMIT $3
"""

SQL_DENSE = f"""
SELECT d.doc_code, d.title AS doc_title, c.path::text AS path, c.verbatim_text,
       c.contextualized_text, c.effective_date
FROM chunks c JOIN documents d ON d.id = c.document_id
WHERE {_LIVE} AND c.embedding IS NOT NULL
ORDER BY c.embedding <=> $1::vector
LIMIT $3
"""

# plainto_tsquery ANDs every lexeme, and a whole question almost never has all
# of them in one clause -- scored that way the text index returns nothing at all
# and the comparison becomes a straw man. OR semantics with ts_rank is the fair
# reading of "the sparse side, alone".
SQL_SPARSE = f"""
WITH q AS (
    SELECT NULLIF(
        replace(plainto_tsquery('vietnamese_legal', $1)::text, ' & ', ' | '), ''
    )::tsquery AS ts
)
SELECT d.doc_code, d.title AS doc_title, c.path::text AS path, c.verbatim_text,
       c.contextualized_text, c.effective_date
FROM chunks c JOIN documents d ON d.id = c.document_id, q
WHERE {_LIVE} AND q.ts IS NOT NULL AND c.tsv_content @@ q.ts
ORDER BY ts_rank(c.tsv_content, q.ts, 32) DESC
LIMIT $3
"""

SQL_FUSED = (
    "SELECT doc_code, doc_title, path, verbatim_text, contextualized_text,"
    " effective_date FROM hybrid_search($1,$2::vector,$3::date,$4::int,60,$5,$6,$7,$8)"
)


def _as_hit(row: Any) -> SearchHit:
    return SearchHit(
        chunk_id="",
        doc_code=str(row["doc_code"]),
        doc_title=str(row["doc_title"]),
        path=str(row["path"]),
        verbatim_text=str(row["verbatim_text"]),
        contextualized_text=str(row["contextualized_text"]),
        metadata={},
        effective_date=str(row["effective_date"]),
        expiration_date=None,
        score=0.0,
    )


async def _fetch(
    conn: Any, mode: str, query: str, vector: list[float], today: Any, limit: int
) -> list[Any]:
    if mode == "grep":
        return await conn.fetch(SQL_GREP, query, today, limit)
    if mode == "sparse":
        return await conn.fetch(SQL_SPARSE, query, today, limit)
    if mode == "dense":
        return await conn.fetch(SQL_DENSE, vector, today, limit)
    if mode == "hybrid":
        # Fusion only: no lexicon, no facets, no phrase bonus, dense untouched.
        return await conn.fetch(
            SQL_FUSED, query, vector, today, limit, None, None, None, 1.0
        )
    return await conn.fetch(
        SQL_FUSED,
        expand_query(query),
        vector,
        today,
        limit,
        classify_query(query),
        classify_intent(query),
        phrase_variants(query),
        0.2 if is_unaccented(query) else 1.0,
    )


MODES = ("grep", "sparse", "dense", "hybrid", "full")


async def _score(
    conn: Any,
    mode: str,
    items: list[dict[str, Any]],
    vectors: dict[str, list[float]],
    today: Any,
    limit: int,
) -> dict[str, float]:
    hit1 = hit3 = hit5 = 0
    reciprocal = 0.0
    for item in items:
        query = item["query"]
        rows = await _fetch(conn, mode, query, vectors[query], today, limit)
        truth = GroundTruth.model_validate(item["ground_truth"])
        for rank, row in enumerate(rows, start=1):
            if not _check_article_match(_as_hit(row), truth):
                continue
            if rank == 1:
                hit1 += 1
            if rank <= 3:
                hit3 += 1
            if rank <= 5:
                hit5 += 1
            reciprocal += 1.0 / rank
            break
    total = len(items) or 1
    return {
        "hit1": hit1 / total,
        "hit3": hit3 / total,
        "hit5": hit5 / total,
        "mrr": reciprocal / total,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=5)
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

    header = "".join(f"{name:>26s}" for name in SETS)
    print(f"{'chế độ truy hồi':22s}{header}")
    print("-" * (22 + 26 * len(SETS)))

    async with pool.acquire() as conn:
        for mode in MODES:
            cells: list[str] = []
            for name in SETS:
                items, vectors = loaded[name]
                s = await _score(conn, mode, items, vectors, today, args.limit)
                cells.append(
                    f"{s['hit1'] * 100:5.1f} /{s['hit5'] * 100:6.1f} / {s['mrr']:.3f}"
                )
            print(f"{mode:22s}" + "".join(f"{cell:>26s}" for cell in cells))

    print("\nHit@1 / Hit@5 / MRR. Trích dẫn cột `test`.")
    await close_db_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
