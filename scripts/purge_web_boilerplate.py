"""Finds chunks that are website furniture, not statutory text, and removes them.

The corpus was fetched from chinhphu.vn, and for three documents the scraper
kept reading past the end of the statute into the page's own chrome: a "Tham
khảo thêm" sidebar, unrelated news teasers, and the masthead ("Tổng Biên tập",
"Giấy phép số 19/GP-CBC"). Those paragraphs were then wrapped into `.w_2`..
`.w_5` continuation nodes hanging off the document's final article, so they
carry a real citation address -- `168/2024/NĐ-CP Điều 55` -- while containing
no law at all.

This is not cosmetic. Asked "Mức phạt với người chưa đủ tuổi điều khiển phương
tiện", retrieval put one of these at rank 1 with a cross-encoder score of
+2.03, above the genuine Điều 18 Khoản 6 at +1.91. The three-signal abstention
cannot catch it either: the text is fluent Vietnamese whose keywords match the
question, so `keyword_matched` is true and the rerank score is high. A wrong
answer with a correct-looking citation is the worst failure this project has.

Targeted by content signature, deliberately not by path shape. `.w_>=2` is a
legitimate structure -- 377 of them, almost all real continuation text -- so
deleting the shape would take 366 good chunks with the 11 bad ones.

The default prints what would go and writes nothing; `--apply` deletes.
Reversible either way: `legal-bootstrap` + `legal-promote` rebuild from source.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Final

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool, get_db_pool

# Markers of the page, never of the statute. Each was read in the offending
# chunks before being put here; none appears in any legitimate provision, which
# the script re-checks every run rather than trusting this comment.
MARKERS: Final[tuple[str, ...]] = (
    "Chinhphu.vn",
    "Tổng Biên tập",
    "GP-CBC",
    "PHỔ ĐIỂM",
    "Zalo",
)

# A statutory provision cites, defines, prescribes or penalises. If a candidate
# also reads like law, this script must not be the thing that decides -- it
# reports the collision and refuses instead.
LEGAL_MARKERS: Final[tuple[str, ...]] = (
    "Phạt tiền từ",
    "Phạt cảnh cáo",
    "trừ điểm giấy phép lái xe",
)

_PREDICATE: Final = " OR ".join(
    f"c.verbatim_text ILIKE ${i}" for i in range(1, len(MARKERS) + 1)
)
_PARAMS: Final = [f"%{m}%" for m in MARKERS]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Xoá thật. Không có cờ này thì chỉ in ra, không ghi gì.",
    )
    args = parser.parse_args()

    db = await get_db_pool()
    async with db.acquire() as conn:
        total = await conn.fetchval("SELECT count(*) FROM chunks")
        rows = await conn.fetch(
            f"""
            SELECT c.id, c.path::text AS path, d.doc_code,
                   length(c.verbatim_text) AS len,
                   regexp_replace(c.verbatim_text, '\\s+', ' ', 'g') AS text
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE {_PREDICATE}
            ORDER BY d.doc_code, c.path
            """,
            *_PARAMS,
        )

        print(f"{total} chunk trong corpus, {len(rows)} khớp dấu hiệu rác web\n")
        for row in rows:
            print(
                f"  {row['doc_code']:16s} {row['path'][-34:]:36s} {row['len']:5d} ký tự"
            )
            print(f"      {row['text'][:96]}")

        # The one thing that would make deleting wrong.
        suspect = [
            row
            for row in rows
            if any(marker in row["text"] for marker in LEGAL_MARKERS)
        ]
        if suspect:
            print(
                f"\nDỪNG LẠI: {len(suspect)} chunk vừa có dấu hiệu rác vừa có văn "
                "luật thật. Phải đọc tay, script không tự quyết."
            )
            for row in suspect:
                print(f"  {row['doc_code']} {row['path']}")
            deletable: list[object] = []
        else:
            deletable = [row["id"] for row in rows]

        if not args.apply:
            # Nothing may close the pool from inside here -- the connection is
            # still checked out, so `Pool.close()` would wait for a release
            # that cannot happen until this block exits.
            print(f"\nCHƯA XOÁ GÌ. Thêm --apply để xoá {len(deletable)} chunk.")
        elif deletable:
            async with conn.transaction():
                gone = await conn.fetchval(
                    "WITH d AS (DELETE FROM chunks WHERE id = ANY($1::uuid[]) "
                    "RETURNING 1) SELECT count(*) FROM d",
                    deletable,
                )
            print(f"\nĐã xoá {gone} chunk. Còn {total - gone} chunk.")
        else:
            print("\nKhông xoá gì.")

    await close_db_pool()
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
