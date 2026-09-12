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

# Two clause-numbering conventions CLAUSE_PATTERN misses, told apart by the
QCVN_CLAUSE_PATTERN = re.compile(r"^(\d{1,3})\.(\d{1,3})\.\s+(.*)$")

# Consolidated documents glue footnote markers to the division number:
FOOTNOTE_CLAUSE_PATTERN = re.compile(r"^(\d{1,3})\.(\d{1,3})\s+(\S.*)$")
FOOTNOTE_POINT_PATTERN = re.compile(r"^([a-zđ])\)(\d{1,3})\s+(\S.*)$", re.IGNORECASE)

# A technical standard's appendix is a flat list of self-contained items
APPENDIX_ITEM_PATTERN = re.compile(r"^([A-Z])\.?(\d+(?:\.\d+)*[a-z]?)\.?\s+(\S.*)$")


# A PDF column break before "Điều 24 của Luật này." otherwise creates a
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
