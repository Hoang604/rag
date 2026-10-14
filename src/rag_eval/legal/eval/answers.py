from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from rag_eval.legal.text import fold_diacritics

ANSWER_CASES_PATH: Final = Path(__file__).resolve().parents[4] / "data" / "eval" / "answers.jsonl"

REFUSAL_MARKERS: Final = (
    "khong tim thay",
    "khong tim duoc",
    "khong co can cu",
    "khong du can cu",
    "chua du can cu",
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
QUOTA_MARKERS: Final = (
    "session limit",
    "usage limit",
    "rate limit",
    "hit your limit",
    "limit reached",
    "credit balance",
)

_UNIT_MULTIPLIER: Final = {"trieu": 1_000_000, "tr": 1_000_000, "nghin": 1_000, "ngan": 1_000, "k": 1_000}
_UNIT: Final = r"(trieu|tr|nghin|ngan|k)\b"
_NUMBER: Final = r"\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?"
_RANGE_RE: Final = re.compile(rf"({_NUMBER})\s*(?:-|–|—|den|toi)\s*({_NUMBER})\s*{_UNIT}")
_SINGLE_RE: Final = re.compile(rf"({_NUMBER})\s*(?:{_UNIT}|(dong))?")
_ARTICLE_SEGMENT: Final = re.compile(r"^(.*?\ba_[0-9a-z]+)(?:\.|$)")


class AnswerCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[uo]\d{3}$")
    question: str = Field(min_length=1)
    in_scope: bool
    topic: str
    style: str
    source: str
    expected: list[str]
    amounts: list[int]
    facts: list[str] = Field(description="Each fact must appear in the answer; `|` separates equivalent wordings")
    note: str | None = None


class AnswerGrade(BaseModel):
    refused: bool
    grounded: bool
    unsupported: list[str]
    correct: bool
    cite_article: bool | None = None
    cite_exact: bool | None = None
    amounts_ok: bool | None = None
    facts_ok: bool | None = None
    missing_amounts: list[int] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)


def load_answer_cases(path: Path = ANSWER_CASES_PATH) -> list[AnswerCase]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [AnswerCase.model_validate_json(line) for line in lines if line.strip()]


def normalize(text: str) -> str:
    folded = fold_diacritics(text.lower())
    folded = re.sub(r"(?<![\d.,])0+(\d)", r"\1", folded)
    folded = re.sub(r"(\d)\s+(km|met|m\b)", r"\1\2", folded)
    return re.sub(r"\s+", " ", folded)


def _to_number(token: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
        return float(token.replace(".", ""))
    return float(token.replace(",", "."))


def amounts_in(text: str) -> set[int]:
    folded = normalize(text)
    found: set[int] = set()
    for low, high, unit in _RANGE_RE.findall(folded):
        multiplier = _UNIT_MULTIPLIER[unit]
        found |= {round(_to_number(low) * multiplier), round(_to_number(high) * multiplier)}
    for number, unit, dong in _SINGLE_RE.findall(folded):
        value = _to_number(number)
        if unit:
            found.add(round(value * _UNIT_MULTIPLIER[unit]))
        elif dong or value >= 1000:
            found.add(round(value))
    return found


def fact_present(fact: str, text: str) -> bool:
    folded = normalize(text)
    return any(normalize(option) in folded for option in fact.split("|"))


def refuses(text: str) -> bool:
    folded = normalize(text)
    return any(marker in folded for marker in REFUSAL_MARKERS)


def is_quota_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in QUOTA_MARKERS)


def _article_of(path: str) -> str:
    match = _ARTICLE_SEGMENT.match(path)
    return match.group(1) if match else path


def _at_or_under(path: str, ancestor: str) -> bool:
    return path == ancestor or path.startswith(ancestor + ".")


def cites_exact(cited: list[str], expected: list[str]) -> bool:
    return any(_at_or_under(path, target) for path in cited for target in expected)


def cites_article(cited: list[str], expected: list[str]) -> bool:
    return any(_at_or_under(path, _article_of(target)) for path in cited for target in expected)


def grade_answer(
    case: AnswerCase, answer: str, cited: list[str], grounding_ok: bool, unsupported: list[str]
) -> AnswerGrade:
    refused = not cited
    if not case.in_scope:
        return AnswerGrade(
            refused=refused,
            grounded=grounding_ok,
            unsupported=unsupported,
            correct=refused or refuses(answer),
        )
    found = amounts_in(answer)
    missing_amounts = [amount for amount in case.amounts if amount not in found]
    missing_facts = [fact for fact in case.facts if not fact_present(fact, answer)]
    cite_article = cites_article(cited, case.expected)
    return AnswerGrade(
        refused=refused,
        grounded=grounding_ok,
        unsupported=unsupported,
        cite_article=cite_article,
        cite_exact=cites_exact(cited, case.expected),
        amounts_ok=not missing_amounts,
        facts_ok=not missing_facts,
        missing_amounts=missing_amounts,
        missing_facts=missing_facts,
        correct=not refused and cite_article and not missing_amounts and not missing_facts and grounding_ok,
    )
