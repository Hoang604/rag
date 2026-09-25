from __future__ import annotations

import argparse
import asyncio
from typing import Final

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool, get_db_pool

MARKERS: Final[tuple[str, ...]] = (
    "Chinhphu.vn",
    "Tổng Biên tập",
    "GP-CBC",
    "PHỔ ĐIỂM",
    "Zalo",
)

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
