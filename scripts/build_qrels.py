"""Turns verified agent-written questions into clause-level qrels.

Sprint 2 asks for ~200 queries with Khoản-level ground truth, split and sealed.
The 128 fixtures already carry that granularity but not that count, and 40
questions cannot resolve the five-point differences the baselines now turn on:
`dense` leads the shipped configuration by 5.0 on `test` and trails it by 2.0
on `dev`, which at those sizes is two questions against one.

The questions come from the agent-written slices rather than templates, and
their ground truth is read off the path each was written from rather than
retyped, so grading stays a comparison instead of an opinion. Every path is
checked against the corpus first: a question whose answer has moved is dropped
rather than scored against an address that no longer exists.

The split is stratified by question style, because the styles are the point.
`no_diacritics`, `colloquial` and `duty_rule` are where the system is weakest,
and an unstratified sample would leave the rare ones on one side.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Final

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.ingestion.xref import address_of_path

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

# Path prefixes are slugged document codes; the qrels name the real code.
_DOC_CODES = {
    "100_2019_nd_cp": "100/2019/ND-CP",
    "12_2025_tt_bca": "12/2025/TT-BCA",
    "151_2024_nd_cp": "151/2024/ND-CP",
    "168_2024_nd_cp": "168/2024/ND-CP",
    "184_2025_nd_cp": "184/2025/ND-CP",
    "236_2026_nd_cp": "236/2026/ND-CP",
    "238_2026_nd_cp": "238/2026/ND-CP",
    "38_2024_tt_bgtvt": "38/2024/TT-BGTVT",
    "49_vbhn_vpqh": "49/VBHN-VPQH",
    "55_vbhn_vpqh": "55/VBHN-VPQH",
    "65_2024_tt_bca": "65/2024/TT-BCA",
    "90_vbhn_vpqh": "90/VBHN-VPQH",
    "qcvn41_2024_bgtvt": "QCVN41/2024/BGTVT",
}


# A question built from an article heading -- "quy định về dừng xe, đỗ xe?" --
_HEADING_STYLES: Final = frozenset({"gen_rule", "gen_rule_alt", "gen_rule_where"})


def _ground_truth(path: str, article_only: bool = False) -> dict[str, Any] | None:
    """Reads the citation a path encodes, or gives up rather than guessing."""
    slug = path.split(".", 1)[0]
    doc_code = _DOC_CODES.get(slug)
    if doc_code is None:
        return None

    address = address_of_path(path)
    if not address.dieu:
        # Appendix provisions carry no Điều, so they are addressed by prefix.
        return {"doc_code": doc_code, "path_suffix": path.rsplit(".", 1)[0]}

    # "18a" is a real article number, not a malformed one.
    dieu: int | str = int(address.dieu) if address.dieu.isdigit() else address.dieu
    truth: dict[str, Any] = {"doc_code": doc_code, "article": dieu}
    if article_only:
        return truth
    if address.khoan and address.khoan.isdigit():
        truth["clause"] = int(address.khoan)
    if address.diem:
        truth["point"] = address.diem
    return truth


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="JSONL of query + source_path")
    parser.add_argument("--dev-size", type=int, default=200)
    parser.add_argument(
        "--prefix",
        default="qrels",
        help=(
            "Output basename. Defaults to the agent-written set; pass another "
            "to avoid overwriting it, and keep sources in separate files -- "
            "machine-generated questions are not the same evidence as "
            "agent-written ones and mixing them hides that."
        ),
    )
    parser.add_argument("--seed", type=int, default=20260906)
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in args.inputs:
        direct = Path(pattern)
        found = [direct] if direct.exists() else sorted(Path().glob(pattern))
        for path in found:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                key = row["query"].casefold()
                if key in seen or not row.get("source_path"):
                    continue
                seen.add(key)
                rows.append(row)

    db = await get_db_pool()
    async with db.acquire() as conn:
        live = {
            r["path"] for r in await conn.fetch("SELECT path::text AS path FROM chunks")
        }
    await close_db_pool()

    built: list[dict[str, Any]] = []
    dropped = 0
    for index, row in enumerate(rows):
        source = str(row["source_path"])
        if source not in live:
            dropped += 1
            continue
        style = str(row.get("style") or "")
        truth = _ground_truth(source, article_only=style in _HEADING_STYLES)
        if truth is None:
            dropped += 1
            continue
        built.append(
            {
                "id": f"q{index:04d}",
                "query": row["query"],
                "domain": row.get("style", "unknown"),
                "source_path": source,
                "ground_truth": truth,
            }
        )

    by_style: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in built:
        by_style[item["domain"]].append(item)

    rng = random.Random(args.seed)
    dev: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    share = args.dev_size / len(built) if built else 0.0
    for style, items in sorted(by_style.items()):
        rng.shuffle(items)
        cut = round(len(items) * share)
        dev.extend(items[:cut])
        holdout.extend(items[cut:])

    for name, items in (
        (f"{args.prefix}_dev", dev),
        (f"{args.prefix}_holdout", holdout),
    ):
        target = FIXTURES / f"{name}.jsonl"
        target.write_text(
            "\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n",
            encoding="utf-8",
        )
        print(f"{len(items):4d} câu -> {target.name}")

    print(f"\n{len(rows)} câu vào, {dropped} bỏ (path không còn tồn tại)")
    levels = {"Điểm": 0, "Khoản": 0, "Điều": 0, "path": 0}
    for item in built:
        truth = item["ground_truth"]
        key = (
            "Điểm"
            if truth.get("point")
            else "Khoản"
            if truth.get("clause")
            else "Điều"
            if truth.get("article")
            else "path"
        )
        levels[key] += 1
    print("Độ mịn ground truth: " + "  ".join(f"{k} {v}" for k, v in levels.items()))
    print("\nPhân bố dev theo phong cách:")
    dev_styles: dict[str, int] = defaultdict(int)
    for item in dev:
        dev_styles[item["domain"]] += 1
    for style, n in sorted(dev_styles.items(), key=lambda kv: -kv[1]):
        print(f"  {style:22s} {n:3d}")
    return 0


from rag_eval.legal.console import use_utf8_stdout

if __name__ == "__main__":
    use_utf8_stdout()
    raise SystemExit(asyncio.run(main()))
