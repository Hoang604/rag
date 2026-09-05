"""Vehicle-class facet for statutory penalty provisions.

Nghị định 168/2024 repeats the same offence across parallel articles, one per
vehicle class: running a red light is Điều 6 for a car, Điều 7 for a motorcycle,
Điều 8 for a works vehicle. The clause bodies are near-identical and the article
headings differ by a few syllables inside 150 shared characters, so cosine
distance cannot separate them -- 10 of 10 Hit@1 misses landed on the right
document and the wrong vehicle. The class is categorical, so it is resolved as a
facet rather than left to the embedding.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

CAR: Final = "car"
MOTORCYCLE: Final = "motorcycle"
WORKS_VEHICLE: Final = "works_vehicle"
BICYCLE: Final = "bicycle"
PEDESTRIAN: Final = "pedestrian"
DRAFT_ANIMAL: Final = "draft_animal"

_ARTICLE_SEGMENT = re.compile(r"\[Điều\s+[^\]:]*:\s*([^\]]+)\]")

# Ordered: the first pattern that matches wins. "xe máy chuyên dùng" must be
# tested before "xe máy", and "xe đạp máy" before both, or every works vehicle
# and every e-bike is filed as a motorcycle.
_HEADING_RULES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (PEDESTRIAN, re.compile(r"người đi bộ")),
    (DRAFT_ANIMAL, re.compile(r"(vật nuôi|súc vật)")),
    (WORKS_VEHICLE, re.compile(r"(xe máy chuyên dùng|máy kéo)")),
    (BICYCLE, re.compile(r"(xe đạp|xe thô sơ)")),
    (MOTORCYCLE, re.compile(r"(xe mô tô|xe gắn máy)")),
    (CAR, re.compile(r"(xe ô tô|ô tô|xe chở người bốn bánh|xe chở hàng bốn bánh)")),
)

# The query side has to accept what people actually type. "Xe máy" is the
# everyday word for a motorcycle; the statute never uses it that way.
_QUERY_RULES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (PEDESTRIAN, re.compile(r"người đi bộ|đi bộ qua đường")),
    (DRAFT_ANIMAL, re.compile(r"vật nuôi|súc vật|xe bò|xe ngựa")),
    (WORKS_VEHICLE, re.compile(r"xe máy chuyên dùng|máy kéo|xe chuyên dùng")),
    (BICYCLE, re.compile(r"xe đạp|xe thô sơ|xích lô")),
    (
        MOTORCYCLE,
        re.compile(r"xe máy|mô tô|xe gắn máy|xe côn tay|xe tay ga|honda|xe hai bánh"),
    ),
    (
        CAR,
        re.compile(
            r"ô tô|oto|xe hơi|xe con|xe tải|xe khách|xe buýt|xe container"
            r"|xe đầu kéo|xe bán tải|xe cứu thương|xe cứu hộ|xe bốn bánh"
        ),
    ),
)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def classify_heading(heading: str) -> str | None:
    """Returns the vehicle class an article heading governs, if it names one."""
    folded = _fold(heading)
    for label, pattern in _HEADING_RULES:
        if pattern.search(folded):
            return label
    return None


def classify_query(query: str) -> str | None:
    """Returns the vehicle class a natural-language question asks about."""
    folded = _fold(query)
    for label, pattern in _QUERY_RULES:
        if pattern.search(folded):
            return label
    return None


def classify_context(contextualized_text: str | None) -> str | None:
    """Reads the vehicle class off the [Điều N: ...] segment of a CPHC prefix.

    Only the article heading is consulted. A clause body mentioning "xe ô tô"
    in passing does not move the provision it belongs to into another class.
    """
    if not contextualized_text:
        return None
    match = _ARTICLE_SEGMENT.search(contextualized_text)
    if match is None:
        return None
    return classify_heading(match.group(1))


PENALTY: Final = "penalty"
DEFINITION: Final = "definition"

# The held-out set exposed a second confusion, orthogonal to vehicle class:
# "xe máy không nhường đường cho người đi bộ bị phạt bao nhiêu" returned Luật
# TTATGTĐB, which states the duty, instead of NĐ 168, which prices breaking it.
# Both provisions are about the same act; only one answers "how much".
_ROLE_MARKERS: Final[tuple[tuple[str, str], ...]] = (
    (DEFINITION, "giải thích từ ngữ"),
    (PENALTY, "phạt tiền từ"),
)

_INTENT_RULES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        DEFINITION,
        re.compile(
            r"là gì|được hiểu là|định nghĩa|nghĩa là gì|thế nào là|được gọi là"
        ),
    ),
    (
        PENALTY,
        re.compile(
            r"phạt bao nhiêu|bị phạt|xử phạt|mức phạt|phạt tiền|phạt thế nào"
            r"|phạt ra sao|bị xử lý|trừ (?:bao nhiêu )?điểm"
        ),
    ),
)


def classify_role(contextualized_text: str | None) -> str | None:
    """Returns what kind of provision a chunk is: a priced offence or a term."""
    if not contextualized_text:
        return None
    folded = _fold(contextualized_text)
    for label, marker in _ROLE_MARKERS:
        if marker in folded:
            return label
    return None


def classify_intent(query: str) -> str | None:
    """Returns whether a question asks for a penalty amount or for a meaning."""
    folded = _fold(query)
    for label, pattern in _INTENT_RULES:
        if pattern.search(folded):
            return label
    return None
