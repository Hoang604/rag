"""The numbered outline of a body without articles: which lines open an item, and where each item nests.

Appendices, attached texts and article-less bodies (a QCVN without Điều, a Chỉ thị)
structure themselves with markers of three kinds, ranked as drafting ranks them: a
capital letter ("A.") above a Roman numeral ("II.") above a decimal ("2.3.1."), as in
NĐ 30/2020's I. / 1. / a). A bare marker is weak evidence on its own ("1." also numbers
form fields and quoted lists), so it opens an item only where it continues the outline:
the first marker of a level not yet open ("A", "I", or a decimal ending in 1 under the
open decimals), or the marker right after the open one of its kind. Numbering has no
gaps -- a repealed unit keeps its number with "(được bãi bỏ)", an inserted one takes a
letter ("7a." after "7.") -- so a gap means the line is not this outline's item, and it
stays text of the open item. A list starts at 1, so a "1." that opens no level starts a
list inside the open item, and the numbers continuing it belong to that item. An item
numbered under the appendix's own letter ("A.1.2" in Phụ lục A) states its place
outright and nests by its number alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rag_eval.legal.ingestion.grammar import (
    OUTLINE_DECIMAL_PATTERN,
    OUTLINE_LETTER_PATTERN,
    OUTLINE_ROMAN_PATTERN,
    OWN_LETTER_ITEM_PATTERN,
)

MarkerKind = Literal["letter", "roman", "decimal"]

_RANK: dict[MarkerKind, int] = {"letter": 0, "roman": 1, "decimal": 2}
_FIRST: dict[MarkerKind, str] = {"letter": "A", "roman": "I", "decimal": "1"}
# Capital enumeration letters run either in Latin order or in Vietnamese order (no F, J, W, Z; Đ after D).
_LETTER_ORDERS = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "ABCDĐEGHIKLMNOPQRSTUVXY")
_INSERTED_NUMBER = re.compile(r"^(\d+)([a-zđ]?)$")
_ROMAN_DIGITS = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


@dataclass(frozen=True)
class OutlineItem:
    """A line that opens an outline item."""

    key: tuple[str, ...]  # the markers from the outermost item down to this one; a parent's key is a prefix
    label: str  # the marker as cited: "A.1.2", "II", "2.3.1"
    content: str  # the line after its marker


def _roman(value: int) -> str:
    out: list[str] = []
    for number, digits in _ROMAN_DIGITS:
        while value >= number:
            out.append(digits)
            value -= number
    return "".join(out)


def _roman_value(numeral: str) -> int | None:
    """The value of a canonically written Roman numeral below 40, None for any other string."""
    for value in range(1, 40):
        if _roman(value) == numeral:
            return value
    return None


def _next_letter(letter: str, current: str) -> bool:
    """True when `letter` comes right after `current` in Latin or Vietnamese alphabetical order (either case)."""
    return any(
        letter in order and current in order and order.index(letter) == order.index(current) + 1
        for order in (*_LETTER_ORDERS, *(o.lower() for o in _LETTER_ORDERS))
    )


def follows_number(number: str, current: str) -> bool:
    """True when an enumeration number comes right after `current`: "7" -> "7a" or "8", "7a" -> "7b" or "8"."""
    new, old = _INSERTED_NUMBER.match(number), _INSERTED_NUMBER.match(current)
    if new is None or old is None:
        return False
    if new.group(1) == old.group(1):
        return bool(new.group(2)) and (_next_letter(new.group(2), old.group(2)) if old.group(2) else new.group(2) == "a")
    return int(new.group(1)) == int(old.group(1)) + 1 and not new.group(2)


def _follows(kind: MarkerKind, marker: str, current: str) -> bool:
    """True when a letter or Roman `marker` comes right after `current`."""
    if kind == "letter":
        return _next_letter(marker, current)
    new, old = _roman_value(marker), _roman_value(current)
    return new is not None and old is not None and new == old + 1


class Outline:
    """Tracks the open path of one outline and accepts the lines that continue it."""

    def __init__(self, own_letter: str | None) -> None:
        """own_letter: the appendix's letter ("A" for Phụ lục A); None for numbered/unnumbered appendices, attachments and bodies."""
        self._letter = own_letter
        self._path: list[tuple[MarkerKind, str]] = []
        # The last number of a bare "1., 2., …" list running inside the open item; None when none runs.
        self._inner: str | None = None

    def accept(self, line: str) -> OutlineItem | None:
        """The item `line` opens, or None when it opens none; an accepted line becomes the open item."""
        if self._letter is not None:
            numbered = OWN_LETTER_ITEM_PATTERN.match(line)
            if numbered and numbered.group(1) == self._letter:
                components = numbered.group(2).split(".")
                return self._open("decimal", components, f"{self._letter}.{numbered.group(2)}", numbered.group(3))
        decimal = OUTLINE_DECIMAL_PATTERN.match(line)
        if decimal:
            components = decimal.group(1).rstrip(".").split(".")
            if self._continues_inner(components):
                return None
            if self._continues_decimal(components):
                return self._open("decimal", components, ".".join(components), decimal.group(2))
            # A list starts at 1: a "1." that opens no outline level starts a list inside the open item.
            self._inner = components[0] if components == [_FIRST["decimal"]] else None
            return None
        candidates: list[tuple[MarkerKind, str, str]] = []
        roman = OUTLINE_ROMAN_PATTERN.match(line)
        if roman and _roman_value(roman.group(1)) is not None:
            candidates.append(("roman", roman.group(1), roman.group(2)))
        letter = OUTLINE_LETTER_PATTERN.match(line)
        if letter:
            candidates.append(("letter", letter.group(1), letter.group(2)))
        # "I." after "H." reads as the next letter; under "A." it starts a Roman run.
        successors = [c for c in candidates if self._after_open(c[0], c[1])]
        starts = [c for c in candidates if self._open_at(c[0]) is None and c[1] == _FIRST[c[0]]]
        for kind, marker, content in successors or starts:
            return self._open(kind, [marker], marker, content)
        return None

    def _open_at(self, kind: MarkerKind) -> str | None:
        """The marker of the open item of `kind`, None when no item of that kind is open."""
        return next((marker for k, marker in self._path if k == kind), None)

    def _after_open(self, kind: MarkerKind, marker: str) -> bool:
        current = self._open_at(kind)
        return current is not None and _follows(kind, marker, current)

    def _continues_inner(self, components: list[str]) -> bool:
        """True when a bare number continues the list running inside the open item; any other marker ends that list."""
        if self._inner is not None and len(components) == 1 and follows_number(components[0], self._inner):
            self._inner = components[0]
            return True
        self._inner = None
        return False

    def _continues_decimal(self, components: list[str]) -> bool:
        open_numbers = [marker for kind, marker in self._path if kind == "decimal"]
        depth = len(components)
        if depth > len(open_numbers) + 1 or components[:-1] != open_numbers[: depth - 1]:
            return False
        if depth == len(open_numbers) + 1:
            return components[-1] == _FIRST["decimal"]
        return follows_number(components[-1], open_numbers[depth - 1])

    def _open(self, kind: MarkerKind, markers: list[str], label: str, content: str) -> OutlineItem:
        self._inner = None
        self._path = [entry for entry in self._path if _RANK[entry[0]] < _RANK[kind]]
        self._path.extend((kind, marker) for marker in markers)
        return OutlineItem(key=tuple(marker for _, marker in self._path), label=label, content=content.strip())
