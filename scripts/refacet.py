"""Recomputes the vehicle facet for every stored chunk, and says what moved.

The facet is derived from the CPHC prefix, which is already in the database,
so this is a backfill rather than a re-ingest: no parsing, no embedding, no
risk to `verbatim_text`.

It exists because a classifier change is invisible until the corpus is
relabelled, and because the size of the change is itself the thing worth
knowing. A silent UPDATE over 7,112 rows is not a measurement; a diff is.

The default prints what would change and writes nothing; `--apply` writes.
There is deliberately no `--dry-run` flag to forget.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.ingestion.facets import classify_context


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ghi thay đổi. Không có cờ này thì chỉ in ra, không ghi gì.",
    )
    parser.add_argument("--show", type=int, default=12, help="Số ví dụ in ra")
    args = parser.parse_args()

    db = await get_db_pool()
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.path::text AS path, c.contextualized_text, c.metadata,
                   d.doc_code
            FROM chunks c JOIN documents d ON d.id = c.document_id
            ORDER BY c.path
            """
        )

        changes: list[tuple[str, str, list[str], list[str]]] = []
        for row in rows:
            metadata = row["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            metadata = dict(metadata or {})
            before = list(metadata.get("vehicle_classes") or [])
            after = classify_context(row["contextualized_text"])
            if sorted(before) != sorted(after):
                changes.append((str(row["doc_code"]), str(row["path"]), before, after))

        print(f"{len(rows)} chunk, {len(changes)} thay đổi nhãn\n")

        kinds: Counter[str] = Counter()
        for _, _, before, after in changes:
            if before and not after:
                kinds["bỏ nhãn (điều khoản tổng quát)"] += 1
            elif not before and after:
                kinds["thêm nhãn"] += 1
            else:
                kinds["đổi nhãn"] += 1
        for kind, count in kinds.most_common():
            print(f"  {kind:34s} {count:5d}")

        if changes:
            print(f"\nVí dụ (tối đa {args.show}):")
            for doc, path, before, after in changes[: args.show]:
                print(f"  {doc:18s} {path[-28:]:30s} {before} -> {after}")

        if not args.apply:
            # Nothing may close the pool from in here. The connection is still
            # checked out from this `async with`, so `Pool.close()` waits for a
            # release that cannot happen until the block exits -- which stalled
            # the whole script for the 60 seconds asyncpg waits before warning
            # "Pool.close() is taking over 60 seconds". Fall through instead.
            print("\nCHƯA GHI GÌ. Thêm --apply để ghi.")
        else:
            # jsonb_set on one key rather than replacing metadata: the column
            # also carries provision_role and whatever ingestion recorded, and
            # rewriting the object would drop anything this script does not
            # know about.
            # `$2::text::jsonb`, not `$2::jsonb`. With the shorter cast
            # asyncpg infers the parameter as jsonb and encodes the Python str
            # as a JSON *scalar string*, so `["car"]` was stored as the string
            # "[\"car\"]" rather than an array. `?` returns false on a string,
            # so every labelled provision then took the mismatch penalty --
            # the same silent inversion as the delete branch below. Binding as
            # text and letting Postgres parse it is what makes it an array.
            # Two statements, not one CASE. The single-statement version passed
            # the text "null" and relied on `$2::jsonb = 'null'::jsonb` to
            # select a delete branch; it stored the JSON *string* `"null"`
            # instead of removing the key. Nothing errored, and the effect was
            # the opposite of the intent: search tests
            # `metadata->'vehicle_classes' IS NULL` to mean "no class", a JSON
            # string is not SQL NULL, so those provisions kept taking the 0.35
            # mismatch penalty this whole change exists to stop.
            async with conn.transaction():
                for row in rows:
                    after = classify_context(row["contextualized_text"])
                    if after:
                        await conn.execute(
                            """
                            UPDATE chunks
                               SET metadata = jsonb_set(
                                     COALESCE(metadata, '{}'::jsonb),
                                     '{vehicle_classes}', $2::text::jsonb, true)
                             WHERE id = $1
                            """,
                            row["id"],
                            json.dumps(after),
                        )
                    else:
                        await conn.execute(
                            "UPDATE chunks SET metadata = metadata - "
                            "'vehicle_classes' WHERE id = $1",
                            row["id"],
                        )
            print(f"\nĐã ghi {len(changes)} thay đổi.")

    await close_db_pool()
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
