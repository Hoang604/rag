from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Final

from rag_eval.legal.answer import AnswerError, answer_with_agent, unsupported_claims
from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.db.repositories import LegalRepository
from rag_eval.legal.eval.answers import (
    AnswerCase,
    grade_answer,
    is_quota_error,
    load_answer_cases,
)
from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.schemas.retrieval import SearchHit

ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_OUT: Final = ROOT / "experiments" / "runs" / "answer_eval.jsonl"


def read_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_row(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


async def answer_case(case: AnswerCase, provider: str, tools: LegalMCPTools) -> dict[str, object]:
    repository = LegalRepository(await get_db_pool())

    async def hits_for_paths(paths: list[str]) -> list[SearchHit]:
        return await tools.annotate_amendments(await repository.chunks.get_hits_by_paths(paths))

    started = time.perf_counter()
    try:
        result = await answer_with_agent(provider, case.question, hits_for_paths)
    except AnswerError as exc:
        message = str(exc)
        return {
            "id": case.id,
            "error": message[:400],
            "quota": is_quota_error(message),
            "ms": round((time.perf_counter() - started) * 1000.0, 1),
        }
    cited = [hit.path for hit in result.hits]
    grade = grade_answer(case, result.answer, cited, result.grounding.ok, unsupported_claims(result.grounding))
    return {
        "id": case.id,
        "in_scope": case.in_scope,
        "question": case.question,
        "answer": result.answer,
        "cited": cited,
        "attempts": result.attempts,
        "ms": round((time.perf_counter() - started) * 1000.0, 1),
        "cost_usd": result.cost_usd,
        **grade.model_dump(),
    }


def verdict(row: dict[str, object]) -> str:
    if "error" in row:
        return "LỖI"
    return "ĐÚNG" if row["correct"] else "sai "


async def run(cases: list[AnswerCase], out: Path, provider: str, budget: float) -> None:
    done = {str(r["id"]) for r in read_rows(out) if "error" not in r}
    spent = sum(float(str(r.get("cost_usd") or 0)) for r in read_rows(out))
    tools = LegalMCPTools.build()
    try:
        for case in cases:
            if case.id in done:
                continue
            if spent >= budget:
                print(f"dừng: đã tiêu {spent:.2f} USD, ngân sách {budget:.2f} USD", flush=True)
                break
            row = await answer_case(case, provider, tools)
            append_row(out, row)
            spent += float(str(row.get("cost_usd") or 0))
            detail = row.get("error") or row.get("answer") or ""
            print(f"{case.id} {verdict(row)} {float(str(row['ms'])) / 1000:5.0f}s {str(detail)[:90]!r}", flush=True)
            if row.get("quota"):
                print("dừng: hết hạn mức của provider; chạy lại sau để tiếp tục", flush=True)
                break
    finally:
        await close_db_pool()


def pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):5.1f}%" if values else "    -"


def failure_reasons(row: dict[str, object]) -> list[str]:
    checks = (
        ("từ chối", not row["refused"]),
        ("sai Điều", row["cite_article"]),
        (f"thiếu số tiền {row['missing_amounts']}", row["amounts_ok"]),
        (f"thiếu dữ kiện {row['missing_facts']}", row["facts_ok"]),
        (f"không bám nguồn {row['unsupported']}", row["grounded"]),
    )
    return [name for name, ok in checks if not ok]


def report(cases: list[AnswerCase], out: Path) -> None:
    by_id = {case.id: case for case in cases}
    latest: dict[str, dict[str, object]] = {}
    for row in read_rows(out):
        if str(row["id"]) in by_id and ("error" not in row or str(row["id"]) not in latest or "error" in latest[str(row["id"])]):
            latest[str(row["id"])] = row
    errors = [r for r in latest.values() if "error" in r]
    rows = [r for r in latest.values() if "error" not in r]
    inside = [r for r in rows if by_id[str(r["id"])].in_scope]
    outside = [r for r in rows if not by_id[str(r["id"])].in_scope]
    keyed = [r for r in inside if by_id[str(r["id"])].amounts or by_id[str(r["id"])].facts]
    print(f"CÂU TRẢ LỜI CUỐI: {len(rows)}/{len(cases)} câu đã chấm, {len(errors)} lỗi (không tính điểm)")
    print(f"  đúng toàn phần (trong phạm vi)   {pct([bool(r['correct']) for r in inside])}  (n={len(inside)})")
    print(f"  trích đúng Điều                  {pct([bool(r['cite_article']) for r in inside])}")
    print(f"  trích đúng Khoản/Điểm            {pct([bool(r['cite_exact']) for r in inside])}")
    print(f"  đủ số tiền và dữ kiện            {pct([bool(r['amounts_ok'] and r['facts_ok']) for r in keyed])}  (n={len(keyed)})")
    print(f"  số liệu bám nguồn (grounding)    {pct([bool(r['grounded']) for r in rows])}")
    print(f"  từ chối nhầm câu trong phạm vi   {pct([bool(r['refused']) for r in inside])}")
    print(f"  từ chối đúng câu ngoài phạm vi   {pct([bool(r['correct']) for r in outside])}  (n={len(outside)})")
    latencies = sorted(float(str(r["ms"])) for r in rows)
    if latencies:
        print(f"  thời gian trung vị {latencies[len(latencies) // 2] / 1000:.0f}s, chậm nhất {latencies[-1] / 1000:.0f}s")
    costs = [float(str(r["cost_usd"])) for r in rows if r.get("cost_usd") is not None]
    if costs:
        print(f"  chi phí {sum(costs):.2f} USD, trung bình {sum(costs) / len(costs):.3f} USD/câu")
    by_style: dict[str, list[bool]] = defaultdict(list)
    for r in inside:
        by_style[by_id[str(r["id"])].style].append(bool(r["correct"]))
    for style, values in sorted(by_style.items()):
        print(f"    {style:12s} n={len(values):3d} đúng {pct(values)}")
    wrong = [r for r in rows if not r["correct"]]
    if wrong:
        print("\n  Câu sai:")
        for r in sorted(wrong, key=lambda r: str(r["id"])):
            case = by_id[str(r["id"])]
            reasons = failure_reasons(r) if case.in_scope else ["không từ chối"]
            print(f"    {r['id']} [{'; '.join(reasons)}] {case.question[:70]}")
    if errors:
        print("\n  Lỗi:")
        for r in sorted(errors, key=lambda r: str(r["id"])):
            print(f"    {r['id']} {str(r['error'])[:120]}")


def regrade(cases: list[AnswerCase], out: Path) -> None:
    by_id = {case.id: case for case in cases}
    rows = read_rows(out)
    for row in rows:
        case = by_id.get(str(row["id"]))
        if case is None or "error" in row:
            continue
        cited = row["cited"]
        unsupported = row["unsupported"]
        grade = grade_answer(
            case,
            str(row["answer"]),
            [str(path) for path in cited] if isinstance(cited, list) else [],
            bool(row["grounded"]),
            [str(claim) for claim in unsupported] if isinstance(unsupported, list) else [],
        )
        row.update(grade.model_dump())
    out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chấm câu trả lời cuối của chế độ agent trên data/eval/answers.jsonl")
    parser.add_argument("--provider", default="claude")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--budget", type=float, default=float("inf"), help="dừng khi tổng chi phí trong file kết quả vượt mức này (USD)")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--regrade", action="store_true", help="chấm lại các câu trả lời đã lưu bằng bộ chấm hiện tại, không gọi agent")
    args = parser.parse_args()

    cases = load_answer_cases()
    selected = [case for case in cases if case.id in set(args.only)] if args.only else cases
    if args.regrade:
        regrade(cases, args.out)
    elif not args.report:
        asyncio.run(run(selected, args.out, args.provider, args.budget))
    report(selected, args.out)
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    sys.exit(main())
