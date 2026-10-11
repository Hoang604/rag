"""The single cleaner: labelled blocks from any extractor become one canonical text.

Canonical text holds only normative content and tables: one paragraph or table row per
line, NFC Unicode, no invisible characters, no table of contents. Footnotes, page
furniture and corrupt text layers are dropped by their label; symbol fonts were already
decoded by the extractor, which knows each run's font. Everything downstream reads this
text and nothing else.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from rag_eval.legal.ingestion.extract import Block

_INVISIBLE: dict[int, None] = dict.fromkeys(
    [0xFEFF, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0x00AD, 0x180E, 0xFFFC]
    + list(range(0x202A, 0x202F))
    + list(range(0x2061, 0x2065))
)

_KEPT_KINDS = ("text", "table")

_TOC_HEADING = ("mục", "lục")
# A table-of-contents entry: a division heading with its number, or any line closed by leader dots and a page number.
_HEADING_SHAPED = re.compile(
    r"^(?:Phần|PHẦN|Chương|CHƯƠNG|Tiểu mục|TIỂU MỤC|Mục|MỤC|Điều|ĐIỀU|Phụ lục|PHỤ LỤC)\s+\S"
)
_LEADER = re.compile(r"(?:\.{3,}|…+)[.…\s]*\d*\s*$")


def _heading_key(line: str) -> tuple[str, ...]:
    """A line compared as a heading: no leader or page number, case and punctuation ignored."""
    return tuple(re.findall(r"\w+", _LEADER.sub("", line).casefold()))


def _is_toc_entry(line: str) -> bool:
    return bool(_HEADING_SHAPED.match(line) or _LEADER.search(line))


def _without_toc(lines: list[str]) -> list[str]:
    """Drops each flattened table of contents: a "MỤC LỤC" line and the run of entries after it.

    The run is the maximal sequence of heading-shaped lines; it ends before the first line
    whose heading restates an earlier entry (the body has begun), so it never reaches body
    text. When no entry follows, nothing is dropped, not even the "MỤC LỤC" line.
    """
    for start, line in enumerate(lines):
        if _heading_key(line) != _TOC_HEADING:
            continue
        seen: list[tuple[str, ...]] = []
        end = start + 1
        while end < len(lines) and _is_toc_entry(lines[end]):
            key = _heading_key(lines[end])
            if any(key == earlier[: len(key)] for earlier in seen):
                break
            seen.append(key)
            end += 1
        if seen:
            return lines[:start] + _without_toc(lines[end:])
    return lines


def normalize_line(line: str) -> str:
    text = unicodedata.normalize("NFC", line).translate(_INVISIBLE)
    return re.sub(r"\s+", " ", text).strip()


def canonical_text(blocks: Sequence[Block]) -> str:
    lines = [
        line
        for block in blocks
        if block.kind in _KEPT_KINDS
        for line in (normalize_line(raw) for raw in block.text.split("\n"))
        if line
    ]
    return "\n".join(_without_toc(lines)) + "\n"
