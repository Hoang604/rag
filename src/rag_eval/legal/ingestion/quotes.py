"""Where quoted text lies in one text: the single quotation model of the ingestion flow.

An amending document carries another document's wording between quotation marks, so
nothing inside a quote is structure or a citation of the quoting document. Marks are
paired over the whole text: “…”, ‘…’, «…» and straight "…". A straight quote opens
after the start of a line, whitespace, "(" or ":" and closes anywhere else. Double marks
are often mixed by typing ("…” or “…"), so a double closer with no opener of its own
kind open closes the innermost open double quote. An opener
that finds no closer is closed at the end of its own line and reported, so one typo
cannot swallow the rest of the document.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

_PAIRS = {"“": "”", "‘": "’", "«": "»"}
_CLOSERS = frozenset(_PAIRS.values())
_STRAIGHT = '"'
_STRAIGHT_OPENS_AFTER = frozenset("(:")
_DOUBLE_CLOSERS = frozenset({"”", _STRAIGHT})


@dataclass(frozen=True)
class QuoteSpans:
    """Character ranges [start, end) of quoted text in one text; `unmatched` holds openers closed at their line end."""

    spans: tuple[tuple[int, int], ...]  # sorted, non-overlapping; nested quotes lie inside their outer span
    unmatched: tuple[int, ...]  # offsets of openers that had no closer

    def contains(self, offset: int) -> bool:
        """True when the character at `offset` lies inside quoted text."""
        index = bisect.bisect_right(self.spans, offset, key=lambda span: span[0]) - 1
        return index >= 0 and offset < self.spans[index][1]


def _opens_straight(text: str, offset: int) -> bool:
    return offset == 0 or text[offset - 1].isspace() or text[offset - 1] in _STRAIGHT_OPENS_AFTER


def _scan(text: str, start: int) -> tuple[list[tuple[int, int]], int | None]:
    """Outermost spans paired from `start` on, and the offset of the outermost opener left open (None when all closed)."""
    spans: list[tuple[int, int]] = []
    stack: list[tuple[str, int]] = []  # (expected closer, opener offset)
    for offset in range(start, len(text)):
        char = text[offset]
        if char in _PAIRS:
            stack.append((_PAIRS[char], offset))
            continue
        if char != _STRAIGHT and char not in _CLOSERS:
            continue
        depth = next((d for d in range(len(stack) - 1, -1, -1) if stack[d][0] == char), None)
        if depth is None:
            # A straight quote with no straight opener on the stack opens one where an opener can stand.
            if char == _STRAIGHT and _opens_straight(text, offset):
                stack.append((_STRAIGHT, offset))
                continue
            # A double closer closes the innermost open double quote of the other kind; any other stray closer is ignored.
            if char in _DOUBLE_CLOSERS:
                depth = next((d for d in range(len(stack) - 1, -1, -1) if stack[d][0] in _DOUBLE_CLOSERS), None)
            if depth is None:
                continue
        opener = stack[depth][1]
        del stack[depth:]
        if not stack:
            spans.append((opener, offset + 1))
    return spans, (stack[0][1] if stack else None)


def quote_spans(text: str) -> QuoteSpans:
    """Pairs quotation marks over the whole text (“” ‘’ «» and straight ")."""
    spans: list[tuple[int, int]] = []
    unmatched: list[int] = []
    start = 0
    while True:
        found, open_at = _scan(text, start)
        if open_at is None:
            spans.extend(found)
            break
        spans.extend(found)
        line_end = text.find("\n", open_at)
        end = len(text) if line_end == -1 else line_end
        spans.append((open_at, end))
        unmatched.append(open_at)
        start = end
    return QuoteSpans(spans=tuple(spans), unmatched=tuple(unmatched))
