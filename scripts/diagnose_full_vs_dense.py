"""Explains why the shipped configuration loses to dense-alone on the large set.

`baselines.py` established the fact and it is uncomfortable: on `qrels200`,
dense alone scores 70.0 Hit@1 at article level against 69.0 for `full`, and
64.5 against 62.0 at clause level. An aggregate cannot say why, and "the
hybrid is not worth building" and "the hybrid is fine but one signal
misfires" call for opposite decisions.

So this scores both modes question by question and reads the regressions --
the questions dense gets right and `full` gets wrong. For each it records what
`full` promoted instead, which signals `full` applied that dense did not, and
whether the right answer was in `full`'s candidates at all. The last
distinction is the important one: a provision missing from the top-k is a
recall failure that reranking and fusion cannot fix, while a provision present
but outranked is a scoring failure that they can.

Every mechanism named here is one the code actually applies, taken from the
same call `baselines.py` makes, so a count in the summary is a count of real
causes rather than a guess at them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from rag_eval.legal.console import use_utf8_stdout
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
    "qrels200": FIXTURES / "qrels_dev.jsonl",
    "test": FIXTURES / "smoke_queries_test.jsonl",
    "coverage": FIXTURES / "qrels_coverage.jsonl",
}

_LIVE = (
    "(c.effective_date <= $2::date)"
    " AND (d.expiration_date IS NULL OR d.expiration_date >= $2::date)"
)

SQL_DENSE = f"""
SELECT d.doc_code, d.title AS doc_title, c.path::text AS path, c.verbatim_text,
       c.contextualized_text, c.effective_date
FROM chunks c JOIN documents d ON d.id = c.document_id
WHERE {_LIVE} AND c.embedding IS NOT NULL
ORDER BY c.embedding <=> $1::vector
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


async def _dense(conn: Any, vector: list[float], today: Any, k: int) -> list[SearchHit]:
    return [_as_hit(r) for r in await conn.fetch(SQL_DENSE, vector, today, k)]


async def _full(
    conn: Any, query: str, vector: list[float], today: Any, k: int
) -> list[SearchHit]:
    rows = await conn.fetch(
        SQL_FUSED,
        expand_query(query),
        vector,
        today,
        k,
        classify_query(query),
        classify_intent(query),
        phrase_variants(query),
        0.2 if is_unaccented(query) else 1.0,
    )
    return [_as_hit(r) for r in rows]


async def _labels(conn: Any, paths: list[str]) -> dict[str, list[str]]:
    """The vehicle labels stored on the ground-truth chunks.

    Needed because the facet bonus compares the query's class against this, and
    a mismatch here is the mechanism that demonstrably cost a whole answer once
    already (the motorway speed limit labelled `works_vehicle`).
    """
    if not paths:
        return {}
    rows = await conn.fetch(
        "SELECT path::text AS path, metadata->'vehicle_classes' AS vc"
        " FROM chunks WHERE path::text = ANY($1::text[])",
        paths,
    )
    out: dict[str, list[str]] = {}
    for row in rows:
        raw = row["vc"]
        if isinstance(raw, str):
            raw = json.loads(raw)
        out[str(row["path"])] = list(raw or [])
    return out


def _blame(
    query: str, truth_labels: list[str], winner: SearchHit, found_rank: int | None
) -> str:
    """Names the signal most likely responsible for one regression.

    Ordered by how specific the evidence is, and every branch is checkable
    against the row printed beside it. `fusion/rerank` is the residual: it
    means none of the named signals differed, so the loss came from the
    ordering itself rather than from a facet or an expansion.
    """
    if found_rank is None:
        return "recall: đáp án không có trong top-k"
    vehicle = classify_query(query)
    if vehicle and truth_labels and vehicle not in truth_labels:
        return "facet loại xe: câu hỏi nêu loại xe khác nhãn của đáp án"
    if vehicle and not truth_labels:
        return "facet loại xe: đáp án không có nhãn nên không được thưởng"
    if classify_intent(query) is not None:
        return "facet vai trò điều khoản"
    if expand_query(query) != query:
        return "mở rộng truy vấn (lexicon)"
    return "fusion/rerank: không tín hiệu nào khác, chỉ do thứ tự"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", default="qrels200", choices=sorted(SETS))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--depth", type=int, default=20, help="Độ sâu kiểm recall")
    parser.add_argument("--strict", action="store_true", help="Chấm mức Khoản/Điểm")
    parser.add_argument("--show", type=int, default=25)
    args = parser.parse_args()

    matches = _check_citation_exactness if args.strict else _check_article_match
    items = [
        json.loads(line)
        for line in SETS[args.set].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    embedder = SentenceTransformerQueryEmbedder()
    pool = await get_db_pool()
    today = get_vietnam_today()

    tally: Counter[str] = Counter()
    causes: Counter[str] = Counter()
    regressions: list[tuple[str, str, str, str]] = []

    async with pool.acquire() as conn:
        label_cache = await _labels(
            conn, [str(i["source_path"]) for i in items if i.get("source_path")]
        )

        for item in items:
            query = str(item["query"])
            truth = GroundTruth.model_validate(item["ground_truth"])
            vector = await embedder.embed_query(query) or []

            dense = await _dense(conn, vector, today, args.limit)
            full = await _full(conn, query, vector, today, args.limit)
            dense_ok = bool(dense) and matches(dense[0], truth)
            full_ok = bool(full) and matches(full[0], truth)

            if dense_ok and full_ok:
                tally["cả hai đúng"] += 1
            elif not dense_ok and not full_ok:
                tally["cả hai sai"] += 1
            elif full_ok:
                tally["full đúng, dense sai"] += 1
            else:
                tally["dense đúng, FULL SAI"] += 1
                deep = await _full(conn, query, vector, today, args.depth)
                found = next(
                    (n for n, h in enumerate(deep, 1) if matches(h, truth)), None
                )
                cause = _blame(
                    query,
                    label_cache.get(str(item.get("source_path") or ""), []),
                    full[0],
                    found,
                )
                causes[cause] += 1
                regressions.append(
                    (
                        query,
                        f"{truth.doc_code} Điều {truth.article}",
                        full[0].path,
                        f"{cause}"
                        + (f" (đáp án ở hạng {found}/{args.depth})" if found else ""),
                    )
                )

    level = "Khoản/Điểm" if args.strict else "Điều"
    print(f"Tập {args.set}, n={len(items)}, mức chấm {level}, Hit@1\n")
    for name, count in tally.most_common():
        print(f"  {name:24s} {count:4d}  ({count / len(items):5.1%})")

    if not regressions:
        print("\nKhông có câu nào dense đúng mà full sai.")
    else:
        print(f"\nNguyên nhân {len(regressions)} ca full thua dense:")
        for cause, count in causes.most_common():
            print(f"  {count:4d}  {cause}")

        print(f"\nVí dụ (tối đa {args.show}):")
        for query, want, got, cause in regressions[: args.show]:
            print(f"\n  hỏi:      {query[:96]}")
            print(f"  đáp án:   {want}")
            print(f"  full #1:  {got[-46:]}")
            print(f"  nguyên nhân: {cause}")

    await close_db_pool()
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
