"""Lightweight statutory structural token patterns for AST hierarchy construction.

Provides clean regular expression tokens for detecting structural legislative divisions
(Chương, Mục, Điều, Khoản, Điểm, Phụ lục) without hardcoded penalty or domain assumptions.
"""

from __future__ import annotations

import re

# Structural statutory division regexes (Clean structural tokenizers)
CHAPTER_PATTERN = re.compile(
    r"^(?:CHƯƠNG|Chương)\s+([IVXLCDM\d]+)(?:[\.\s:–-]\s*(.*))?$",
    re.IGNORECASE,
)

SECTION_PATTERN = re.compile(
    r"^(?:MỤC|Mục)\s+(\d+)(?:[\.\s:–-]\s*(.*))?$",
    re.IGNORECASE,
)

ARTICLE_PATTERN = re.compile(
    r"^(?:ĐIỀU|Điều)\s+(\d+[a-z]?)(?:[\.\s:–-]\s*(.*))?$",
    re.IGNORECASE,
)

CLAUSE_PATTERN = re.compile(
    r"^(\d+)\.\s+(.*)$",
)

POINT_PATTERN = re.compile(
    r"^([a-zđ])\)\s+(.*)$",
    re.IGNORECASE,
)

APPENDIX_PATTERN = re.compile(
    r"^(?:PHỤ LỤC|Phụ lục)\s+([IVXLCDM\d]+|[A-Z])(?:[\.\s:–-]\s*(.*))?$",
    re.IGNORECASE,
)

# A wrapped citation can begin a line with a division keyword. The patterns
# above accept whitespace as the separator between the number and the title, so
# a PDF column break landing before "Điều 24 của Luật này." matches ARTICLE with
# "của Luật này." as its title. Three such lines in Luật Đường bộ created a
# second Điều 24, 32 and 45, and each duplicate swallowed the real articles'
# clauses -- five distinct provisions ended up sharing an ltree path.
#
# A genuine Vietnamese statutory title is capitalised; a citation continues in
# lower case. An explicit ".", ":" or dash after the number settles it either
# way, so the check only applies where the separator is bare whitespace.
_DIVISION_HEAD = re.compile(
    r"^(?:ĐIỀU|Điều|CHƯƠNG|Chương|MỤC|Mục|PHỤ LỤC|Phụ lục)\s+"
    r"(?:[IVXLCDM\d]+[a-z]?)(?P<tail>.*)$"
)


def looks_like_citation_fragment(line: str) -> bool:
    """True when a division keyword opens a wrapped citation, not a heading."""
    match = _DIVISION_HEAD.match(line.strip())
    if match is None:
        return False
    tail = match.group("tail")
    if tail[:1] in (".", ":", "–", "-"):
        return False
    rest = tail.strip()
    return bool(rest) and rest[:1].islower()


SIGN_CODE_PATTERN = re.compile(
    r"\b([PWIROMS]\.[\d]+[a-z]?|[M]\.[\d]+\.[\d]+)\b",
    re.IGNORECASE,
)
