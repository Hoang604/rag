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

# Two drafting conventions number their divisions in ways CLAUSE_PATTERN misses,
# and both were silently absorbing statute into the enclosing chunk. They are
# told apart by the trailing dot, which is empirically unambiguous across the
# corpus: QCVN 41 has 270 of the first form and none of the second, the
# consolidated administrative-violations law has 77 of the second and none of
# the first, and 168/2024/NĐ-CP has neither.
#
# A technical standard repeats its article number in each clause -- "83.1." is
# khoản 1 of Điều 83. All 270 of these were read as body text, so every clause
# of QCVN 41 collapsed into its article's chunk.
QCVN_CLAUSE_PATTERN = re.compile(r"^(\d{1,3})\.(\d{1,3})\.\s+(.*)$")

# A consolidated document renders its amendment footnote markers inline, gluing
# them to the division number: "8.240 Thời hạn tạm giữ" is khoản 8 carrying
# footnote 240, and "c)236 Hàng siêu trường" is điểm c carrying footnote 236.
# Unrecognised, khoản 8 was appended to khoản 7's text rather than becoming a
# chunk an agent could retrieve or cite.
FOOTNOTE_CLAUSE_PATTERN = re.compile(r"^(\d{1,3})\.(\d{1,3})\s+(\S.*)$")
FOOTNOTE_POINT_PATTERN = re.compile(r"^([a-zđ])\)(\d{1,3})\s+(\S.*)$", re.IGNORECASE)

# An appendix of a technical standard is a flat list whose every item is one
# self-contained definition: "B.1 Biển số P.101 "Đường cấm"" is the complete
# meaning of one road sign. Treating the appendix as a single leaf produced
# chunks of 18,000-21,000 characters -- far past the embedding window, so most
# of the sign catalogue was invisible to dense search. The letter must match the
# enclosing appendix, which is what stops a line beginning "P.124 (a,b) “Cấm
# quay đầu xe”" from being read as an item of Phụ lục P.
APPENDIX_ITEM_PATTERN = re.compile(
    r"^([A-Z])\.?(\d+(?:\.\d+)*[a-z]?)\.?\s+(\S.*)$"
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
