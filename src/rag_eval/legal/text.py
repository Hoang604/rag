"""Diacritic folding, shared by every component that matches Vietnamese words.

Most people type Vietnamese without tone marks: "xe may vuot den do". The text
search configuration already folds diacritics, so the sparse ranker never
noticed -- but the vehicle classifier, the intent classifier and the synonym
lexicon all matched accented patterns against raw input, so all three returned
nothing and switched off silently. Measured over 1,005 queries, dropping
diacritics cost 58 points of Hit@1 (86.7% to 28.9%).
"""

from __future__ import annotations

import unicodedata

_D_LOWER = "đ"
_D_UPPER = "Đ"


def fold_diacritics(text: str) -> str:
    """Returns text with tone marks removed and đ mapped to d. Case is kept.

    Case must survive because this also folds regular-expression sources, and
    case folding a pattern turns `\\W` into `\\w` -- inverting the character
    class and, in this corpus, filing every motorcycle article as a car.
    """
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.replace(_D_LOWER, "d").replace(_D_UPPER, "D")


def fold_for_match(text: str) -> str:
    """Folds text for comparison against a folded pattern: diacritics and case."""
    return fold_diacritics(text).casefold()


def is_unaccented(text: str) -> bool:
    """Reports whether a Vietnamese query was typed without any tone marks.

    Used to discount the dense ranker: the corpus is embedded from accented
    text, so an unaccented query lands far from its answer in vector space
    while the diacritic-folding text index still finds it exactly.
    """
    stripped = text.strip()
    if len(stripped.split()) < 2:
        return False
    return fold_diacritics(stripped) == stripped
