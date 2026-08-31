"""AST Node data structures and statutory hierarchy tree parser for Vietnamese Traffic Law.

Converts raw Vietnamese legal text (Laws, Decrees, Circulars, QCVN Standards) into a structured
Abstract Syntax Tree (AST) while preserving hierarchical lineage, clause lead sentences,
technical sign specifications, and road marking specifications.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar
from rag_eval.legal.schemas import canonical_doc_slug


def sanitize_ltree_label(label: str) -> str:
    """Normalizes a Vietnamese or alphanumeric label into a valid PostgreSQL ltree label.

    Ltree labels must contain only alphanumeric ASCII characters and underscores [A-Za-z0-9_],
    maximum 256 characters per label.
    """
    if not label:
        return "root"
    # Pre-transliterate Vietnamese Đ/đ into ASCII D/d before NFKD normalization
    transliterated = label.replace("đ", "d").replace("Đ", "D")
    # Unaccent and lowercase
    normalized = unicodedata.normalize("NFKD", transliterated)
    ascii_text = "".join(c for c in normalized if not unicodedata.combining(c))
    # Replace non-alphanumeric chars with underscore
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", ascii_text.lower()).strip("_")
    # Clean up repeated underscores
    clean = re.sub(r"_+", "_", clean)
    # Enforce PostgreSQL ltree label maximum length (256 chars)
    if len(clean) > 256:
        clean = clean[:256].rstrip("_")
    return clean or "node"


@dataclass
class ASTNode:
    """Represents a hierarchical legislative unit in Vietnamese statutory law."""

    level: (
        Literal[
            "DOCUMENT",
            "PART",
            "CHAPTER",
            "SECTION",
            "SUB_SECTION",
            "ARTICLE",
            "CLAUSE",
            "POINT",
            "APPENDIX",
            "SIGN_SPEC",
            "MARKING_SPEC",
            "TABLE",
        ]
        | str
    )
    index_label: (
        str  # e.g., "100/2019/NĐ-CP", "Chương II", "Điều 5", "Khoản 3", "Điểm a", "P.102", "1.1"
    )
    title: str  # e.g., "Xử phạt người điều khiển xe ô tô..."
    raw_text: str  # Verbatim textual content of this node
    lead_sentence: str | None = (
        None  # Clause lead sentence inherited by child sub-points
    )
    children: list[ASTNode] = field(default_factory=lambda: list[ASTNode]())
    parent_path: str = ""  # Dot-separated path of parent node
    depth: int = 1  # 1 = Document, 2 = Chapter/Appendix, 4 = Article/Sign/Marking, 5 = Clause, 6 = Point
    display_order: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def full_path(self) -> str:
        """Returns deterministic ltree-compatible dot-separated hierarchical path."""
        if self.level == "DOCUMENT":
            return canonical_doc_slug(self.index_label)

        # Determine short tag for this node level
        tag = self._compute_label_tag()
        if self.parent_path:
            return f"{self.parent_path}.{tag}"
        return tag

    def _compute_label_tag(self) -> str:
        """Computes standardized ltree label tag based on node level and index."""
        idx_lower = self.index_label.lower().strip()
        if self.level == "CHAPTER":
            num = re.search(r"chương\s+([ivxlcdm0-9]+)", idx_lower)
            return (
                f"c_{sanitize_ltree_label(num.group(1))}"
                if num
                else sanitize_ltree_label(self.index_label)
            )
        if self.level == "SECTION":
            num = re.search(r"mục\s+([0-9]+)", idx_lower)
            return (
                f"s_{sanitize_ltree_label(num.group(1))}"
                if num
                else sanitize_ltree_label(self.index_label)
            )
        if self.level == "SUB_SECTION":
            num = re.search(r"tiểu\s+mục\s+([0-9]+)", idx_lower)
            return (
                f"ss_{sanitize_ltree_label(num.group(1))}"
                if num
                else sanitize_ltree_label(self.index_label)
            )
        if self.level == "ARTICLE":
            num = re.search(r"điều\s+([0-9]+[a-zđ]*)", idx_lower)
            return f"a{sanitize_ltree_label(num.group(1))}" if num else sanitize_ltree_label(self.index_label)
        if self.level == "CLAUSE":
            num = re.search(r"(?:khoản\s+)?([0-9]+)", idx_lower)
            return f"c{sanitize_ltree_label(num.group(1))}" if num else sanitize_ltree_label(self.index_label)
        if self.level == "POINT":
            letter = re.search(r"(?:điểm\s+)?([a-zđ])", idx_lower)
            return (
                f"p_{sanitize_ltree_label(letter.group(1))}"
                if letter
                else sanitize_ltree_label(self.index_label)
            )
        if self.level == "APPENDIX":
            app_id = re.search(r"phụ\s+lục\s+([a-z0-9]+)", idx_lower)
            return (
                f"app_{sanitize_ltree_label(app_id.group(1))}"
                if app_id
                else sanitize_ltree_label(self.index_label)
            )
        if self.level in ("SIGN_SPEC", "MARKING_SPEC"):
            return sanitize_ltree_label(self.index_label)

        return sanitize_ltree_label(self.index_label)

    def find_nodes_by_level(self, level: str) -> list[ASTNode]:
        """Recursively collects all descendant nodes matching a specific level."""
        results: list[ASTNode] = []
        if self.level == level:
            results.append(self)
        for child in self.children:
            results.extend(child.find_nodes_by_level(level))
        return results

    def flatten(self) -> list[ASTNode]:
        """Flattens the entire AST hierarchy into a pre-order traversal list."""
        nodes: list[ASTNode] = [self]
        for child in self.children:
            nodes.extend(child.flatten())
        return nodes


class LegalASTParser:
    """Production AST parser for Vietnamese legislative texts."""

    def __init__(
        self, grammar: type[VietnameseLegalGrammar] = VietnameseLegalGrammar
    ) -> None:
        self.grammar = grammar

    def parse_document(
        self,
        doc_code: str,
        raw_text: str,
        doc_title: str | None = None,
        doc_type: str = "NGHI_DINH",
    ) -> ASTNode:
        """Parses a full Vietnamese statutory document into an AST hierarchy tree."""
        normalized_lines = [line.strip() for line in raw_text.splitlines()]
        clean_text = "\n".join(normalized_lines)
        title = doc_title or doc_code
        root = ASTNode(
            level="DOCUMENT",
            index_label=doc_code,
            title=title,
            raw_text=clean_text[:1000].strip(),
            parent_path="",
            depth=1,
            display_order=0,
            metadata={"doc_code": doc_code, "doc_type": doc_type, "title": title},
        )

        # DEF-09 FIX: Route by document type or code prefix, NOT by presence of "PHỤ LỤC" in body
        is_tech_std = (
            doc_type in ("QUY_CHUAN_KY_THUAT", "TIEU_CHUAN_KY_THUAT", "QCVN", "TCVN")
            or "QCVN" in doc_code.upper()
            or "TCVN" in doc_code.upper()
        )
        if is_tech_std:
            self._parse_technical_standard(root, clean_text)
        else:
            self._parse_standard_statute(root, clean_text)

        return root

    def _parse_standard_statute(self, root: ASTNode, raw_text: str) -> None:
        """Parses standard legislative statute (Decrees, Laws, Circulars)."""
        doc_path = root.full_path
        order = 1

        # Check for Chapters
        chapter_matches = list(self.grammar.CHAPTER.finditer(raw_text))
        if chapter_matches:
            for idx, chap_match in enumerate(chapter_matches):
                chap_num = chap_match.group(1)
                chap_title = chap_match.group(2).strip()
                chap_start = chap_match.start()
                chap_end = (
                    chapter_matches[idx + 1].start()
                    if idx + 1 < len(chapter_matches)
                    else len(raw_text)
                )
                chap_text = raw_text[chap_start:chap_end]

                chap_node = ASTNode(
                    level="CHAPTER",
                    index_label=f"Chương {chap_num}",
                    title=chap_title,
                    raw_text=chap_text[:500].strip(),
                    parent_path=doc_path,
                    depth=2,
                    display_order=order,
                )
                order += 1
                root.children.append(chap_node)

                # Parse Sections or direct Articles inside Chapter
                self._parse_sections_or_articles_in_chapter(
                    chap_node, chap_text, chap_node.full_path
                )
        else:
            # No chapters declared - parse Articles directly under Document
            self._parse_articles_in_block(root, raw_text, doc_path)

    def _parse_sections_or_articles_in_chapter(
        self, chap_node: ASTNode, chap_text: str, chap_path: str
    ) -> None:
        """Parses Sections (Mục) or direct Articles within a Chapter."""
        section_matches = list(self.grammar.SECTION.finditer(chap_text))
        if section_matches:
            order = 1
            for idx, sec_match in enumerate(section_matches):
                sec_num = sec_match.group(1)
                sec_title = sec_match.group(2).strip()
                sec_start = sec_match.start()
                sec_end = (
                    section_matches[idx + 1].start()
                    if idx + 1 < len(section_matches)
                    else len(chap_text)
                )
                sec_text = chap_text[sec_start:sec_end]

                sec_node = ASTNode(
                    level="SECTION",
                    index_label=f"Mục {sec_num}",
                    title=sec_title,
                    raw_text=sec_text[:500].strip(),
                    parent_path=chap_path,
                    depth=3,
                    display_order=order,
                )
                order += 1
                chap_node.children.append(sec_node)
                self._parse_articles_in_block(sec_node, sec_text, sec_node.full_path)
        else:
            self._parse_articles_in_block(chap_node, chap_text, chap_path)

    def _parse_articles_in_block(
        self, parent_node: ASTNode, block_text: str, parent_path: str
    ) -> None:
        """Parses Article blocks and attaches them to parent AST node."""
        article_matches = list(self.grammar.ARTICLE.finditer(block_text))
        order = 1
        for idx, art_match in enumerate(article_matches):
            art_num_str = art_match.group(1)
            art_title = art_match.group(2).strip()
            art_start = art_match.start()
            art_end = (
                article_matches[idx + 1].start()
                if idx + 1 < len(article_matches)
                else len(block_text)
            )
            art_full_text = block_text[art_start:art_end]

            art_digits = re.sub(r"\D", "", art_num_str)
            art_num_val = int(art_digits) if art_digits else 1
            art_node = ASTNode(
                level="ARTICLE",
                index_label=f"Điều {art_num_str}",
                title=art_title,
                raw_text=art_full_text.strip(),
                parent_path=parent_path,
                depth=4,
                display_order=order,
                metadata={"article_number": art_num_val, "article_index": f"Điều {art_num_str}"},
            )
            order += 1
            parent_node.children.append(art_node)

            # Parse Clauses inside Article
            self._parse_clauses_in_article(art_node, art_full_text, art_node.full_path)

    def _parse_clauses_in_article(
        self, art_node: ASTNode, article_text: str, parent_path: str
    ) -> None:
        """Parses Clauses (Khoản) and child Points (Điểm) within an Article."""
        first_line_end = article_text.find("\n")
        body_text = article_text[first_line_end + 1 :] if first_line_end != -1 else ""

        clause_matches = list(self.grammar.CLAUSE.finditer(body_text))
        if not clause_matches:
            # Article without numbered clauses - single clause block
            if body_text.strip():
                cl_node = ASTNode(
                    level="CLAUSE",
                    index_label="Khoản 1",
                    title=art_node.title,
                    raw_text=body_text.strip(),
                    lead_sentence=body_text.strip(),
                    parent_path=parent_path,
                    depth=5,
                    display_order=1,
                    metadata={"clause_number": 1},
                )
                art_node.children.append(cl_node)
                self._parse_points_in_clause(cl_node, body_text, cl_node.full_path)
            return

        order = 1
        for idx, cl_match in enumerate(clause_matches):
            cl_num_str = cl_match.group(1)
            cl_start = cl_match.start()
            cl_end = (
                clause_matches[idx + 1].start()
                if idx + 1 < len(clause_matches)
                else len(body_text)
            )
            cl_full_text = body_text[cl_start:cl_end].strip()

            # Determine lead sentence: text up to the first point or colon
            lead_sentence = self._extract_lead_sentence(cl_full_text)

            cl_node = ASTNode(
                level="CLAUSE",
                index_label=f"Khoản {cl_num_str}",
                title=f"{art_node.index_label} Khoản {cl_num_str}",
                raw_text=cl_full_text,
                lead_sentence=lead_sentence,
                parent_path=parent_path,
                depth=5,
                display_order=order,
                metadata={"clause_number": int(cl_num_str)},
            )
            order += 1
            art_node.children.append(cl_node)

            # Parse Points inside Clause
            self._parse_points_in_clause(cl_node, cl_full_text, cl_node.full_path)

    def _extract_lead_sentence(self, clause_text: str) -> str:
        """Extracts introductory lead sentence declaring fines or rules before sub-points."""
        point_match = self.grammar.POINT.search(clause_text)
        if point_match:
            lead = clause_text[: point_match.start()].strip()
            if lead:
                return lead
        lines = clause_text.split("\n")
        return lines[0].strip() if lines else clause_text.strip()

    # Pattern detecting trailing aggravating sentences / common rules after points in a clause
    CLAUSE_TAIL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:\n\s*\n|\n)\s*(?=(?:Thực hiện|Vi phạm|Người điều khiển|Trường hợp|Ngoài việc|Đối với|Quy định tại|Hành vi vi phạm|Nếu)\b[^\n]*(?:thì|bị|sẽ bị|tước|tạm giữ|trừ|phạt|áp dụng))",
        re.IGNORECASE,
    )

    def _parse_points_in_clause(
        self, cl_node: ASTNode, clause_text: str, parent_path: str
    ) -> None:
        """Parses Points (Điểm a, b, c) and attaches inherited lead sentence and extracts clause tail."""
        point_matches = list(self.grammar.POINT.finditer(clause_text))
        order = 1
        for idx, pt_match in enumerate(point_matches):
            pt_letter = pt_match.group(1).lower()
            pt_start = pt_match.start()
            is_last_point = idx + 1 == len(point_matches)
            pt_end = (
                point_matches[idx + 1].start()
                if not is_last_point
                else len(clause_text)
            )
            pt_full_text = clause_text[pt_start:pt_end].strip()

            # For the last point, detect if there is a trailing clause tail paragraph
            if is_last_point:
                tail_match = self.CLAUSE_TAIL_PATTERN.search(pt_full_text)
                if tail_match:
                    pt_clean_text = pt_full_text[: tail_match.start()].strip()
                    clause_tail = pt_full_text[tail_match.start() :].strip()
                    cl_node.metadata["clause_tail"] = clause_tail
                    pt_full_text = pt_clean_text

            pt_node = ASTNode(
                level="POINT",
                index_label=f"Điểm {pt_letter}",
                title=f"{cl_node.title} Điểm {pt_letter}",
                raw_text=pt_full_text,
                lead_sentence=cl_node.lead_sentence,
                parent_path=parent_path,
                depth=6,
                display_order=order,
                metadata={"point_letter": pt_letter},
            )
            order += 1
            cl_node.children.append(pt_node)

    def _parse_technical_standard(self, root: ASTNode, raw_text: str) -> None:
        """Parses technical standards (QCVN 41:2019/BGTVT) including appendices, signs, and road markings."""
        doc_path = root.full_path
        order = 1

        appendix_matches = list(self.grammar.APPENDIX.finditer(raw_text))
        if not appendix_matches:
            self._parse_standard_statute(root, raw_text)
            return

        for idx, app_match in enumerate(appendix_matches):
            app_id = app_match.group(1).strip()
            app_title = app_match.group(2).strip()
            app_start = app_match.start()
            app_end = (
                appendix_matches[idx + 1].start()
                if idx + 1 < len(appendix_matches)
                else len(raw_text)
            )
            app_text = raw_text[app_start:app_end]

            app_node = ASTNode(
                level="APPENDIX",
                index_label=f"Phụ lục {app_id}",
                title=app_title,
                raw_text=app_text[:500].strip(),
                parent_path=doc_path,
                depth=2,
                display_order=order,
                metadata={"appendix_id": app_id},
            )
            order += 1
            root.children.append(app_node)

            self._parse_appendix_items(
                app_node, app_text, app_node.full_path, app_id, app_title
            )

    def _parse_appendix_items(
        self,
        app_node: ASTNode,
        appendix_text: str,
        parent_path: str,
        app_id: str,
        app_title: str,
    ) -> None:
        """DEF-12 FIX: Inspects appendix content dynamically for markings, signs, or statutory text."""
        marking_matches = list(self.grammar.MARKING_SPEC.finditer(appendix_text))
        sign_matches = list(self.grammar.SIGN_SPEC.finditer(appendix_text))
        app_title_upper = app_title.upper()

        if "VẠCH" in app_title_upper or (marking_matches and not sign_matches):
            self._parse_marking_specs_in_appendix(
                app_node, appendix_text, parent_path
            )
            return

        if sign_matches:
            self._parse_sign_specs_in_appendix(app_node, appendix_text, parent_path)
            return

        # Fallback to standard articles if appendix contains statutory text
        self._parse_articles_in_block(app_node, appendix_text, parent_path)

    def _parse_sign_specs_in_appendix(
        self, app_node: ASTNode, appendix_text: str, parent_path: str
    ) -> None:
        """Parses sign specification items inside technical appendix."""
        sign_matches = list(self.grammar.SIGN_SPEC.finditer(appendix_text))
        order = len(app_node.children) + 1
        for idx, s_match in enumerate(sign_matches):
            sign_code = s_match.group(1).strip()
            sign_name = s_match.group(2).strip()
            sign_body = (
                s_match.group("body").strip()
                if "body" in s_match.groupdict() and s_match.group("body")
                else (
                    s_match.group(3).strip() if len(s_match.groups()) >= 3 else ""
                )
            )
            s_start = s_match.start()
            s_end = (
                sign_matches[idx + 1].start()
                if idx + 1 < len(sign_matches)
                else len(appendix_text)
            )
            s_full_text = appendix_text[s_start:s_end].strip()

            sign_node = ASTNode(
                level="SIGN_SPEC",
                index_label=sign_code,
                title=sign_name,
                raw_text=s_full_text,
                lead_sentence=f"Quy chuẩn kỹ thuật biển báo {sign_code}: {sign_name}",
                parent_path=parent_path,
                depth=4,
                display_order=order,
                metadata={
                    "sign_code": sign_code,
                    "sign_name": sign_name,
                    "sign_body": sign_body,
                },
            )
            order += 1
            app_node.children.append(sign_node)

    def _parse_marking_specs_in_appendix(
        self, app_node: ASTNode, appendix_text: str, parent_path: str
    ) -> None:
        """Parses road marking specification items inside technical appendix (Phụ lục G)."""
        marking_matches = list(self.grammar.MARKING_SPEC.finditer(appendix_text))
        order = len(app_node.children) + 1
        for idx, m_match in enumerate(marking_matches):
            marking_code = m_match.group(1).strip()
            marking_name = m_match.group(2).strip()
            marking_body = (
                m_match.group("body").strip()
                if "body" in m_match.groupdict() and m_match.group("body")
                else (
                    m_match.group(3).strip() if len(m_match.groups()) >= 3 else ""
                )
            )
            m_start = m_match.start()
            m_end = (
                marking_matches[idx + 1].start()
                if idx + 1 < len(marking_matches)
                else len(appendix_text)
            )
            m_full_text = appendix_text[m_start:m_end].strip()

            marking_node = ASTNode(
                level="MARKING_SPEC",
                index_label=marking_code,
                title=marking_name,
                raw_text=m_full_text,
                lead_sentence=f"Quy chuẩn kỹ thuật vạch kẻ đường {marking_code}: {marking_name}",
                parent_path=parent_path,
                depth=4,
                display_order=order,
                metadata={
                    "marking_code": marking_code,
                    "marking_name": marking_name,
                    "marking_body": marking_body,
                },
            )
            order += 1
            app_node.children.append(marking_node)
