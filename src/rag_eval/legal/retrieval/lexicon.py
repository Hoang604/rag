"""Colloquial-to-statutory query expansion for the sparse half of retrieval.

Nobody asks "không chấp hành hiệu lệnh của đèn tín hiệu giao thông" -- they ask
"vượt đèn đỏ". The two share no lexeme, so the sparse ranker scored the correct
provision 821st while dense had it 12th. Expansion appends the statutory wording
to the text the tsquery is built from; the dense vector is still computed from
what the user actually wrote, so the two halves keep their independence and a
wrong expansion cannot poison both.

Every replacement below is a phrase verified to occur in the corpus.
"""

from __future__ import annotations

import re
from typing import Final

from rag_eval.legal.text import fold_for_match
from rag_eval.legal.vocabulary import vocabulary

# Ordered longest-context-first so "vượt đèn đỏ" is not consumed by "đèn đỏ".
# Statutes write small counts zero-padded -- "chở theo từ 03 người" -- and the
_BARE_DIGIT = re.compile(r"(?<![\d,.])([1-9])(?![\d,.])")

MAX_EXPANSIONS: Final[int] = 4


# Patterns and input are both folded: "vuot den do" typed without a Vietnamese
_fold = fold_for_match


def _expansions(query: str) -> list[str]:
    """Returns the statutory phrasings a question maps onto."""
    folded = _fold(query)
    found: list[str] = []
    for pattern, expansion in vocabulary().synonyms:
        if len(found) >= MAX_EXPANSIONS:
            break
        if pattern.search(folded) and _fold(expansion) not in folded:
            found.append(expansion)
    return found


def expand_query(query: str) -> str:
    """Returns the query with statutory phrasings appended for sparse matching.

    The original text is kept in front. At most four expansions are appended,
    because each one adds syllable pairs that dilute ts_rank across the whole
    candidate pool.
    """
    additions = _expansions(query)
    padded = _BARE_DIGIT.sub(lambda m: f"0{m.group(1)}", query)
    if padded != query:
        additions.append(padded)
    if not additions:
        return query
    return " ".join([query, *additions])


def phrase_variants(query: str) -> list[str]:
    """Returns the phrases worth scoring a literal match against.

    A phrase query built from a whole natural-language question matches nothing
    -- measured: zero chunks out of 7,112, for every smoke query -- because no
    statute contains "... bị phạt bao nhiêu tiền?". The phrases that do occur
    are the statutory ones the lexicon maps onto, so those are what the bonus is
    evaluated on.
    """
    return [query, *_expansions(query)]
