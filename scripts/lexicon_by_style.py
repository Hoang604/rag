"""Tests whether query expansion helps or hurts, split by how the question is worded.

`ablation.py` found something that looks like a straightforward defect: on
`qrels200` the lexicon costs 2.0 points of Hit@1 on its own and 1.5 on top of
the facets, so the shipped configuration scores below `both facets`. Read alone
that says: drop the expansion.

There is a reason to distrust that reading. The lexicon exists to bridge
colloquial wording to statutory wording -- "vượt đèn đỏ" and the statute's
"không chấp hành hiệu lệnh của đèn tín hiệu giao thông" share no words. But
every qrels question was written from a corpus path, so those questions already
speak in statutory vocabulary. Expansion has nothing to bridge there and can
only add candidates. If that is what is happening, the benchmark is measuring
the lexicon on precisely the inputs it was not built for, and removing it would
help the benchmark while hurting real users.

So this scores the same queries twice -- expanded and raw, everything else
identical -- and reports the difference per question style. Statutory-sounding
generated styles and colloquial perturbations are counted separately, because
the whole question is whether they disagree.

It also reports the control the first version of this experiment lacked, and
which turned out to matter more than the scores: how often the expansion
rewrites the question at all. A style where it never fires cannot show an
effect, and reading 0.0 there as "the lexicon does not help" would be reading
a measurement that was never taken.

Measured, and it refuted the hypothesis above rather than confirming it. The
two groups do not diverge -- colloquial -0.3, statutory -0.5, both inside the
noise of zero -- and sixteen of twenty styles moved by exactly 0.0. The control
says why: expansion fires on 7.2% of the sample overall, 0.0% of the definition
styles, 1.7% of `gen_rule`. The perturbations are mechanical disguises of
statutory wording -- typos, stripped diacritics, abbreviations -- not different
words for the same thing, so there is no vocabulary gap anywhere in the set for
the lexicon to bridge.

The conclusion is therefore stronger and less convenient than "the lexicon
hurts": this benchmark cannot measure the lexicon in either direction, and the
-2.0 that `ablation.py` reports on `qrels200` is a penalty concentrated in the
few per cent of questions where expansion fires at all. Deciding whether to
keep it needs the evaluation set that `build_colloquial_qrels.py` exists to
produce.

One embedding per query, reused for both runs: the vector never depends on the
expansion, and computing it twice would double the cost of the experiment for
no difference in the numbers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.ingestion.facets import classify_intent, classify_query
from rag_eval.legal.ingestion.xref import address_of_path
from rag_eval.legal.mcp.tools import SearchHit, SentenceTransformerQueryEmbedder
from rag_eval.legal.retrieval.lexicon import expand_query, phrase_variants
from rag_eval.legal.schemas import get_vietnam_today
from rag_eval.legal.text import is_unaccented

SQL = (
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


async def _search(
    conn: Any, sparse_text: str, query: str, vector: list[float], today: Any, k: int
) -> list[SearchHit]:
    """One search. `sparse_text` is the only thing the two runs differ in."""
    rows = await conn.fetch(
        SQL,
        sparse_text,
        vector,
        today,
        k,
        classify_query(query),
        classify_intent(query),
        phrase_variants(query),
        0.2 if is_unaccented(query) else 1.0,
    )
    return [_as_hit(r) for r in rows]


def _article_key(path: str) -> tuple[str, ...]:
    """The address a hit must share with the sampled path to count as correct.

    Copied from `qa_bench.py` on purpose rather than tightened: scoring this
    experiment by a different rule than the benchmark it is explaining would
    make the two sets of numbers incomparable, which is the whole point of
    running it.
    """
    address = address_of_path(path)
    if address.dieu:
        return (path.split(".", 1)[0], address.dieu)
    return tuple(path.rsplit(".", 1)[0].split("."))


# A perturbation is applied to a generated question, so its style name records
# the disguise rather than the template. Everything else is a question written
# from the statute and phrased like it.
def _is_colloquial(style: str) -> bool:
    return style.startswith("p_")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs", nargs="+", help="JSONL sinh bởi qa_generate/qa_perturb"
    )
    parser.add_argument("--per-style", type=int, default=60)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260908)
    args = parser.parse_args()

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pattern in args.inputs:
        direct = Path(pattern)
        found = [direct] if direct.exists() else sorted(Path().glob(pattern))
        for path in found:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("source_path") and row.get("expect", "hit") != "miss":
                    grouped[str(row.get("style") or "unknown")].append(row)

    rng = random.Random(args.seed)
    sample: dict[str, list[dict[str, Any]]] = {}
    for style, rows in grouped.items():
        rng.shuffle(rows)
        sample[style] = rows[: args.per_style]

    total = sum(len(v) for v in sample.values())
    print(f"{len(sample)} phong cách, {total} câu (tối đa {args.per_style}/phong cách)")
    # Article level only. The generated ground truth is a sampled path, and
    # `qa_bench` scores it at article level for a stated reason -- a question
    # about Điều 7 Khoản 7 is answered by that article's neighbourhood, and
    # demanding the exact leaf scores a correct retrieval as a miss whenever
    # the answer spans two windows.
    print("Chấm mức Điều, Hit@1\n")

    embedder = SentenceTransformerQueryEmbedder()
    pool = await get_db_pool()
    today = get_vietnam_today()

    per_style: dict[str, Counter[str]] = defaultdict(Counter)

    async with pool.acquire() as conn:
        for style, rows in sample.items():
            for row in rows:
                query = str(row["query"])
                want = _article_key(str(row["source_path"]))
                vector = await embedder.embed_query(query) or []

                raw = await _search(conn, query, query, vector, today, args.limit)
                expanded = await _search(
                    conn, expand_query(query), query, vector, today, args.limit
                )

                per_style[style]["n"] += 1
                if expand_query(query) != query:
                    per_style[style]["fired"] += 1
                if raw and _article_key(raw[0].path) == want:
                    per_style[style]["off"] += 1
                if expanded and _article_key(expanded[0].path) == want:
                    per_style[style]["on"] += 1

    def rate(c: Counter[str], key: str) -> float:
        return c[key] / c["n"] * 100 if c["n"] else 0.0

    rows_out = [
        (
            style,
            c["n"],
            rate(c, "fired"),
            rate(c, "off"),
            rate(c, "on"),
            rate(c, "on") - rate(c, "off"),
        )
        for style, c in per_style.items()
    ]
    rows_out.sort(key=lambda r: r[5])

    print(
        f"{'phong cách':28s}{'n':>5s}{'lexicon nổ':>12s}"
        f"{'không lexicon':>15s}{'có lexicon':>12s}{'chênh':>8s}"
    )
    print("-" * 80)
    for style, n, fired, off, on, delta in rows_out:
        print(f"{style:28s}{n:5d}{fired:11.1f}%{off:14.1f}%{on:11.1f}%{delta:+8.1f}")

    groups = {
        "khẩu ngữ (p_*)": _is_colloquial,
        "văn luật (còn lại)": lambda s: not _is_colloquial(s),
    }
    print()
    for name, pick in groups.items():
        agg = Counter()
        for style, c in per_style.items():
            if pick(style):
                agg.update(c)
        if not agg["n"]:
            continue
        off, on = rate(agg, "off"), rate(agg, "on")
        print(
            f"{name:28s}{agg['n']:5d}{rate(agg, 'fired'):11.1f}%"
            f"{off:14.1f}%{on:11.1f}%{on - off:+8.1f}"
        )

    fired_overall = sum(c["fired"] for c in per_style.values())
    n_overall = sum(c["n"] for c in per_style.values()) or 1
    print(
        f"\nĐọc cột 'lexicon nổ' TRƯỚC hai cột điểm. Trên toàn bộ mẫu, lexicon"
        f"\nchỉ viết lại {fired_overall / n_overall:.1%} câu hỏi. Một phong cách"
        "\nmà nó không nổ lần nào thì chênh 0,0 của phong cách đó là một phép đo"
        "\nCHƯA TỪNG ĐƯỢC THỰC HIỆN, không phải một kết quả âm tính."
    )
    await close_db_pool()
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
