"""Mines term relatedness from the corpus, for queries the hand lexicon misses.

`lexicon.py` maps colloquial phrasings onto statutory ones, and every pair in
it was written and verified by hand. That is why it is trustworthy and also why
there are only fifteen: each one costs a person reading the corpus. On the
118-question colloquial set the lexicon fires on a minority of questions, and
the rest reach the sparse ranker with the user's own words and nothing else.

This fills that gap from a signal that exists at scale. Two words are related
here if they occur in the same provision more often than their separate
frequencies predict -- positive pointwise mutual information over 7,093
provisions.

What it cannot do, stated plainly because the plan asked for something else:
it cannot learn that "vượt đèn đỏ" means "không chấp hành hiệu lệnh của đèn tín
hiệu giao thông". Nothing in a corpus of statutes contains the colloquial side
of that pair. The original design learned relatedness from user co-retrieval,
which would have; that data does not exist yet. What this learns is the
statutory side's internal structure: land on `đèn` and it can reach `lệnh`,
`hiệu`, `tín`, because those words keep company in this corpus.

Two floors, and both were read off measurements rather than chosen:

  * `--min-df 20` on each term. Without it PPMI is dominated by rare tokens --
    the first run returned `đèn → huynh, hom, 800, 000, bu, tec`, which is what
    PPMI always does to a long tail. At 20 the same query returns
    `đèn → nháy, xanh, gác, vàng`.
  * `--min-pair 8` provisions holding both. A pair seen five times has a
    spectacular PPMI and no evidence behind it.

Writes nothing without `--apply`.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import math
from collections import Counter, defaultdict

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.retrieval.annotations import content_tokens


def _has_digit(token: str) -> bool:
    return any(character.isdigit() for character in token)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-df", type=int, default=20)
    parser.add_argument("--min-pair", type=int, default=8)
    parser.add_argument(
        "--top-k", type=int, default=12, help="giữ mấy láng giềng mỗi từ"
    )
    parser.add_argument("--show", type=int, default=12, help="in thử mấy từ")
    parser.add_argument(
        "--apply", action="store_true", help="ghi thật vào cơ sở dữ liệu"
    )
    args = parser.parse_args()

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT verbatim_text FROM chunks")

    # Verbatim, not contextualized: the ancestor prefix repeats the article
    # heading into every one of its descendants, so counting it would report
    # that every word of a heading co-occurs with every word of every child.
    # That is an artefact of how the chunk is stored, not a fact about language.
    documents = [content_tokens(str(row["verbatim_text"])) for row in rows]
    documents = [d for d in documents if len(d) >= 3]
    total = len(documents)
    if not total:
        print("corpus rỗng — chưa nạp văn bản")
        await close_db_pool()
        return 1

    frequency: Counter[str] = Counter()
    for document in documents:
        frequency.update(document)

    vocabulary = {
        token
        for token, count in frequency.items()
        if count >= args.min_df and not _has_digit(token)
    }

    pair_counts: Counter[tuple[str, str]] = Counter()
    for document in documents:
        kept = sorted(document & vocabulary)
        pair_counts.update(itertools.combinations(kept, 2))

    neighbours: defaultdict[str, list[tuple[float, str, int]]] = defaultdict(list)
    for (left, right), count in pair_counts.items():
        if count < args.min_pair:
            continue
        score = math.log(
            (count / total) / ((frequency[left] / total) * (frequency[right] / total))
        )
        if score <= 0.0:
            continue
        neighbours[left].append((score, right, count))
        neighbours[right].append((score, left, count))

    records: list[tuple[str, str, float, int]] = []
    for term, found in neighbours.items():
        found.sort(reverse=True)
        for score, related, count in found[: args.top_k]:
            records.append((term, related, score, count))

    print(f"{total} đoạn · {len(frequency)} từ · {len(vocabulary)} từ qua sàn df")
    print(f"{len(neighbours)} từ có láng giềng · {len(records)} dòng sẽ ghi\n")

    sample = sorted(neighbours, key=lambda t: -frequency[t])[: args.show]
    print(f"{'từ':<12}{'láng giềng mạnh nhất':<60}")
    print("-" * 74)
    for term in sample:
        top = ", ".join(related for _, related, _ in neighbours[term][:6])
        print(f"{term:<12}{top:<60}")

    if not args.apply:
        print("\nCHẠY KHÔ — chưa ghi gì. Thêm --apply để ghi thật.")
        await close_db_pool()
        return 0

    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("TRUNCATE term_relatedness")
        await conn.executemany(
            "INSERT INTO term_relatedness (term, related, score, pair_df) "
            "VALUES ($1, $2, $3, $4)",
            records,
        )
    print(f"\nĐã ghi {len(records)} dòng vào term_relatedness.")
    await close_db_pool()
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
