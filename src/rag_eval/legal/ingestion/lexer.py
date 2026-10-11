"""Tokenizes canonical text into the divisions of Vietnamese legal drafting, one line at a time.

Canonical text holds one paragraph per line, so a heading's title is on its own line or
on the next one; no line is repaired across breaks. Which line shapes count depends on
the scope the line is read in:

- A line that starts inside quoted text carries another document's wording: body text.
- The signature block opens once, outside appendices, at the recipients' list, a
  signing-authority line or a consolidated text's authentication block, and closes only
  at a division or appendix heading. The main text ends at the signature, so a Phần,
  Chương, Mục or Điều after it opens attached text (an attachment), whose title is not
  guessed.
- Each scope (the main body, an appendix, an attachment) reads an outline of numbered
  items until its first article; a Phần/Chương/Mục/Tiểu mục heading restarts it.
- Inside an appendix or attachment a form ("Mẫu số 01") runs to the next form or
  division heading, and every line of it is body text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rag_eval.legal.ingestion.grammar import (
    ATTACHED_PARENTHETICAL,
    CLAUSE_PATTERN,
    OUTLINE_DECIMAL_PATTERN,
    PARENTHETICAL,
    POINT_PATTERN,
    Division,
    DivisionKind,
    is_capitals_title,
    is_marker_line,
    is_provision_text,
    match_article,
    match_division,
    match_form,
    match_unnumbered_appendix,
    opens_postamble,
    part_number,
)
from rag_eval.legal.ingestion.outline import Outline, follows_number
from rag_eval.legal.ingestion.quotes import quote_spans

TokenType = Literal[
    "PART", "CHAPTER", "SECTION", "SUBSECTION", "ARTICLE", "CLAUSE", "POINT",
    "APPENDIX", "ATTACHMENT", "OUTLINE_ITEM", "FORM", "POSTAMBLE", "BODY_TEXT",
]

_DIVISION_WORD: dict[DivisionKind, str] = {
    "PART": "Phần",
    "CHAPTER": "Chương",
    "SECTION": "Mục",
    "SUBSECTION": "Tiểu mục",
    "APPENDIX": "Phụ lục",
}
# An appendix heading takes at most this many following lines: its title and its "(Kèm theo …)" line.
_APPENDIX_HEADING_LINES = 2


@dataclass(frozen=True)
class LegalToken:
    """One structural line (or heading block) of canonical text."""

    token_type: TokenType
    index_label: str  # "Phần 2", "Chương IIa", "Điều 12đ", "Khoản 1đ", "Điểm a", "Phụ lục I-A", "2.3.1", "Mẫu số 01"; "" for BODY_TEXT/POSTAMBLE/ATTACHMENT
    title: str  # division title; "" when the division has none
    content: str  # the line text after the marker (BODY_TEXT and POSTAMBLE: the whole line)
    line_number: int
    last_line: int  # last heading line (title and parenthetical lines included); line_number - 1 when the token's own line is body
    # An OUTLINE_ITEM's key (markers from the outermost item down); empty for every other token.
    outline: tuple[str, ...] = ()


class LegalLexer:
    """Tokenizes canonical statutory text into a stream of LegalToken elements."""

    def tokenize(self, text: str) -> list[LegalToken]:
        """Tokens in line order; lines inside quote spans, forms and the postamble are BODY_TEXT."""
        return _Scan(text).tokens()


def _quoted_lines(text: str) -> set[int]:
    """Line numbers (1-indexed) whose first non-blank character lies inside quoted text."""
    spans = quote_spans(text)
    quoted: set[int] = set()
    offset = 0
    for number, raw in enumerate(text.splitlines(keepends=True), start=1):
        first = offset + len(raw) - len(raw.lstrip())
        if raw.strip() and spans.contains(first):
            quoted.add(number)
        offset += len(raw)
    return quoted


class _Scan:
    """The state of one tokenization pass."""

    def __init__(self, text: str) -> None:
        self.lines: list[tuple[int, str]] = [
            (number, line.strip()) for number, line in enumerate(text.splitlines(), start=1) if line.strip()
        ]
        self.quoted = _quoted_lines(text)
        self.out: list[LegalToken] = []
        self.i = 0
        self.in_appendix = False  # an appendix or attachment is open
        self.own_letter: str | None = None  # the open appendix's letter, for "A.1.2"-style items
        self.articles_in_scope = False  # the current scope (main body, appendix, attachment) has an article
        self.outline: Outline | None = Outline(None)
        self.form_open = False
        self.postamble: Literal["NONE", "OPEN", "DONE"] = "NONE"
        self.article_number: str | None = None
        # The khoản number of the open decimal-numbered khoản ("46.6."), None under any other khoản.
        self.decimal_clause: str | None = None

    def tokens(self) -> list[LegalToken]:
        while self.i < len(self.lines):
            self._line()
        return self.out

    # -- helpers --------------------------------------------------------------------------

    def _emit(self, token_type: TokenType, label: str, title: str, content: str, last_line: int | None = None, outline: tuple[str, ...] = ()) -> None:
        line_no = self.lines[self.i][0]
        self.out.append(
            LegalToken(
                token_type=token_type,
                index_label=label,
                title=title,
                content=content,
                line_number=line_no,
                last_line=line_no if last_line is None else last_line,
                outline=outline,
            )
        )

    def _body(self) -> None:
        self._emit("BODY_TEXT", "", "", self.lines[self.i][1])
        self.i += 1

    def _peek(self, offset: int = 1) -> str | None:
        """The text of a later line, None past the end or when that line starts inside a quote."""
        index = self.i + offset
        if index >= len(self.lines) or self.lines[index][0] in self.quoted:
            return None
        return self.lines[index][1]

    def _appendix_heading(self, line: str, *, inside_form: bool) -> Division | None:
        """The appendix `line` opens here, or None; an unnumbered one only where an appendix can begin."""
        division = match_division(line)
        if division is not None:
            return division if division.kind == "APPENDIX" else None
        title = match_unnumbered_appendix(line)
        if title is None:
            return None
        following = self._peek()
        attached = following is not None and bool(ATTACHED_PARENTHETICAL.match(following))
        where_appendices_begin = not inside_form and (self.postamble == "OPEN" or self.in_appendix)
        return Division(kind="APPENDIX", number="", title=title) if attached or where_appendices_begin else None

    def _restart_outline(self) -> None:
        self.outline = None if self.articles_in_scope else Outline(self.own_letter)

    def _open_scope(self, own_letter: str | None) -> None:
        self.in_appendix = True
        self.own_letter = own_letter
        self.articles_in_scope = False
        self.outline = Outline(own_letter)
        self.form_open = False
        self.article_number = None
        self.decimal_clause = None

    # -- the dispatcher -------------------------------------------------------------------

    def _line(self) -> None:
        line_no, line = self.lines[self.i]
        if line_no in self.quoted:
            self._body()
            return
        if self.postamble == "OPEN":
            if not self._closes_postamble(line):
                self._body()
                return
            self.postamble = "DONE"
            if self._appendix_heading(line, inside_form=False) is None:
                self._open_scope(None)
                self._emit("ATTACHMENT", "", "", "", last_line=line_no - 1)
        if self.form_open:
            if not self._closes_form(line):
                self._body()
                return
            self.form_open = False
        previous = self.lines[self.i - 1][1] if self.i else ""
        if self.postamble == "NONE" and not self.in_appendix and opens_postamble(line, previous):
            self.postamble = "OPEN"
            self.article_number = None
            self._emit("POSTAMBLE", "", "", line)
            self.i += 1
            return
        appendix = self._appendix_heading(line, inside_form=False)
        if appendix is not None:
            self._appendix(appendix)
            return
        division = match_division(line)
        if division is not None:
            self._division(division)
            return
        article = match_article(line)
        if article is not None:
            self._article(*article)
            return
        form = match_form(line) if self.in_appendix else None
        if form is not None:
            self.form_open = True
            self._emit("FORM", f"Mẫu số {form}", "", line)
            self.i += 1
            return
        if self.outline is not None:
            item = self.outline.accept(line)
            if item is not None:
                self._emit("OUTLINE_ITEM", item.label, "", item.content, outline=item.key)
                self.i += 1
                return
        if self._decimal_provision(line):
            return
        clause = CLAUSE_PATTERN.match(line)
        if clause:
            self.decimal_clause = None
            self._emit("CLAUSE", f"Khoản {clause.group(1)}", "", clause.group(2).strip())
            self.i += 1
            return
        point = POINT_PATTERN.match(line)
        if point:
            self._emit("POINT", f"Điểm {point.group(1)}", "", point.group(2).strip())
            self.i += 1
            return
        self._body()

    # -- scope ends -----------------------------------------------------------------------

    def _closes_postamble(self, line: str) -> bool:
        """True when `line` ends the signature block: a division, article or appendix heading."""
        return bool(self._appendix_heading(line, inside_form=False) or match_division(line) or match_article(line))

    def _closes_form(self, line: str) -> bool:
        """True when `line` ends the open form: another form, or a division, article or appendix heading."""
        return bool(
            self._appendix_heading(line, inside_form=True)
            or match_form(line)
            or match_division(line)
            or match_article(line)
        )

    # -- headings -------------------------------------------------------------------------

    def _appendix(self, division: Division) -> None:
        number = division.number.removeprefix("số").strip()
        title = "" if PARENTHETICAL.match(division.title) else division.title
        last = self.i
        for offset in range(1, _APPENDIX_HEADING_LINES + 1):
            following = self._peek(offset)
            if following is None or last != self.i + offset - 1:
                break
            if PARENTHETICAL.match(following):
                last = self.i + offset
            elif not title and is_capitals_title(following) and not is_marker_line(following):
                title = following
                last = self.i + offset
        self._open_scope(number if len(number) == 1 and number.isalpha() else None)
        label = f"Phụ lục {number}" if number else "Phụ lục"
        self._emit("APPENDIX", label, title, division.title, last_line=self.lines[last][0])
        self.i = last + 1

    def _division(self, division: Division) -> None:
        number = part_number(division.number) if division.kind == "PART" else division.number
        title = division.title
        last = self.i
        following = self._peek()
        if not title and following is not None and not is_marker_line(following):
            title = following
            last = self.i + 1
        self._restart_outline()
        self.article_number = None
        self._emit(division.kind, f"{_DIVISION_WORD[division.kind]} {number}", title, division.title, last_line=self.lines[last][0])
        self.i = last + 1

    def _article(self, number: str, title: str) -> None:
        line_no = self.lines[self.i][0]
        self.article_number = number
        self.decimal_clause = None
        self.articles_in_scope = True
        self.outline = None
        if is_provision_text(title):
            self._emit("ARTICLE", f"Điều {number}", "", title, last_line=line_no - 1)
        else:
            self._emit("ARTICLE", f"Điều {number}", title, title)
        self.i += 1

    def _decimal_provision(self, line: str) -> bool:
        """Emits "N.M." under Điều N as khoản M and "N.M.K." as its điểm K; False when the line is neither.

        A khoản number must be 1 or follow the open one, so a money amount that opens a
        line ("7.500 đồng …") is never read as khoản 500 of Điều 7.
        """
        decimal = OUTLINE_DECIMAL_PATTERN.match(line) if self.article_number is not None else None
        if decimal is None:
            return False
        parts = decimal.group(1).rstrip(".").split(".")
        content = decimal.group(2).strip()
        if len(parts) == 2 and parts[0] == self.article_number:
            opens = parts[1] == "1" if self.decimal_clause is None else follows_number(parts[1], self.decimal_clause)
            if opens:
                self.decimal_clause = parts[1]
                self._emit("CLAUSE", f"Khoản {parts[1]}", "", content)
                self.i += 1
                return True
        if len(parts) == 3 and parts[:2] == [self.article_number, self.decimal_clause]:
            self._emit("POINT", f"Điểm {parts[2]}", "", content)
            self.i += 1
            return True
        return False
