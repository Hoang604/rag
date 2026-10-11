from __future__ import annotations

import asyncio
import datetime
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.schemas.retrieval import LegalSearchResult, ProvisionMatch

EVAL_CASES_PATH: Final = Path(__file__).resolve().parents[4] / "data" / "eval" / "retrieval.jsonl"
_CONCURRENCY: Final = 4

Split = Literal["dev", "holdout"]
FoundIn = Literal["both", "semantic_only", "verbatim_only", "missed"]


class EvalCase(BaseModel):
    """One question, the first `search` call an agent makes for it, and the provisions that answer it."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^e\d{3,}$")
    split: Split
    question: str = Field(min_length=1)
    query: str = Field(min_length=1)
    pattern: str = Field(min_length=1)
    is_regex: bool
    temporal_violation_date: datetime.date | None  # None: the question names no violation date, so search uses today
    doc_codes: list[str]
    expected: list[str] = Field(min_length=1, description="Any of these paths, or a provision under one, answers the question")
    note: str | None = None  # None: nothing about the label needs a reviewer's attention


class CaseOutcome(BaseModel):
    id: str
    split: Split
    found_in: FoundIn
    position: int | None  # None: missed; else 1-based rank inside its group
    matched_path: str | None  # None: missed


class CaseRun(BaseModel):
    outcome: CaseOutcome
    result: LegalSearchResult


class SplitSummary(BaseModel):
    split: Split
    total: int
    both: int
    semantic_only: int
    verbatim_only: int
    missed: int


class EvalRun(BaseModel):
    outcomes: list[CaseOutcome]
    summaries: list[SplitSummary]


def load_cases(path: Path = EVAL_CASES_PATH) -> list[EvalCase]:
    cases = [EvalCase.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate case ids")
    return cases


def save_cases(cases: Sequence[EvalCase], path: Path = EVAL_CASES_PATH) -> None:
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids")
    body = "".join(
        json.dumps(c.model_dump(mode="json"), ensure_ascii=False) + "\n" for c in sorted(cases, key=lambda c: c.id)
    )
    tmp = path.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


def _answers(path: str, expected: Sequence[str]) -> bool:
    return any(path == e or path.startswith(e + ".") for e in expected)


def score(case: EvalCase, result: LegalSearchResult) -> CaseOutcome:
    groups: list[tuple[FoundIn, list[ProvisionMatch]]] = [
        ("both", result.both),
        ("semantic_only", result.semantic_only),
        ("verbatim_only", result.verbatim_only),
    ]
    for name, hits in groups:
        for position, hit in enumerate(hits, start=1):
            if _answers(hit.path, case.expected):
                return CaseOutcome(id=case.id, split=case.split, found_in=name, position=position, matched_path=hit.path)
    return CaseOutcome(id=case.id, split=case.split, found_in="missed", position=None, matched_path=None)


async def run_case(tools: LegalMCPTools, case: EvalCase, limit: int = 10) -> CaseRun:
    result = await tools.search(
        query=case.query,
        pattern=case.pattern,
        is_regex=case.is_regex,
        temporal_violation_date=case.temporal_violation_date.isoformat() if case.temporal_violation_date else None,
        doc_codes=case.doc_codes or None,
        limit=limit,
    )
    return CaseRun(outcome=score(case, result), result=result)


def summarize(outcomes: Sequence[CaseOutcome]) -> list[SplitSummary]:
    summaries: list[SplitSummary] = []
    for split in ("dev", "holdout"):
        rows = [o for o in outcomes if o.split == split]
        summaries.append(
            SplitSummary(
                split=split,
                total=len(rows),
                both=sum(o.found_in == "both" for o in rows),
                semantic_only=sum(o.found_in == "semantic_only" for o in rows),
                verbatim_only=sum(o.found_in == "verbatim_only" for o in rows),
                missed=sum(o.found_in == "missed" for o in rows),
            )
        )
    return summaries


async def run_all(tools: LegalMCPTools, cases: Sequence[EvalCase], limit: int = 10) -> EvalRun:
    gate = asyncio.Semaphore(_CONCURRENCY)

    async def one(case: EvalCase) -> CaseOutcome:
        async with gate:
            return (await run_case(tools, case, limit)).outcome

    outcomes = list(await asyncio.gather(*(one(c) for c in cases)))
    return EvalRun(outcomes=outcomes, summaries=summarize(outcomes))
