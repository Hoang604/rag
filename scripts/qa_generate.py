"""Generates questions from the corpus itself, so the answer needs no judgement.

An agent asked to invent a thousand traffic-law questions invents the law along
with them, and grading its output means grading its hallucinations. Deriving the
question from a sampled provision inverts that: the text supplies the offence,
the sampled path supplies the ground truth, and scoring becomes a comparison
rather than an opinion.

The filters are deliberately harsh. A malformed question -- a mid-sentence
fragment, or a procedural clause bent into "bị phạt bao nhiêu" -- has no right
answer, so the engine cannot win it, and every one of them understates the
score. Rejecting four fifths of the corpus is the cheaper error.

Each family of templates is labelled, so the report says which *kind* of
question fails rather than only how many.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
from pathlib import Path
from typing import Any

from rag_eval.legal.db.connection import close_db_pool, get_db_pool
from rag_eval.legal.ingestion.facets import (
    BICYCLE,
    CAR,
    DRAFT_ANIMAL,
    MOTORCYCLE,
    PEDESTRIAN,
    WORKS_VEHICLE,
    classify_heading,
)

_HEADING = re.compile(r"\[Điều\s+([^\]:]*):\s*([^\]]+)\]")
_LEAF_PREFIX = re.compile(r"^\s*(Điểm|Khoản)\s+[^\s)]{1,4}[).]\s*")

# A leaf is an offence only if the clause above it opens a penalty bracket.
# Without this the generator priced definitions and time limits as if they
# were violations: "thời hiệu xử phạt là 01 năm bị phạt bao nhiêu?".
_PENALTY_PARENT = re.compile(r"\[Khoản [^\]:]*:\s*Phạt tiền từ")

# The cross-reference tail names other provisions, not this one -- keeping it
# points the question at the article it excludes.
_XREF_TAIL = re.compile(
    r"\s*,?\s*(trừ|ngoại trừ)\s+(các\s+)?(hành vi|trường hợp|quy định).*$",
    re.IGNORECASE | re.DOTALL,
)
_TRAILING_REF = re.compile(
    r"\s*(quy định tại|theo quy định tại|được quy định tại)\s+"
    r"(điểm|khoản|điều|Phụ lục).*$",
    re.IGNORECASE | re.DOTALL,
)

# Text that refers outward, delegates, or names an office describes machinery
# rather than conduct, and cannot carry a question on its own.
_JUNK = re.compile(
    r"(@|Email|Fax|Điện thoại|Phạt cảnh cáo|Sửa đổi|Bổ sung|Bãi bỏ|Thay thế"
    r"|Điều này|Quy chuẩn này|Nghị định này|Thông tư này|Luật này|khoản này"
    r"|quy định chi tiết|Bộ trưởng|Chủ tịch|Thủ trưởng|Giám đốc|Cục trưởng"
    r"|thẩm quyền|trách nhiệm|thời hiệu|hiệu lực thi hành|Chính phủ"
    r"|Ủy ban nhân dân|cơ quan|như sau)",
    re.IGNORECASE,
)

# A fragment lifted from the middle of an enumeration starts mid-thought.
_FRAGMENT_START = re.compile(
    r"^(và|hoặc|thì|nhưng|trong đó|đối với|của|các|nếu|khi|sinh|viên)\b",
    re.IGNORECASE,
)

# How a person names the class the statute spells out in full.
_SUBJECT: dict[str, str] = {
    CAR: "ô tô",
    MOTORCYCLE: "xe máy",
    WORKS_VEHICLE: "xe máy chuyên dùng",
    BICYCLE: "xe đạp",
    PEDESTRIAN: "người đi bộ",
    DRAFT_ANIMAL: "người dắt súc vật",
}

_MIN_WORDS = 5
_MAX_WORDS = 24


def _clean_offence(verbatim: str) -> str | None:
    """Reduces a provision to the offence it prices, or rejects it as unusable."""
    text = " ".join(verbatim.split())
    stripped = _LEAF_PREFIX.sub("", text)
    # An enumeration item opens with a capital; a continuation does not.
    if not stripped[:1].isupper():
        return None
    body = stripped.split(";")[0]
    body = _XREF_TAIL.sub("", body)
    body = _TRAILING_REF.sub("", body)
    body = body.strip(" .;,:")
    if _JUNK.search(body) or _FRAGMENT_START.search(body):
        return None
    if "(" in body or ")" in body:
        return None
    words = body.split()
    if not (_MIN_WORDS <= len(words) <= _MAX_WORDS):
        return None
    # A clause opening with the sanction states the bracket, not the act.
    if body.lower().startswith(("phạt ", "tước ", "tịch thu", "trừ điểm", "buộc ")):
        return None
    return body[0].lower() + body[1:]


def _subject_of(heading: str) -> str | None:
    classes = classify_heading(heading)
    # Several classes means a question naming one of them would be answered
    # just as well by the parallel article, so the row is not a fair test.
    if len(classes) != 1:
        return None
    return _SUBJECT.get(classes[0])


_PENALTY_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("gen_penalty", "{subject} {offence} bị phạt bao nhiêu tiền?"),
    (
        "gen_penalty_alt",
        "mức phạt đối với hành vi {offence} của {subject} là bao nhiêu?",
    ),
    ("gen_keyword", "{subject} {offence}"),
    (
        "gen_verbose",
        (
            "Cho em hỏi {subject} mà {offence} thì theo quy định hiện hành"
            " bị xử lý như thế nào ạ?"
        ),
    ),
    ("gen_penalty_short", "phạt {subject} {offence}"),
    ("gen_question_word", "{subject} {offence} thì bị làm sao?"),
)

_UNCLASSED_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("gen_penalty_noclass", "hành vi {offence} bị xử phạt thế nào?"),
    ("gen_keyword_noclass", "{offence}"),
    ("gen_penalty_noclass_alt", "mức xử phạt cho hành vi {offence} là bao nhiêu?"),
)

# Built from the article heading rather than a clause body: a heading is a
# complete noun phrase by construction, so these are always well formed.
_RULE_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("gen_rule", "quy định về {heading}?"),
    ("gen_rule_alt", "luật quy định thế nào về {heading}?"),
    ("gen_rule_where", "{heading} nằm ở điều nào?"),
)

_DEFINITION_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("gen_definition", "{term} là gì?"),
    ("gen_definition_alt", "thế nào là {term}?"),
)

_DEFINITION_LEAD = re.compile(
    r"^\s*(?:Điểm|Khoản)?\s*[^\s)]{0,4}[).]?\s*([^là]{3,60}?)\s+là\s+", re.IGNORECASE
)

SQL = """
SELECT c.path::text AS path, c.verbatim_text, c.contextualized_text, d.doc_code
FROM chunks c JOIN documents d ON d.id = c.document_id
WHERE ($1::text IS NULL AND d.expiration_date IS NULL) OR d.doc_code = $1
"""


def _penalty_rows(
    record: dict[str, Any], heading: str, rng: random.Random
) -> list[dict[str, Any]]:
    if not _PENALTY_PARENT.search(record["contextualized_text"]):
        return []
    offence = _clean_offence(record["verbatim_text"])
    if offence is None:
        return []
    base = {"source_path": record["path"], "doc_code": record["doc_code"]}
    subject = _subject_of(heading)
    if subject:
        pool = _PENALTY_TEMPLATES
        fields = {"subject": subject, "offence": offence}
    else:
        pool = _UNCLASSED_TEMPLATES
        fields = {"offence": offence}
    return [
        {"query": template.format(**fields), "style": style, **base}
        for style, template in rng.sample(pool, k=min(4, len(pool)))
    ]


def _definition_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    match = _DEFINITION_LEAD.match(" ".join(record["verbatim_text"].split()))
    if match is None:
        return []
    term = match.group(1).strip(" .;,:")
    if not (1 <= len(term.split()) <= 8) or _JUNK.search(term):
        return []
    base = {"source_path": record["path"], "doc_code": record["doc_code"]}
    return [
        {"query": template.format(term=term.lower()), "style": style, **base}
        for style, template in _DEFINITION_TEMPLATES
    ]


def _heading_is_usable(heading: str) -> bool:
    lowered = heading.lower()
    if _JUNK.search(heading):
        return False
    if lowered.startswith(("xử phạt", "sửa đổi", "bổ sung", "bãi bỏ")):
        return False
    return 2 <= len(heading.split()) <= 18


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--rules-per-article", type=int, default=3)
    parser.add_argument(
        "--doc-code",
        default=None,
        help="Draw only from this document, superseded ones included.",
    )
    parser.add_argument(
        "--violation-date",
        default=None,
        help="Stamp every row with this offence date, to test the temporal filter.",
    )
    parser.add_argument("--style-prefix", default="")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        records = [dict(r) for r in await conn.fetch(SQL, args.doc_code)]
    await close_db_pool()

    rng.shuffle(records)
    generated: list[dict[str, Any]] = []
    seen: set[str] = set()
    articles_done: set[str] = set()

    for record in records:
        match = _HEADING.search(record["contextualized_text"])
        if match is None:
            continue
        heading = " ".join(match.group(2).split())
        rows: list[dict[str, Any]] = []

        if "giải thích từ ngữ" in heading.lower():
            rows = _definition_rows(record)
        else:
            rows = _penalty_rows(record, heading, rng)
            # One question per article from its heading, not one per chunk.
            article = record["path"].rsplit(".c_", 1)[0]
            if _heading_is_usable(heading) and article not in articles_done:
                articles_done.add(article)
                rows += [
                    {
                        "query": template.format(heading=heading.lower()),
                        "style": style,
                        "source_path": record["path"],
                        "doc_code": record["doc_code"],
                    }
                    for style, template in rng.sample(
                        _RULE_TEMPLATES, k=args.rules_per_article
                    )
                ]

        for row in rows:
            if args.violation_date:
                row["violation_date"] = args.violation_date
            if args.style_prefix:
                row["style"] = args.style_prefix + row["style"]
            key = row["query"].casefold()
            if key in seen:
                continue
            seen.add(key)
            generated.append(row)

    Path(args.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in generated) + "\n",
        encoding="utf-8",
    )
    by_style: dict[str, int] = {}
    for row in generated:
        by_style[row["style"]] = by_style.get(row["style"], 0) + 1
    print(f"{len(records)} chunk -> {len(generated)} câu hỏi -> {args.out}")
    for style, count in sorted(by_style.items(), key=lambda kv: -kv[1]):
        print(f"  {style:26s} {count:5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
