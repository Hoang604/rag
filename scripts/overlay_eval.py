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
import re
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
from rag_eval.legal.retrieval.overlay import OverlayBuilder, lookup_tokens
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
    frequency: dict[str, int],
    limit: int = 5,
) -> tuple[dict[str, float], list[str]]:
    """Scores one configuration, and records which provision it ranked first.

    The top-1 list is what makes a null result readable. An aggregate that
    barely moves has two very different explanations -- the overlay reordered
    many questions and the gains cancelled the losses, or it reordered almost
    nothing -- and the promotion decision differs between them.
    """
    matches = _check_citation_exactness if strict else _check_article_match
    hit1 = hit5 = 0
    reciprocal = 0.0
    first: list[str] = []
    for item in items:
        query = item["query"]
        # Exploration is switched off while measuring: a tenth of searches
        # randomly ignoring the overlay would add noise to the very comparison
        # being run. It is a production behaviour, not an evaluation one.
        topic = lookup_tokens(query, frequency, explore=False) if use_overlay else None
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
        first.append(str(rows[0]["path"]) if rows else "")
        truth = GroundTruth.model_validate(item["ground_truth"])
        for rank, row in enumerate(rows, start=1):
            if matches(_as_hit(row), truth):
                if rank == 1:
                    hit1 += 1
                hit5 += 1
                reciprocal += 1.0 / rank
                break
    total = len(items) or 1
    scores = {"hit1": hit1 / total, "hit5": hit5 / total, "mrr": reciprocal / total}
    return scores, first


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
    # Live provisions only. Pointing a wrong annotation at repealed law would
    # let the effectiveness filter drop it before the promotion gate ever saw
    # it -- the first run of this experiment did exactly that for eight of
    # nine planted errors, and measured mechanism 5 while claiming to test
    # mechanism 2.
    # Live provisions only. Pointing a wrong annotation at repealed law would
    # let the effectiveness filter drop it before the promotion gate ever saw
    # it -- the first run of this experiment did exactly that for eight of
    # nine planted errors, and measured mechanism 5 while claiming to test
    # mechanism 2.
    rows = await conn.fetch(
        """
        SELECT c.path::text AS path, c.id::text AS id FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.expiration_date IS NULL AND c.effective_date <= CURRENT_DATE
        """
    )
    # One lookup table instead of a query per planted annotation. The loop
    # below ran a fetchval each time, which is a round trip per row for data
    # that never changes during the run.
    id_by_path = {str(r["path"]): str(r["id"]) for r in rows}
    all_paths = list(id_by_path)

    planted = wrong = 0
    for item in train:
        target = item["source_path"]
        if rng.random() < error_rate:
            target = rng.choice(all_paths)
            wrong += 1
        chunk_id = id_by_path.get(target)
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


_LEAF = re.compile(r"^\s*(Điểm|Khoản)\s+[^\s)]{1,4}[).]\s*")


def _offence_of(verbatim: str) -> str | None:
    """Reduces a provision to the act it describes, for a synthetic question."""
    text = _LEAF.sub("", " ".join(verbatim.split())).split(";")[0]
    text = text.strip(" .;,:")
    words = text.split()
    if not (5 <= len(words) <= 22):
        return None
    return text[0].lower() + text[1:]


def _load(path: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval", default=str(FIXTURES / "qrels_holdout.jsonl"))
    parser.add_argument("--error-rates", type=float, nargs="+", default=[0.0, 0.3])
    parser.add_argument(
        "--max-weights",
        type=float,
        nargs="+",
        default=[0.10],
        help=(
            "Trần trọng số cần quét. Mặc định 0,10 là giá trị đang cài. "
            "SQL chặn trên 0,25 nên giá trị lớn hơn sẽ bị kẹp."
        ),
    )
    parser.add_argument("--seed", type=int, default=20260906)
    args = parser.parse_args()

    evaluation = _load(args.eval)

    pool = await get_db_pool()
    embedder = SentenceTransformerQueryEmbedder()
    today = get_vietnam_today()

    # The two fixture splits point at disjoint provisions, so annotations from
    # one can never reach the other. Prior traffic is synthesised instead: a
    # different question about each provision the evaluation asks about, built
    # from the statutory text rather than from the evaluation question, so the
    # wording is genuinely independent.
    eval_paths = sorted({i["source_path"] for i in evaluation})
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT path::text AS path, verbatim_text FROM chunks"
            " WHERE path::text = ANY($1::text[])",
            eval_paths,
        )
    train = []
    for row in rows:
        offence = _offence_of(str(row["verbatim_text"]))
        if not offence:
            continue
        # Two phrasings per provision, because the promotion gate needs
        # agreement and one question asked twice is one opinion.
        for template in (
            "hành vi {} bị xử phạt thế nào",
            "mức phạt cho {} là bao nhiêu",
        ):
            train.append(
                {
                    "query": template.format(offence),
                    "source_path": str(row["path"]),
                }
            )
    print(
        f"{len(evaluation)} câu đánh giá trên {len(eval_paths)} điều khoản;"
        f" dựng {len(train)} câu 'lượt hỏi trước' từ chính văn bản luật\n"
    )
    if not train:
        print("Không dựng được câu huấn luyện nào. Dừng.")
        await close_db_pool()
        return 0

    vectors = {
        i["query"]: (await embedder.embed_query(i["query"]) or []) for i in evaluation
    }

    store = AnnotationStore(pool)
    builder = OverlayBuilder(pool)
    frequency = await builder.document_frequency()
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
        baseline_first: list[str] = []
        for strict in (False, True):
            scores, first = await _score(
                conn, evaluation, vectors, today, False, strict, frequency
            )
            if not strict:
                baseline_first = first
            cells.append(
                f"{scores['hit1'] * 100:6.1f} /{scores['hit5'] * 100:6.1f}"
                f" / {scores['mrr']:.3f}"
            )
        print(f"{'overlay tắt':28s}{cells[0]:>26s}{cells[1]:>28s}")

        moved: list[tuple[float, float, int]] = []
        for cap in args.max_weights:
            for error_rate in args.error_rates:
                rng = random.Random(args.seed)
                await conn.execute("DELETE FROM annotations WHERE source = $1", SOURCE)
                planted, wrong = await _plant(store, conn, train, error_rate, rng)
                await builder.verify_by_grep()
                report = await builder.build(guard, as_of=today, max_weight=cap)
                await builder.activate(
                    report.build_version, f"trần {cap:g}, lỗi {error_rate:.0%}"
                )

                cells = []
                changed = 0
                for strict in (False, True):
                    scores, first = await _score(
                        conn, evaluation, vectors, today, True, strict, frequency
                    )
                    if not strict:
                        changed = sum(
                            1
                            for before, after in zip(baseline_first, first, strict=True)
                            if before != after
                        )
                    cells.append(
                        f"{scores['hit1'] * 100:6.1f} /{scores['hit5'] * 100:6.1f}"
                        f" / {scores['mrr']:.3f}"
                    )
                label = f"trần {cap:g}, {error_rate:.0%} sai"
                print(f"{label:28s}{cells[0]:>26s}{cells[1]:>28s}")
                print(
                    f"    {report.describe()}  ({planted} ghi nhận, {wrong} sai)"
                    f"  đổi hạng 1: {changed}/{len(evaluation)}"
                )
                moved.append((cap, error_rate, changed))

        print()
        if all(count == 0 for _, _, count in moved):
            print(
                "Overlay không đổi hạng 1 của một câu nào ở mọi trần đã quét."
                " Cơ chế không chạm được tới xếp hạng, nên con số benefit và"
                " damage đều bằng 0 vì cùng một lý do, không phải vì overlay an"
                " toàn."
            )
        else:
            print(
                "Số 'đổi hạng 1' là thứ cần đọc trước Hit@1: nếu nó nhỏ thì"
                " mọi chênh lệch phía trên đều nằm trong nhiễu của vài câu."
            )

        await conn.execute("DELETE FROM annotations WHERE source = $1", SOURCE)
        await builder.activate(None, "tắt lại sau thí nghiệm")

    print("\nOverlay đã tắt lại. Annotation thí nghiệm đã xoá.")
    await close_db_pool()
    return 0


from rag_eval.legal.console import use_utf8_stdout

if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
