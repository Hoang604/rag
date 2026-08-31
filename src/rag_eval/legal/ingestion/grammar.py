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

SIGN_CODE_PATTERN = re.compile(
    r"\b([PWIROMS]\.[\d]+[a-z]?|[M]\.[\d]+\.[\d]+)\b",
    re.IGNORECASE,
)
