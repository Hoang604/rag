from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rag_eval.legal.ingestion.grammar import (
    APPENDIX_ITEM_PATTERN,
    APPENDIX_PATTERN,
    ARTICLE_PATTERN,
    CHAPTER_PATTERN,
    CLAUSE_PATTERN,
    FOOTNOTE_CLAUSE_PATTERN,
    FOOTNOTE_POINT_PATTERN,
    POINT_PATTERN,
    QCVN_CLAUSE_PATTERN,
    SECTION_PATTERN,
    looks_like_citation_fragment,
)

TokenType = Literal[
    "DOCUMENT",
    "CHAPTER",
    "SECTION",
    "ARTICLE",
    "CLAUSE",
    "POINT",
    "APPENDIX",
    "APPENDIX_ITEM",
    "BODY_TEXT",
]

_DANGLING_CONNECTORS = (
    " và",
    " về",
    " của",
    " đối với",
    " tại",
    " theo",
    " trong",
    " do",
    " từ",
    " đến",
    " hoặc",
    " nhưng",
    " để",
    " khi",
    " được",
)


@dataclass(frozen=True)
class LegalToken:
    """Represents a tokenized statutory division with lookahead line-stitching."""

    token_type: TokenType
    index_label: str
    title: str
    content: str
    line_number: int
    footnote_id: str | None = None


class LegalLexer:
    """Tokenizes raw statutory text into a structured stream of LegalToken elements."""

    def __init__(self, doc_code: str = "") -> None:
        self.doc_code = doc_code

    def _is_boundary_marker(self, line: str) -> bool:
        """Checks whether a line starts a new structural division or bullet item."""
        s = line.strip()
        if not s:
            return False
        if looks_like_citation_fragment(s):
            return False
        return bool(
            CHAPTER_PATTERN.match(s)
            or SECTION_PATTERN.match(s)
            or ARTICLE_PATTERN.match(s)
            or CLAUSE_PATTERN.match(s)
            or POINT_PATTERN.match(s)
            or APPENDIX_PATTERN.match(s)
            or QCVN_CLAUSE_PATTERN.match(s)
            or FOOTNOTE_CLAUSE_PATTERN.match(s)
            or FOOTNOTE_POINT_PATTERN.match(s)
            or re.match(r"^[-*•]\s+", s)
        )

    def _is_article_title_continuation(
        self, current_title: str, next_line: str
    ) -> bool:
        """Applies strict fail-safe syntactic rules to check if next_line continues an Article title."""
        s = next_line.strip()
        if not s or self._is_boundary_marker(s):
            return False

        if not current_title:
            return len(s) < 200 and not s.endswith((".", ":", ";"))

        if current_title.rstrip().endswith((".", ":", ";")):
            return False

        if s[0].islower():
            return True

        lower_curr = current_title.rstrip().lower()
        return any(lower_curr.endswith(conn) for conn in _DANGLING_CONNECTORS)

    def _is_heading_continuation(self, current_title: str, next_line: str) -> bool:
        """Checks if next_line continues a Chapter/Section/Appendix heading under syntactic rules."""
        s = next_line.strip()
        if not s or self._is_boundary_marker(s):
            return False

        if not current_title:
            return len(s) < 200 and not s.endswith((".", ":", ";"))

        if current_title.rstrip().endswith((".", ":", ";")):
            return False

        if current_title.isupper():
            return s.isupper() or s[0].islower()

        if s[0].islower():
            return True
        lower_curr = current_title.rstrip().lower()
        return any(lower_curr.endswith(conn) for conn in _DANGLING_CONNECTORS)

    def tokenize(self, text: str) -> list[LegalToken]:
        """Performs 2-pass lookahead tokenization, stitching multi-line titles."""
        lines = [line.strip() for line in text.splitlines()]
        raw_indexed_lines: list[tuple[int, str]] = [
            (idx + 1, line) for idx, line in enumerate(lines) if line
        ]

        if not raw_indexed_lines:
            return []

        tokens: list[LegalToken] = []
        i = 0
        total_lines = len(raw_indexed_lines)
        current_article_num: str | None = None
        current_appendix_letter: str | None = None

        while i < total_lines:
            line_no, line = raw_indexed_lines[i]

            if looks_like_citation_fragment(line):
                tokens.append(
                    LegalToken(
                        token_type="BODY_TEXT",
                        index_label="",
                        title="",
                        content=line.strip(),
                        line_number=line_no,
                    )
                )
                i += 1
                continue

            chap_match = CHAPTER_PATTERN.match(line)
            if chap_match:
                chap_num = chap_match.group(1).strip()
                chap_title = (chap_match.group(2) or "").strip()

                while i + 1 < total_lines:
                    _, next_line = raw_indexed_lines[i + 1]
                    if not self._is_heading_continuation(chap_title, next_line):
                        break
                    if not chap_title:
                        chap_title = next_line.strip()
                    else:
                        chap_title = f"{chap_title} {next_line.strip()}"
                    i += 1

                tokens.append(
                    LegalToken(
                        token_type="CHAPTER",
                        index_label=f"Chương {chap_num.upper()}",
                        title=chap_title.strip(" -:–"),
                        content=line,
                        line_number=line_no,
                    )
                )
                i += 1
                continue

            sec_match = SECTION_PATTERN.match(line)
            if sec_match:
                sec_num = sec_match.group(1).strip()
                sec_title = (sec_match.group(2) or "").strip()

                while i + 1 < total_lines:
                    _, next_line = raw_indexed_lines[i + 1]
                    if not self._is_heading_continuation(sec_title, next_line):
                        break
                    if not sec_title:
                        sec_title = next_line.strip()
                    else:
                        sec_title = f"{sec_title} {next_line.strip()}"
                    i += 1

                tokens.append(
                    LegalToken(
                        token_type="SECTION",
                        index_label=f"Mục {sec_num}",
                        title=sec_title.strip(" -:–"),
                        content=line,
                        line_number=line_no,
                    )
                )
                i += 1
                continue

            app_match = APPENDIX_PATTERN.match(line)
            if app_match:
                app_num = app_match.group(1).strip()
                app_title = (app_match.group(2) or "").strip()

                while i + 1 < total_lines:
                    _, next_line = raw_indexed_lines[i + 1]
                    if not self._is_heading_continuation(app_title, next_line):
                        break
                    if not app_title:
                        app_title = next_line.strip()
                    else:
                        app_title = f"{app_title} {next_line.strip()}"
                    i += 1

                current_appendix_letter = app_num.upper() if app_num.isalpha() else None
                current_article_num = None
                tokens.append(
                    LegalToken(
                        token_type="APPENDIX",
                        index_label=f"Phụ lục {app_num.upper()}",
                        title=app_title.strip(" -:–"),
                        content=line,
                        line_number=line_no,
                    )
                )
                i += 1
                continue

            art_match = ARTICLE_PATTERN.match(line)
            if art_match:
                art_num = art_match.group(1).strip()
                art_title = (art_match.group(2) or "").strip()

                while i + 1 < total_lines:
                    _, next_line = raw_indexed_lines[i + 1]
                    if not self._is_article_title_continuation(art_title, next_line):
                        break
                    if not art_title:
                        art_title = next_line.strip()
                    else:
                        art_title = f"{art_title} {next_line.strip()}"
                    i += 1

                current_article_num = art_num
                current_appendix_letter = None
                tokens.append(
                    LegalToken(
                        token_type="ARTICLE",
                        index_label=f"Điều {art_num}",
                        title=art_title.strip(" -:–"),
                        content=line,
                        line_number=line_no,
                    )
                )
                i += 1
                continue

            if current_appendix_letter is not None:
                item_match = APPENDIX_ITEM_PATTERN.match(line)
                if (
                    item_match
                    and item_match.group(1).upper() == current_appendix_letter
                ):
                    tokens.append(
                        LegalToken(
                            token_type="APPENDIX_ITEM",
                            index_label=f"{item_match.group(1).upper()}.{item_match.group(2)}",
                            title="",
                            content=item_match.group(3).strip(),
                            line_number=line_no,
                        )
                    )
                    i += 1
                    continue

            if current_article_num is not None:
                qcvn_match = QCVN_CLAUSE_PATTERN.match(line)
                if qcvn_match and qcvn_match.group(1) == current_article_num:
                    tokens.append(
                        LegalToken(
                            token_type="CLAUSE",
                            index_label=f"Khoản {qcvn_match.group(2)}",
                            title="",
                            content=qcvn_match.group(3).strip(),
                            line_number=line_no,
                        )
                    )
                    i += 1
                    continue

            foot_pt = FOOTNOTE_POINT_PATTERN.match(line)
            if foot_pt:
                tokens.append(
                    LegalToken(
                        token_type="POINT",
                        index_label=f"Điểm {foot_pt.group(1).lower()}",
                        title="",
                        content=foot_pt.group(3).strip(),
                        line_number=line_no,
                        footnote_id=foot_pt.group(2),
                    )
                )
                i += 1
                continue
            foot_cl = FOOTNOTE_CLAUSE_PATTERN.match(line)
            if foot_cl and current_article_num is not None:
                tokens.append(
                    LegalToken(
                        token_type="CLAUSE",
                        index_label=f"Khoản {foot_cl.group(1)}",
                        title="",
                        content=foot_cl.group(3).strip(),
                        line_number=line_no,
                        footnote_id=foot_cl.group(2),
                    )
                )
                i += 1
                continue

            cl_match = CLAUSE_PATTERN.match(line)
            if cl_match:
                cl_num = cl_match.group(1).strip()
                cl_content = cl_match.group(2).strip()
                tokens.append(
                    LegalToken(
                        token_type="CLAUSE",
                        index_label=f"Khoản {cl_num}",
                        title="",
                        content=cl_content,
                        line_number=line_no,
                    )
                )
                i += 1
                continue

            pt_match = POINT_PATTERN.match(line)
            if pt_match:
                pt_letter = pt_match.group(1).strip().lower()
                pt_content = pt_match.group(2).strip()
                tokens.append(
                    LegalToken(
                        token_type="POINT",
                        index_label=f"Điểm {pt_letter}",
                        title="",
                        content=pt_content,
                        line_number=line_no,
                    )
                )
                i += 1
                continue

            tokens.append(
                LegalToken(
                    token_type="BODY_TEXT",
                    index_label="",
                    title="",
                    content=line,
                    line_number=line_no,
                )
            )
            i += 1

        return tokens
