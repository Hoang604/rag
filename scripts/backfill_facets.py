"""Stamps the retrieval facets onto chunks already in the database.

The loader sets it on every future ingest. This exists so the 7,112 rows that
predate the facet do not have to be re-embedded to acquire it -- the class is
read off the CPHC prefix, which is already stored.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.ingestion.facets import classify_context, classify_role

BATCH = 500


async def main() -> int:
    pool = await get_db_pool()
    counts: Counter[str] = Counter()
    updates: list[tuple[str, dict[str, object]]] = []

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT path::text AS path, contextualized_text, metadata,"
            " jsonb_typeof(metadata) AS stored_type FROM chunks"
        )
        for row in rows:
            facets = {
                "vehicle_classes": classify_context(row["contextualized_text"]) or None,
                "provision_role": classify_role(row["contextualized_text"]),
            }
            facets = {k: v for k, v in facets.items() if v is not None}
            if not facets:
                counts["none"] += 1
                continue
            raw = row["metadata"]
            current = raw if isinstance(raw, dict) else json.loads(raw or "{}")
            # stored_type guards the repair case: a row double-encoded by an
            # earlier run decodes to the right dict but is stored as a jsonb
            # string scalar, where every metadata->>'key' against it reads NULL.
            if row["stored_type"] == "object" and all(
                current.get(k) == v for k, v in facets.items()
            ):
                counts["unchanged"] += 1
                continue
            for value in facets.values():
                for label in value if isinstance(value, list) else [value]:
                    counts[label] += 1
            updates.append((row["path"], {**current, **facets}))

        for start in range(0, len(updates), BATCH):
            await conn.executemany(
                "UPDATE chunks SET metadata = $2::jsonb WHERE path = $1::ltree",
                updates[start : start + BATCH],
            )

    for label, count in counts.most_common():
        print(f"  {label:16s} {count}")
    print(f"updated {len(updates)} chunks")
    await close_db_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
