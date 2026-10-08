from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from rag_eval.legal.console import use_utf8_stdout
from rag_eval.legal.eval.smoke_runner import (
    GroundTruth,
    _check_article_match,
    _check_citation_exactness,
)
from rag_eval.legal.mcp.tools import SearchHit
from rag_eval.legal.text import fold_diacritics

ROOT: Final = Path(__file__).resolve().parents[1]
QUESTIONS: Final = ROOT / "tests" / "fixtures" / "user_questions.jsonl"
RUNS: Final = ROOT / "experiments" / "runs"
RETRIEVAL_DEPTH: Final = 10

REFUSAL_MARKERS: Final = (
    "khong tim thay",
    "khong tim duoc",
    "khong co can cu",
    "khong du can cu",
    "khong co quy dinh",
    "khong quy dinh",
    "khong thuoc pham vi",
    "ngoai pham vi",
    "khong co dieu khoan",
    "khong du dieu khoan",
    "chua tim thay",
    "chua co du lieu",
    "khong co du lieu",
    "khong co thong tin",
)
PROVIDER_FAILURES: Final = ("session limit", "usage limit", "rate limit", "hit your limit")

UNIT_MULTIPLIER: Final = {
    "trieu": 1_000_000,
    "tr": 1_000_000,
    "nghin": 1_000,
    "ngan": 1_000,
    "k": 1_000,
}
UNIT_PATTERN: Final = r"(trieu|tr|nghin|ngan|k)\b"
NUMBER_PATTERN: Final = r"\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?"
RANGE_RE: Final = re.compile(
    rf"({NUMBER_PATTERN})\s*(?:-|–|den|toi)\s*({NUMBER_PATTERN})\s*{UNIT_PATTERN}"
)
SINGLE_RE: Final = re.compile(rf"({NUMBER_PATTERN})\s*(?:{UNIT_PATTERN}|(dong))?")


@dataclass(frozen=True)
class Question:
    id: str
    query: str
    topic: str
    style: str
    in_scope: bool
    targets: list[GroundTruth]
    amounts: list[int] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Question:
        expected = row.get("expected", {})
        return cls(
            id=row["id"],
            query=row["query"],
            topic=row["topic"],
            style=row["style"],
            in_scope=row["in_scope"],
            targets=[GroundTruth.model_validate(t) for t in row.get("targets", [])],
            amounts=[int(a) for a in expected.get("amounts", [])],
            facts=list(expected.get("facts", [])),
        )


def load_questions(path: Path) -> list[Question]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Question.from_row(json.loads(line)) for line in lines if line.strip()]


def as_hit(doc_code: str, path: str) -> SearchHit:
    return SearchHit(
        chunk_id="", doc_code=doc_code, doc_title="", path=path,
        verbatim_text="", contextualized_text="", effective_date="", score=0.0,
    )


def first_rank(hits: list[SearchHit], question: Question, exact: bool) -> int | None:
    check = _check_citation_exactness if exact else _check_article_match
    return next(
        (rank for rank, hit in enumerate(hits, 1) if any(check(hit, t) for t in question.targets)),
        None,
    )


def normalize(text: str) -> str:
    folded = fold_diacritics(text.lower()).replace("đ", "d")
    folded = re.sub(r"(?<![\d.,])0+(\d)", r"\1", folded)
    folded = re.sub(r"(\d)\s+(km|met|m\b)", r"\1\2", folded)
    return re.sub(r"\s+", " ", folded)


def to_number(token: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
        return float(token.replace(".", ""))
    return float(token.replace(",", "."))


def amounts_in(text: str) -> set[int]:
    folded = normalize(text)
    found: set[int] = set()
    for low, high, unit in RANGE_RE.findall(folded):
        found |= {round(to_number(low) * UNIT_MULTIPLIER[unit]), round(to_number(high) * UNIT_MULTIPLIER[unit])}
    for number, unit, dong in SINGLE_RE.findall(folded):
        value = to_number(number)
        if unit:
            found.add(round(value * UNIT_MULTIPLIER[unit]))
        elif dong or value >= 1000:
            found.add(round(value))
    return found


def fact_present(fact: str, answer: str) -> bool:
    folded = normalize(answer)
    return any(normalize(option) in folded for option in fact.split("|"))


def refuses(answer: str) -> bool:
    folded = normalize(answer)
    return any(marker in folded for marker in REFUSAL_MARKERS)


def grade_answer(question: Question, response: dict[str, Any]) -> dict[str, Any]:
    answer = str(response.get("answer", ""))
    cited = [as_hit(h["doc_code"], h["path"]) for h in response.get("hits", [])]
    refused = bool(response.get("abstained")) or not cited
    grounding = response.get("grounding", {})
    row: dict[str, Any] = {
        "refused": refused,
        "grounded": bool(grounding.get("ok", True)),
        "unsupported": grounding.get("unsupported_amounts", []) + grounding.get("unsupported_articles", []),
    }
    if not question.in_scope:
        row["correct"] = refused or refuses(answer)
        return row
    found = amounts_in(answer)
    row["cite_article"] = first_rank(cited, question, exact=False) is not None
    row["cite_exact"] = first_rank(cited, question, exact=True) is not None
    row["amounts_ok"] = all(a in found for a in question.amounts)
    row["facts_ok"] = all(fact_present(f, answer) for f in question.facts)
    row["has_key"] = bool(question.amounts or question.facts)
    row["correct"] = (
        not refused and row["cite_article"] and row["amounts_ok"] and row["facts_ok"] and row["grounded"]
    )
    return row


def pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):5.1f}" if values else "    -"


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


async def run_retrieval(questions: list[Question], out: Path) -> None:
    from bench import CachedEmbedder

    from rag_eval.legal.db.connection import close_db_pool
    from rag_eval.legal.mcp.tools import LegalMCPTools

    tools = LegalMCPTools.build(embedding_engine=CachedEmbedder())
    done = {r["id"] for r in read_rows(out)}
    try:
        for question in questions:
            if question.id in done:
                continue
            started = time.perf_counter()
            result = await tools.hybrid_search(query=question.query, limit=RETRIEVAL_DEPTH)
            hits = list(result.hits)
            append_row(out, {
                "id": question.id,
                "confidence": result.confidence,
                "article_rank": first_rank(hits, question, exact=False) if question.in_scope else None,
                "exact_rank": first_rank(hits, question, exact=True) if question.in_scope else None,
                "top": [f"{h.doc_code}:{h.path}" for h in hits[:3]],
                "ms": round((time.perf_counter() - started) * 1000, 1),
            })
    finally:
        await close_db_pool()


def run_answers(questions: list[Question], out: Path, mode: str, provider: str) -> None:
    from fastapi.testclient import TestClient

    from rag_eval.legal.web.app import create_app

    done = {r["id"] for r in read_rows(out) if "error" not in r}
    with TestClient(create_app()) as client:
        for question in questions:
            if question.id in done:
                continue
            started = time.perf_counter()
            response = client.post(
                "/api/answer", json={"query": question.query, "mode": mode, "provider": provider}
            )
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            if response.status_code != 200:
                append_row(out, {"id": question.id, "error": response.text[:300], "ms": elapsed})
                print(f"{question.id} lỗi {response.status_code}", flush=True)
                continue
            payload = response.json()
            if any(marker in payload["answer"].lower() for marker in PROVIDER_FAILURES):
                append_row(out, {"id": question.id, "error": payload["answer"][:300], "ms": elapsed})
                print(f"{question.id} lỗi: {payload['answer'][:80]}", flush=True)
                continue
            row = {
                "id": question.id,
                "answer": payload["answer"],
                "cited": [f"{h['doc_code']}:{h['path']}" for h in payload["hits"]],
                "ms": elapsed,
                **grade_answer(question, payload),
            }
            append_row(out, row)
            print(f"{question.id} {'ĐÚNG' if row['correct'] else 'sai '} {question.query[:60]}", flush=True)


def report_retrieval(questions: dict[str, Question], rows: list[dict[str, Any]]) -> None:
    answerable = [r for r in rows if questions[r["id"]].in_scope]
    outside = [r for r in rows if not questions[r["id"]].in_scope]

    def line(label: str, part: list[dict[str, Any]]) -> None:
        ranks = [r["article_rank"] for r in part]
        exact = [r["exact_rank"] for r in part]
        mrr = statistics.fmean(1 / r if r else 0.0 for r in ranks) if ranks else 0.0
        print(
            f"{label:22s} {len(part):4d} {pct([bool(r and r <= 1) for r in ranks])} "
            f"{pct([bool(r and r <= 3) for r in ranks])} {pct([bool(r and r <= 5) for r in ranks])} "
            f"{pct([bool(r and r <= 10) for r in ranks])} {mrr:6.3f} {pct([bool(r and r <= 5) for r in exact])}"
        )

    print(f"\nTÌM KIẾM (hybrid_search, top {RETRIEVAL_DEPTH})")
    print(f"{'nhóm':22s} {'n':>4s} {'@1':>5s} {'@3':>5s} {'@5':>5s} {'@10':>5s} {'MRR':>6s} {'đúng điểm@5':>5s}")
    line("tất cả", answerable)
    for style in sorted({questions[r["id"]].style for r in answerable}):
        line(f"  {style}", [r for r in answerable if questions[r["id"]].style == style])
    for topic in sorted({questions[r["id"]].topic for r in answerable}):
        line(f"  #{topic}", [r for r in answerable if questions[r["id"]].topic == topic])
    if outside:
        weak = [r["confidence"] in ("none", "low") for r in outside]
        print(f"ngoài phạm vi: {len(outside)} câu, độ tin cậy none/low ở {pct(weak).strip()}%")


def report_answers(questions: dict[str, Question], rows: list[dict[str, Any]]) -> None:
    errors = [r for r in rows if "error" in r]
    rows = [r for r in rows if "error" not in r]
    inside = [r for r in rows if questions[r["id"]].in_scope]
    outside = [r for r in rows if not questions[r["id"]].in_scope]
    keyed = [r for r in inside if r["has_key"]]
    print(f"\nCÂU TRẢ LỜI CUỐI ({len(rows)} câu, {len(errors)} lỗi)")
    print(f"  đúng toàn phần (trong phạm vi)   {pct([r['correct'] for r in inside])}%")
    print(f"  trích đúng Điều                  {pct([r['cite_article'] for r in inside])}%")
    print(f"  trích đúng Khoản/Điểm            {pct([r['cite_exact'] for r in inside])}%")
    print(f"  đúng số tiền / dữ kiện chính     {pct([r['amounts_ok'] and r['facts_ok'] for r in keyed])}%  (n={len(keyed)})")
    print(f"  số liệu bám nguồn (grounding)    {pct([r['grounded'] for r in rows])}%")
    print(f"  từ chối nhầm câu trong phạm vi   {pct([r['refused'] for r in inside])}%")
    print(f"  từ chối đúng câu ngoài phạm vi   {pct([r['correct'] for r in outside])}%  (n={len(outside)})")
    latencies = sorted(r["ms"] for r in rows)
    if latencies:
        print(f"  thời gian trung vị {latencies[len(latencies) // 2] / 1000:.1f}s, chậm nhất {latencies[-1] / 1000:.1f}s")
    by_style: dict[str, list[bool]] = defaultdict(list)
    for r in inside:
        by_style[questions[r["id"]].style].append(r["correct"])
    for style, values in sorted(by_style.items()):
        print(f"    {style:12s} n={len(values):3d} đúng {pct(values)}%")
    wrong = [r for r in inside if not r["correct"]]
    if wrong:
        print("\n  Câu sai:")
        for r in wrong:
            reasons = [
                name for name, ok in (
                    ("từ chối", not r["refused"]), ("sai Điều", r["cite_article"]),
                    ("sai số tiền", r["amounts_ok"]), ("thiếu dữ kiện", r["facts_ok"]),
                    ("số liệu không bám nguồn", r["grounded"]),
                ) if not ok
            ]
            print(f"    {r['id']} [{', '.join(reasons)}] {questions[r['id']].query[:70]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("retrieval", "answer", "report"))
    parser.add_argument("--mode", choices=("agent", "retrieve"), default="agent")
    parser.add_argument("--provider", default="claude")
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--tag", default="")
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()

    questions = load_questions(args.questions)
    if args.only:
        questions = [q for q in questions if q.id in set(args.only)]
    suffix = f"_{args.tag}" if args.tag else ""
    retrieval_out = RUNS / f"eval_retrieval{suffix}.jsonl"
    answer_out = RUNS / f"eval_answer_{args.mode}_{args.provider}{suffix}.jsonl"

    if args.stage == "retrieval":
        asyncio.run(run_retrieval(questions, retrieval_out))
    elif args.stage == "answer":
        run_answers(questions, answer_out, args.mode, args.provider)

    by_id = {q.id: q for q in load_questions(args.questions)}
    if retrieval_out.exists():
        report_retrieval(by_id, read_rows(retrieval_out))
    if answer_out.exists():
        report_answers(by_id, read_rows(answer_out))
    return 0


if __name__ == "__main__":
    use_utf8_stdout()
    sys.exit(main())
