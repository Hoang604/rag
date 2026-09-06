"""The overlay on/off experiment, plus the one that matters more: overlay wrong.

Sprint 3's gate asks for a PROMOTE or REVERT decision backed by numbers, and
REVERT with numbers passes the gate. This produces both halves of that.

The honest limitation, stated first: there is no real annotation log yet. It
started today and Sprint 3 was sized on three months of it. So the annotations
here are simulated -- an agent that asked one set of questions and recorded
where it found the answers -- and the evaluation runs on a disjoint set of
questions about the same provisions. That is the shape of the real thing, with
one difference that matters: the simulated agent can be made right exactly as
often as we choose, which is what makes the second experiment possible.

Two experiments:

  Benefit. Annotations from the training questions, measured on the evaluation
  questions. This is the optimistic bound: every annotation is correct.

  Damage. The same, with a fraction of annotations pointing at the wrong
  provision. This is the failure §4.4 is about -- a wrong answer boosted,
  found more often, annotated again. The promotion gate is supposed to hold
  here, and if it does not, the overlay does not ship no matter how good the
  first number looks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
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
from rag_eval.legal.retrieval.annotations import AnnotationStore, SplitGuard
from rag_eval.legal.retrieval.lexicon import expand_query, phrase_variants
from rag_eval.legal.retrieval.overlay import OverlayBuilder, lookup_fingerprint
from rag_eval.legal.schemas import get_vietnam_today
from rag_eval.legal.text import is_unaccented

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

SQL = (
    "SELECT doc_code, doc_title, path, verbatim_text, contextualized_text,"
    " effective_date, rrf_score"
    " FROM hybrid_search($1,$2::vector,$3::date,$4::int,60,$5,$6,$7,$8,$9)"
)

SOURCE = "overlay-experiment"


def _as_hit(row: Any) -> SearchHit:
    return SearchHit(
        chunk_id="",
        doc_code=str(row["doc_code"]),
        doc_title="",
        path=str(row["path"]),
        verbatim_text="",
        contextualized_text="",
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
    use_overlay: bool,
    strict: bool,
    limit: int = 5,
) -> dict[str, float]:
    matches = _check_citation_exactness if strict else _check_article_match
    hit1 = hit5 = 0
    reciprocal = 0.0
    for item in items:
        query = item["query"]
        # Exploration is switched off while measuring: a tenth of searches
        # randomly ignoring the overlay would add noise to the very comparison
        # being run. It is a production behaviour, not an evaluation one.
        topic = lookup_fingerprint(query, explore=False) if use_overlay else None
        rows = await conn.fetch(
            SQL,
            expand_query(query),
            vectors[query],
            today,
            limit,
            classify_query(query),
            classify_intent(query),
            phrase_variants(query),
            0.2 if is_unaccented(query) else 1.0,
            topic,
        )
        truth = GroundTruth.model_validate(item["ground_truth"])
        for rank, row in enumerate(rows, start=1):
            if matches(_as_hit(row), truth):
                if rank == 1:
                    hit1 += 1
                hit5 += 1
                reciprocal += 1.0 / rank
                break
    total = len(items) or 1
    return {"hit1": hit1 / total, "hit5": hit5 / total, "mrr": reciprocal / total}


async def _plant(
    store: AnnotationStore,
    conn: Any,
    train: list[dict[str, Any]],
    error_rate: float,
    rng: random.Random,
) -> tuple[int, int]:
    """Simulates a log: one agent's answer per training question.

    Two independent sessions record each finding, because the promotion gate
    requires that. A wrong annotation is planted by pointing at a random live
    provision instead of the right one -- which is what an agent that misread
    the question would produce.
    """
    all_paths = [
        r["path"]
        for r in await conn.fetch("SELECT path::text AS path FROM chunks LIMIT 4000")
    ]
    planted = wrong = 0
    for item in train:
        target = item["source_path"]
        if rng.random() < error_rate:
            target = rng.choice(all_paths)
            wrong += 1
        chunk_id = await conn.fetchval(
            "SELECT id::text FROM chunks WHERE path = $1::ltree", target
        )
        if chunk_id is None:
            continue
        for session in ("s1", "s2"):
            await store.record(
                chunk_id=chunk_id,
                query_text=item["query"],
                note="planted",
                source=SOURCE,
                session_id=f"{session}-{planted}",
            )
        planted += 1
    return planted, wrong


def _load(path: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", default=str(FIXTURES / "qrels_dev.jsonl"))
    parser.add_argument("--eval", default=str(FIXTURES / "qrels_holdout.jsonl"))
    parser.add_argument("--error-rates", type=float, nargs="+", default=[0.0, 0.3])
    parser.add_argument("--seed", type=int, default=20260906)
    args = parser.parse_args()

    train_all = _load(args.train)
    evaluation = _load(args.eval)

    # The experiment only means anything where the two sets overlap in subject
    # matter: an overlay cannot help with a provision nobody ever annotated.
    eval_paths = {i["source_path"] for i in evaluation}
    train = [i for i in train_all if i["source_path"] in eval_paths]
    print(
        f"{len(train_all)} câu huấn luyện, {len(train)} câu trỏ vào cùng điều khoản"
        f" với tập đánh giá ({len(evaluation)} câu)\n"
    )
    if not train:
        print("Không có giao nhau: overlay không thể tác động. Dừng.")
        return 0

    pool = await get_db_pool()
    embedder = SentenceTransformerQueryEmbedder()
    today = get_vietnam_today()
    vectors = {
        i["query"]: (await embedder.embed_query(i["query"]) or []) for i in evaluation
    }

    store = AnnotationStore(pool)
    builder = OverlayBuilder(pool)
    # Reuse level: these annotations come from a disjoint question set, so only
    # a near-verbatim restating counts as leakage. Under the topic-level guard
    # the overlay could not fire at all and the experiment would be vacuous.
    guard = SplitGuard.from_queries([i["query"] for i in evaluation], topic_level=False)

    print(
        f"{'cấu hình':28s}{'Điều Hit@1/Hit@5/MRR':>26s}{'Khoản Hit@1/Hit@5/MRR':>28s}"
    )
    print("-" * 82)

    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM annotations WHERE source = $1", SOURCE)
        await builder.activate(None, "tắt")

        cells = []
        for strict in (False, True):
            s = await _score(conn, evaluation, vectors, today, False, strict)
            cells.append(
                f"{s['hit1'] * 100:6.1f} /{s['hit5'] * 100:6.1f} / {s['mrr']:.3f}"
            )
        print(f"{'overlay tắt':28s}{cells[0]:>26s}{cells[1]:>28s}")

        for error_rate in args.error_rates:
            rng = random.Random(args.seed)
            await conn.execute("DELETE FROM annotations WHERE source = $1", SOURCE)
            planted, wrong = await _plant(store, conn, train, error_rate, rng)
            await builder.verify_by_grep()
            report = await builder.build(guard, as_of=today)
            await builder.activate(report.build_version, f"lỗi {error_rate:.0%}")

            cells = []
            for strict in (False, True):
                s = await _score(conn, evaluation, vectors, today, True, strict)
                cells.append(
                    f"{s['hit1'] * 100:6.1f} /{s['hit5'] * 100:6.1f} / {s['mrr']:.3f}"
                )
            label = f"overlay bật, {error_rate:.0%} sai"
            print(f"{label:28s}{cells[0]:>26s}{cells[1]:>28s}")
            print(f"    {report.describe()}  ({planted} ghi nhận, {wrong} sai)")

        await conn.execute("DELETE FROM annotations WHERE source = $1", SOURCE)
        await builder.activate(None, "tắt lại sau thí nghiệm")

    print("\nOverlay đã tắt lại. Annotation thí nghiệm đã xoá.")
    await close_db_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
