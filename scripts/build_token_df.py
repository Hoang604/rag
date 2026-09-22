"""Counts how many provisions each word appears in, for the overlay's topic key.

Run once after ingestion, and again whenever the corpus changes. The counts
decide which words identify a question's subject and which are background, so
they have to come from this corpus rather than from a general Vietnamese
frequency list -- "phạt" is rare in Vietnamese and ubiquitous here.
"""

from __future__ import annotations

import asyncio
from collections import Counter

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.retrieval.annotations import content_tokens


async def main() -> int:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT contextualized_text FROM chunks")
        counts: Counter[str] = Counter()
        for row in rows:
            counts.update(content_tokens(str(row["contextualized_text"])))

        await conn.execute("TRUNCATE token_df")
        await conn.executemany(
            "INSERT INTO token_df (token, df) VALUES ($1, $2)",
            list(counts.items()),
        )

    print(f"{len(rows)} chunk -> {len(counts)} từ")
    print("\n15 từ phổ biến nhất (không mang chủ đề):")
    for token, df in counts.most_common(15):
        print(f"  {token:18s} {df:5d}")
    rare = [(t, c) for t, c in counts.items() if c >= 3]
    rare.sort(key=lambda kv: kv[1])
    print("\n15 từ hiếm nhất còn xuất hiện >=3 lần (mang chủ đề):")
    for token, df in rare[:15]:
        print(f"  {token:18s} {df:5d}")
    await close_db_pool()
    return 0


from rag_eval.legal.console import use_utf8_stdout

if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
