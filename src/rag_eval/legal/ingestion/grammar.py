"""The line shapes of Vietnamese legal drafting: division headings, enumeration markers, forms, signature lines.

Keywords are matched case-sensitively in the two spellings drafting uses (`Chương` and
`CHƯƠNG`), so a wrapped sentence that begins "chương II của Luật này" is never a heading.
A heading's number is followed by a separator (`.`, `:`, a dash), or by whitespace only
when the rest of the line is empty or set in capitals, as division titles are; a rest
that ends in ";" or "," is a list item, never a heading. Everything here judges one line;
the lexer decides from the surrounding lines which of these shapes count.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

DivisionKind = Literal["PART", "CHAPTER", "SECTION", "SUBSECTION", "APPENDIX"]

_ROMAN = r"[IVXLCDM]+"
_SUFFIX = r"[a-zđ]"

# "Phần thứ hai": the ordinal words of Vietnamese, in both cases.
ORDINAL_WORDS: dict[str, int] = {
    "nhất": 1, "một": 1, "hai": 2, "ba": 3, "tư": 4, "bốn": 4, "năm": 5,
    "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10,
}
_ORDINAL = "|".join(sorted({*ORDINAL_WORDS, *(word.upper() for word in ORDINAL_WORDS)}, key=len, reverse=True))

_NUMBERS: dict[DivisionKind, str] = {
    "PART": rf"(?:thứ|THỨ)\s+(?:{_ORDINAL})|{_ROMAN}{_SUFFIX}?|\d+{_SUFFIX}?",
    "CHAPTER": rf"{_ROMAN}{_SUFFIX}?|\d+{_SUFFIX}?",
    "SECTION": rf"\d+{_SUFFIX}?|{_ROMAN}",
    "SUBSECTION": rf"\d+{_SUFFIX}?|{_ROMAN}",
    "APPENDIX": rf"(?:số\s+)?(?:{_ROMAN}|\d+|[A-Z])(?:{_SUFFIX}|[.\-–](?:{_ROMAN}|\d+|[A-Z]))*",
}
_KEYWORDS: dict[DivisionKind, str] = {
    "PART": "Phần|PHẦN",
    "CHAPTER": "Chương|CHƯƠNG",
    "SECTION": "Mục|MỤC",
    "SUBSECTION": "Tiểu mục|TIỂU MỤC",
    "APPENDIX": "Phụ lục|PHỤ LỤC",
}
_DIVISION_PATTERNS: dict[DivisionKind, re.Pattern[str]] = {
    kind: re.compile(
        rf"^(?:{_KEYWORDS[kind]})\s+(?P<number>{_NUMBERS[kind]})"
        r"(?:\s*(?P<sep>[.:–-])\s*(?P<rest>.*)|\s+(?P<spaced>.*))?$"
    )
    for kind in ("SUBSECTION", "PART", "CHAPTER", "SECTION", "APPENDIX")
}
# An appendix heading may carry no number: "PHỤ LỤC", "Phụ lục: Danh mục giấy tờ".
_UNNUMBERED_APPENDIX = re.compile(r"^(?:Phụ lục|PHỤ LỤC)(?:\s*(?P<sep>[:.–-])\s*(?P<rest>.*)|\s+(?P<spaced>.*))?$")
# The NĐ 30/2020 appendix heading wording: "Phụ lục I kèm theo Thông tư số …".
_ATTACHED_WORDING = re.compile(r"^(?:ban hành\s+)?kèm theo\b")
# A parenthetical heading line: "(Kèm theo Thông tư số …)", "(quy định)".
PARENTHETICAL = re.compile(r"^\(.*\)$")
ATTACHED_PARENTHETICAL = re.compile(r"^\((?:Ban hành\s+)?[Kk]èm theo\b")

ARTICLE_PATTERN = re.compile(r"^(?:Điều|ĐIỀU)\s+(?P<number>\d+[a-zđ]?)\s*(?:[.:–-]\s*(?P<rest>.*))?$")
# An article "title" that opens with another article is a range citation ("Điều 5 - Điều 7 …"), not a heading.
_ARTICLE_RANGE = re.compile(r"^(?:Điều|điều)\s+\d")
CLAUSE_PATTERN = re.compile(r"^(\d+[a-zđ]?)\.\s+(.*)$")
POINT_PATTERN = re.compile(r"^([a-zđ]\d*)\)\s+(.*)$")

# Outline markers ("A.", "II.", "2.3.1."), and items numbered under an appendix's own letter ("A.1.2" in Phụ lục A).
OWN_LETTER_ITEM_PATTERN = re.compile(r"^([A-Z])\.\s?(\d+(?:\.\d+)*[a-zđ]?)\.?\s+(\S.*)$")
OUTLINE_LETTER_PATTERN = re.compile(r"^([A-ZĐ])\.\s+(\S.*)$")
OUTLINE_ROMAN_PATTERN = re.compile(r"^([IVXLCDM]+)\.\s+(\S.*)$")
# A decimal marker's last number may carry an insertion letter ("7a.", "2.3a"), as inserted articles and khoản do.
OUTLINE_DECIMAL_PATTERN = re.compile(r"^(\d{1,3}(?:\.\d{1,3})+[a-zđ]?\.?|\d{1,3}[a-zđ]?\.)\s+(\S.*)$")

FORM_PATTERN = re.compile(r"^(?:Mẫu số|MẪU SỐ)\s+(?P<number>\S+)(?P<rest>.*)$")

# The signature block: the recipients' list, or a signing-authority line ("TM. CHÍNH PHỦ", "KT. BỘ TRƯỞNG");
# a consolidated text closes with its authentication block instead.
_RECIPIENTS = re.compile(r"^Nơi nhận\s*[:.]")
_SIGNING_AUTHORITY = re.compile(r"^(?:TM|KT|TL|TUQ)\.\s+(?P<rest>\S.*)$")
_AUTHENTICATION = re.compile(r"^XÁC THỰC VĂN BẢN HỢP NHẤT$")

TABLE_ROW = re.compile(r"^\|.*\|$")
_LIST_BULLET = re.compile(r"^[-+*•]\s")


@dataclass(frozen=True)
class Division:
    """A division heading line: its kind, its number as written ("" for an unnumbered appendix) and the title on the line."""

    kind: DivisionKind
    number: str
    title: str


def _ends_list_item(rest: str) -> bool:
    return rest.endswith((";", ","))


def _title_case_rest(rest: str) -> bool:
    """True when a rest that follows the number after only whitespace can be a title: empty or in capitals."""
    return not rest or rest.isupper()


def match_division(line: str) -> Division | None:
    """The numbered Phần/Chương/Mục/Tiểu mục/Phụ lục heading `line` opens, or None.

    A rest after whitespace alone must be empty or capitals, except the appendix wording
    "kèm theo …" and a parenthetical qualifier ("Phụ lục A (quy định)"); anything else
    after whitespace is a sentence that begins with a citation ("Chương III Luật này …").
    """
    for kind, pattern in _DIVISION_PATTERNS.items():
        match = pattern.match(line)
        if match is None:
            continue
        if match.group("sep") is not None:
            rest = match.group("rest").strip()
        else:
            rest = (match.group("spaced") or "").strip()
            attached = kind == "APPENDIX" and (
                bool(_ATTACHED_WORDING.match(rest)) and not rest.endswith((".", ";")) or rest.startswith("(")
            )
            if not (_title_case_rest(rest) or attached):
                continue
        if _ends_list_item(rest):
            continue
        return Division(kind=kind, number=match.group("number"), title=rest)
    return None


def match_unnumbered_appendix(line: str) -> str | None:
    """The title on an unnumbered appendix heading line ("" for "PHỤ LỤC" alone), or None.

    Only the line's shape is judged here; the lexer admits it as a heading only where an
    appendix can begin.
    """
    match = _UNNUMBERED_APPENDIX.match(line)
    if match is None:
        return None
    if match.group("sep") is not None:
        rest = match.group("rest").strip()
    else:
        rest = (match.group("spaced") or "").strip()
        if not (_title_case_rest(rest) or rest.startswith("(")):
            return None
    return None if _ends_list_item(rest) else rest


def match_article(line: str) -> tuple[str, str] | None:
    """(number, rest) when `line` opens an article; the rest is a title unless `is_provision_text` says otherwise."""
    match = ARTICLE_PATTERN.match(line)
    if match is None:
        return None
    rest = (match.group("rest") or "").strip()
    if _ends_list_item(rest) or _ARTICLE_RANGE.match(rest):
        return None
    return match.group("number"), rest


def is_provision_text(rest: str) -> bool:
    """True when an article's text on its heading line is provision text, not a title.

    A Quyết định often writes "Điều 1. Ban hành kèm theo Quyết định này Quy chế …." with
    no title, and a consolidated text writes a repealed article as "Điều 38. (được bãi bỏ)".
    Article titles carry no closing period ("./." closes a document's last sentence) and
    are never wholly parenthetical.
    """
    return rest.endswith(".") or bool(PARENTHETICAL.match(rest))



def match_form(line: str) -> str | None:
    """The number of the form `line` heads ("01" for "Mẫu số 01"), or None."""
    match = FORM_PATTERN.match(line)
    if match is None or _ends_list_item(match.group("rest").strip()):
        return None
    return match.group("number").rstrip(".:")


def opens_postamble(line: str, previous: str) -> bool:
    """True for the line that opens the signature block, given the line before it.

    The block follows finished text: after a line ending in ":", ";" or "," the sentence
    or list goes on, so a "KT. CỤC TRƯỞNG" there is an example the provision gives.
    """
    if previous.endswith((":", ";", ",")):
        return False
    if _RECIPIENTS.match(line) or _AUTHENTICATION.match(line):
        return True
    authority = _SIGNING_AUTHORITY.match(line)
    return authority is not None and authority.group("rest").isupper()


def is_capitals_title(line: str) -> bool:
    """True for a title line set in capitals (division titles are); a table row is never a title."""
    return line.isupper() and not TABLE_ROW.match(line)


def is_marker_line(line: str) -> bool:
    """True when a line opens any division, enumeration, outline item, form, table row or list entry."""
    return bool(
        match_division(line)
        or match_unnumbered_appendix(line) is not None
        or match_article(line)
        or match_form(line)
        or CLAUSE_PATTERN.match(line)
        or POINT_PATTERN.match(line)
        or OUTLINE_LETTER_PATTERN.match(line)
        or OUTLINE_ROMAN_PATTERN.match(line)
        or OUTLINE_DECIMAL_PATTERN.match(line)
        or TABLE_ROW.match(line)
        or _LIST_BULLET.match(line)
    )


def part_number(number: str) -> str:
    """A Phần number as cited: "thứ hai" becomes "2"; Roman and Arabic numbers are kept as written."""
    words = number.split()
    if len(words) == 2 and words[0].lower() == "thứ":
        return str(ORDINAL_WORDS[words[1].lower()])
    return number
