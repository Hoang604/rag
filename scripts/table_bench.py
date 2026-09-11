"""Scores table questions on the thing that lets a model answer them.

`qa_bench.py` scores at article level, which is right for prose: a question
about Điều 7 is answered by that article's neighbourhood. It is not right for a
table. Retrieving a paragraph of Điều 46 when the answer is a row of Bảng 4
counts as a hit there and answers nothing -- the figure is in the table and
nowhere else.

So this reports two numbers side by side:

  đúng Điều    the same measure the other sets use, kept so the two are
               comparable
  có bảng      whether a chunk that actually contains a Markdown table
               reached the top-k

  sau khi ghép the same, measured after `expand_windows` -- which is what
               `/answer` actually hands the model

The gap between the first two is the quantity of interest. A high first number
with a low second one means retrieval is landing in the right article and
handing the model the prose around the table instead of the table.

The third column exists because the second one was measuring the wrong path.
A long table is stored as sibling windows, and retrieval can land on the prose
window of the very provision that holds the table: all three of the remaining
misses were `a_12.c_2.p_b.w_5` and `a_46.c_3.p_dd.w_1`, prose windows sitting
next to the answer. `/answer` merges the siblings before the model sees them,
so scoring the raw hits understated the pipeline by a third of its misses.

Both are still reported. The raw column is what ranking has to improve; the
merged column is what a user gets. Collapsing them into one number would hide
whichever question you were not asking.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool
from rag_eval.legal.eval.smoke_runner import GroundTruth, _check_article_match
from rag_eval.legal.ingestion.tables import is_data_table
from rag_eval.legal.mcp.server import default_legal_tools
from rag_eval.legal.mcp.tools import SearchHit

FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "qrels_tables.jsonl"
)


def _has_table(hit: SearchHit) -> bool:
    text: str = hit.verbatim_text or ""
    return "---" in text and is_data_table(text.splitlines())


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(FIXTURE))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--show-misses", action="store_true")
    parser.add_argument(
        "--no-expand",
        action="store_true",
        help="bỏ cột sau-khi-ghép; chỉ đo kết quả thô như bản trước",
    )
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in Path(args.fixture).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    tools = default_legal_tools()
    at: dict[str, list[int]] = {
        "dieu": [0, 0, 0],
        "bang": [0, 0, 0],
        "ghep": [0, 0, 0],
    }
    misses: list[tuple[str, str, list[str]]] = []

    for row in rows:
        truth = GroundTruth.model_validate(row["ground_truth"])
        result = await tools.hybrid_search(query=str(row["query"]), limit=args.limit)
        hits = result.hits

        dieu_rank = next(
            (i for i, h in enumerate(hits, 1) if _check_article_match(h, truth)), None
        )
        bang_rank = next(
            (
                i
                for i, h in enumerate(hits, 1)
                if _has_table(h) and _check_article_match(h, truth)
            ),
            None,
        )
        # Ranks are compared before and after merging, so a table that only
        # appears once the siblings are joined is credited at the rank of the
        # window that pulled it in -- not at rank 1 for free.
        ghep_rank = bang_rank
        if not args.no_expand:
            merged = await tools.expand_windows(list(hits))
            ghep_rank = next(
                (
                    i
                    for i, h in enumerate(merged, 1)
                    if _has_table(h) and _check_article_match(h, truth)
                ),
                None,
            )

        for key, rank in (
            ("dieu", dieu_rank),
            ("bang", bang_rank),
            ("ghep", ghep_rank),
        ):
            for slot, k in enumerate((1, 3, 5)):
                if rank is not None and rank <= k:
                    at[key][slot] += 1
        if bang_rank is None:
            misses.append(
                (
                    str(row.get("table", "")),
                    str(row["query"]),
                    [h.path for h in hits[:3]],
                )
            )

    total = len(rows) or 1

    def pct(values: list[int]) -> str:
        return "  ".join(f"{v / total:6.1%}" for v in values)

    print(f"{len(rows)} câu hỏi bảng, top-{args.limit}\n")
    print(f"{'':22s}{'@1':>8s}{'@3':>8s}{'@5':>8s}")
    print("-" * 46)
    print(f"{'đúng Điều':22s}{pct(at['dieu'])}")
    print(f"{'lấy được đúng bảng':22s}{pct(at['bang'])}")
    if not args.no_expand:
        print(f"{'— sau khi ghép':22s}{pct(at['ghep'])}")

    if misses:
        print(
            f"\n{len(misses)} câu KHÔNG lấy được chunk bảng nào trong top-{args.limit}:"
        )
        seen: set[str] = set()
        for table, query, paths in misses:
            if table not in seen:
                seen.add(table)
                print(f"\n  [{table}]")
            print(f"    {query[:70]}")
            if args.show_misses:
                for p in paths:
                    print(f"        #{p[-40:]}")

    await close_db_pool()
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
