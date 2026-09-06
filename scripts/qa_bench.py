"""Scores a large generated query set against the retrieval engine.

At a few hundred queries an agent cannot judge each answer -- it is slow, and
the judge invents Vietnamese law as readily as the system under test would. So
the questions are written *from* sampled chunks and the ground truth is derived
from the sampled path rather than retyped, which makes judging a string
comparison instead of an opinion.

Input is JSONL with `query`, `source_path`, and optionally `style`,
`violation_date` and `expect` ("hit" or "miss"). A `miss` row asserts the corpus
has no answer, and is scored on whether the engine stayed quiet rather than on
what it ranked first.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.eval.smoke_runner import GroundTruth, _check_article_match
from rag_eval.legal.ingestion.facets import classify_intent, classify_query
from rag_eval.legal.ingestion.xref import address_of_path
from rag_eval.legal.mcp.tools import SearchHit, SentenceTransformerQueryEmbedder
from rag_eval.legal.retrieval.lexicon import expand_query, phrase_variants
from rag_eval.legal.schemas import get_vietnam_today, parse_flexible_date

SQL = (
    "SELECT doc_code, doc_title, path, verbatim_text, contextualized_text,"
    " effective_date, rrf_score FROM"
    " hybrid_search($1,$2::vector,$3::date,$4::int,60,$5,$6,$7)"
)

# A "miss" row is only a pass if nothing scored above this. Chosen from the
# observed spread: real answers land near 0.030-0.040, and an out-of-scope
# question's best guess sits below 0.025.
MISS_SCORE_CEILING = 0.025


def _article_key(path: str) -> tuple[str, ...]:
    """Returns the address a hit must share with the target to count as correct.

    Article level, matching the smoke runner: a question about Điều 7 Khoản 7 is
    answered by that article's neighbourhood, and demanding the exact leaf would
    score a correct retrieval as a miss whenever the answer spans two windows.
    """
    address = address_of_path(path)
    if address.dieu:
        return (path.split(".", 1)[0], address.dieu)
    # Appendix provisions carry no Điều; fall back to the path minus its leaf.
    return tuple(path.rsplit(".", 1)[0].split("."))


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
        score=float(row["rrf_score"]),
    )


async def _load(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or not row.get("query"):
            continue
        key = (row["query"], row.get("violation_date"))
        if key in seen:
            continue
        seen.add(key)
        row["_source"] = path.name
        rows.append(row)
    return rows


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="JSONL files of generated queries")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--failures", type=str, default=None, help="Write misses here")
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    for pattern in args.inputs:
        direct = Path(pattern)
        # Path.glob rejects an absolute pattern, and these files live outside
        # the repo, so an existing path is taken as given.
        found = [direct] if direct.exists() else sorted(Path().glob(pattern))
        for path in found:
            if path.exists():
                rows.extend(await _load(path))

    pool = await get_db_pool()
    embedder = SentenceTransformerQueryEmbedder()
    today = get_vietnam_today()

    by_style: dict[str, Counter[str]] = defaultdict(Counter)
    totals: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    unresolved = 0

    async with pool.acquire() as conn:
        valid_paths = {
            r["path"]
            for r in await conn.fetch("SELECT path::text AS path FROM chunks")
        }

        for row in rows:
            query = str(row["query"])
            target = row.get("source_path")
            expect_hit = row.get("expect", "hit") != "miss"

            # A fixture row names its answer by address; a generated one by the
            # path it was sampled from, which must still exist in the corpus.
            if (
                expect_hit
                and not row.get("ground_truth")
                and (not target or target not in valid_paths)
            ):
                unresolved += 1
                continue

            vector = await embedder.embed_query(query) if query.strip() else None
            if vector is None:
                totals["skipped_empty"] += 1
                continue

            violation = parse_flexible_date(row.get("violation_date")) or today
            hits = await conn.fetch(
                SQL,
                expand_query(query),
                vector,
                violation,
                args.limit,
                classify_query(query),
                classify_intent(query),
                phrase_variants(query),
            )

            style = str(row.get("style") or "unknown")
            totals["scored"] += 1
            by_style[style]["n"] += 1

            if not expect_hit:
                best = max((float(h["rrf_score"]) for h in hits), default=0.0)
                quiet = not hits or best < MISS_SCORE_CEILING
                by_style[style]["pass"] += 1 if quiet else 0
                totals["miss_pass"] += 1 if quiet else 0
                totals["miss_total"] += 1
                if not quiet:
                    failures.append(
                        {
                            "query": query,
                            "style": style,
                            "kind": "should_have_stayed_quiet",
                            "top": str(hits[0]["path"]),
                            "score": round(best, 4),
                            "source": row["_source"],
                        }
                    )
                continue

            truth = row.get("ground_truth")
            if truth:
                # Fixture rows name the answer by address rather than by path.
                target_truth = GroundTruth.model_validate(truth)
                rank = next(
                    (
                        i
                        for i, h in enumerate(hits, 1)
                        if _check_article_match(_as_hit(h), target_truth)
                    ),
                    None,
                )
            else:
                want = _article_key(str(target))
                rank = next(
                    (
                        i
                        for i, h in enumerate(hits, 1)
                        if _article_key(str(h["path"])) == want
                    ),
                    None,
                )
            totals["hit_total"] += 1
            if rank == 1:
                totals["hit1"] += 1
                by_style[style]["hit1"] += 1
            if rank is not None and rank <= 3:
                totals["hit3"] += 1
            if rank is not None:
                totals["hit5"] += 1
                totals["rr"] += 0
                by_style[style]["hit5"] += 1
            if rank != 1:
                failures.append(
                    {
                        "query": query,
                        "style": style,
                        "kind": "wrong_rank_1" if rank else "not_in_top_k",
                        "want": str(target or row.get("ground_truth")),
                        "got": str(hits[0]["path"]) if hits else None,
                        "rank_of_answer": rank,
                        "violation_date": row.get("violation_date"),
                        "source": row["_source"],
                    }
                )

    hit_total = totals["hit_total"] or 1
    miss_total = totals["miss_total"] or 1
    print(f"Đã chấm {totals['scored']} truy vấn ({unresolved} bỏ vì path không tồn tại)\n")
    print(f"  Câu có đáp án   n={totals['hit_total']:4d}"
          f"  Hit@1 {totals['hit1'] / hit_total:6.1%}"
          f"  Hit@3 {totals['hit3'] / hit_total:6.1%}"
          f"  Hit@5 {totals['hit5'] / hit_total:6.1%}")
    print(f"  Câu không đáp án n={totals['miss_total']:4d}"
          f"  giữ im lặng đúng {totals['miss_pass'] / miss_total:6.1%}")

    print("\nTheo phong cách câu hỏi:")
    for style, counts in sorted(by_style.items(), key=lambda kv: -kv[1]["n"]):
        n = counts["n"] or 1
        if counts.get("pass"):
            print(f"  {style:22s} n={n:4d}  im lặng đúng {counts['pass'] / n:6.1%}")
        else:
            print(f"  {style:22s} n={n:4d}  Hit@1 {counts['hit1'] / n:6.1%}"
                  f"  Hit@5 {counts['hit5'] / n:6.1%}")

    if args.failures:
        Path(args.failures).write_text(
            "\n".join(json.dumps(f, ensure_ascii=False) for f in failures) + "\n",
            encoding="utf-8",
        )
        print(f"\n{len(failures)} ca trượt đã ghi vào {args.failures}")

    await close_db_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
