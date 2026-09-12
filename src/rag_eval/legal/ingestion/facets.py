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
from typing import Final

from rag_eval.legal.text import fold_for_match
from rag_eval.legal.vocabulary import vocabulary

CAR: Final = "car"
MOTORCYCLE: Final = "motorcycle"
WORKS_VEHICLE: Final = "works_vehicle"
BICYCLE: Final = "bicycle"
PEDESTRIAN: Final = "pedestrian"
DRAFT_ANIMAL: Final = "draft_animal"

_ARTICLE_SEGMENT = re.compile(r"\[Điều\s+[^\]:]*:\s*([^\]]+)\]")

# A heading may name several classes at once -- Điều 21 governs "xe ô tô tải,
# Patterns and input are both folded, so a rule written "xe máy chuyên dùng"
_fold = fold_for_match


# A heading that governs every vehicle must not be filed under one of them.


def classify_heading(heading: str) -> list[str]:
    """Returns every vehicle class an article heading governs.

    Empty when the heading governs all of them, which is not the same as
    failing to recognise it: both mean "do not apply the vehicle facet here",
    and that is exactly the right treatment.
    """
    folded = _fold(heading)
    if vocabulary().general_heading.search(folded):
        return []
    return [
        label
        for label, pattern in vocabulary().vehicle_heading
        if pattern.search(folded)
    ]


# A penalty falls on whoever operates the vehicle, so the class is the subject's,
_VICTIM_ONLY: Final = frozenset({PEDESTRIAN, DRAFT_ANIMAL})


def classify_query(query: str) -> str | None:
    """Returns the vehicle class whose operator a question asks about."""
    folded = _fold(query)
    matches = [
        label for label, pattern in vocabulary().vehicle_query if pattern.search(folded)
    ]
    if not matches:
        return None
    driven = [label for label in matches if label not in _VICTIM_ONLY]
    return driven[0] if driven else matches[0]


def classify_context(contextualized_text: str | None) -> list[str]:
    """Reads the vehicle class off the [Điều N: ...] segment of a CPHC prefix.

    Only the article heading is consulted. A clause body mentioning "xe ô tô"
    in passing does not move the provision it belongs to into another class.
    """
    if not contextualized_text:
        return []
    match = _ARTICLE_SEGMENT.search(contextualized_text)
    if match is None:
        return []
    return classify_heading(match.group(1))


PENALTY: Final = "penalty"
DEFINITION: Final = "definition"


# The held-out set exposed a second confusion, orthogonal to vehicle class:
def classify_role(contextualized_text: str | None) -> str | None:
    """Returns what kind of provision a chunk is: a priced offence or a term."""
    if not contextualized_text:
        return None
    folded = _fold(contextualized_text)
    for label, marker in vocabulary().role_markers:
        if marker in folded:
            return label
    return None


def classify_intent(query: str) -> str | None:
    """Returns whether a question asks for a penalty amount or for a meaning."""
    folded = _fold(query)
    for label, pattern in vocabulary().intent:
        if pattern.search(folded):
            return label
    return None
