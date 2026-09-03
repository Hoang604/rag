"""Abstract Syntax Tree (AST) parser for Vietnamese statutory legal texts.

Parses arbitrary legal documents into a clean hierarchical tree of ASTNode elements
using the 2-pass lookahead LegalLexer with support for all 7 statutory divisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from rag_eval.legal.ingestion.lexer import LegalLexer
from rag_eval.legal.schemas import (
    sanitize_index_label,
    sanitize_ltree_label,
    validate_ltree_path,
)

ClauseKind = Literal["CONTAINER_STEM", "STANDALONE_RULE", "NONE"]


@dataclass
class ASTNode:
    """Represents a hierarchical node in the legal syntax tree."""

    node_type: str  # DOCUMENT | CHAPTER | SECTION | ARTICLE | CLAUSE | POINT | APPENDIX
    index_label: str  # e.g., "Điều 5", "Khoản 3", "Điểm a", "Mục 1", "Phụ lục I"
    title: str  # Section/Article title or heading
    full_path: str  # ltree path e.g. "doc_100_2019.c_ii.s_1.a_5.c_3.p_a"
    depth: int  # 1=Doc, 2=Chapter, 3=Section, 4=Article, 5=Clause, 6=Point, 7=Appendix
    raw_text: str  # Raw text content of this division
    lead_sentence: str = ""  # Inherited lead sentence (for clauses/points)
    clause_kind: ClauseKind = "NONE"  # CONTAINER_STEM vs STANDALONE_RULE for clauses
    parent_path: str | None = None
    display_order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[ASTNode] = field(default_factory=list)



def _disambiguate(parent: ASTNode, segment: str) -> str:
    """Returns a segment unique among `parent`'s children, suffixing if needed.

    An enumeration letter repeats under one parent when a division heading was
    not recognised -- QCVN 41 numbers its khoản "7.1." rather than "1.", so
    every point under 7.1 and 7.2 attaches straight to Điều 7 and the second
    a) claims the first a)'s path. A consolidated law does the same where an
    amending block restates a list.

    Dropping or overwriting the later provision loses statute, which is the one
    outcome never acceptable here, so the path is made unique instead. The
    suffix records that the hierarchy at this point is approximate; the text and
    its retrievability are exact.
    """
    taken = {child.full_path.rsplit(".", 1)[-1] for child in parent.children}
    if segment not in taken:
        return segment
    ordinal = 2
    while f"{segment}_{ordinal}" in taken:
        ordinal += 1
    return f"{segment}_{ordinal}"


class LegalASTParser:
    """Recursively parses raw statutory text into a hierarchy of ASTNode objects."""

    def __init__(self, doc_code: str) -> None:
        self.doc_code = doc_code
        self.doc_prefix = sanitize_ltree_label(doc_code)
        self.lexer = LegalLexer(doc_code=doc_code)

    def parse(self, text: str, doc_title: str = "") -> ASTNode:
        """Parses the entire document text into a root ASTNode with nested children."""
        root = ASTNode(
            node_type="DOCUMENT",
            index_label=self.doc_code,
            title=doc_title or self.doc_code,
            full_path=self.doc_prefix,
            depth=1,
            raw_text=text[:500],
            display_order=0,
            metadata={"doc_code": self.doc_code},
        )

        tokens = self.lexer.tokenize(text)
        if not tokens:
            return root

        current_chapter: ASTNode | None = None
        current_section: ASTNode | None = None
        current_article: ASTNode | None = None
        current_clause: ASTNode | None = None
        current_appendix: ASTNode | None = None

        doc_order = 0

        for token in tokens:
            # 1. CHAPTER
            if token.token_type == "CHAPTER":
                chap_num = sanitize_ltree_label(token.index_label.replace("Chương", "").strip())
                chap_seg = _disambiguate(root, f"c_{chap_num}")
                chap_path = validate_ltree_path(f"{self.doc_prefix}.{chap_seg}")
                doc_order += 1
                current_chapter = ASTNode(
                    node_type="CHAPTER",
                    index_label=token.index_label,
                    title=token.title,
                    full_path=chap_path,
                    depth=2,
                    raw_text=token.content,
                    parent_path=self.doc_prefix,
                    display_order=doc_order,
                )
                root.children.append(current_chapter)
                current_section = None
                current_article = None
                current_clause = None
                current_appendix = None
                continue

            # 2. SECTION
            if token.token_type == "SECTION":
                sec_num = sanitize_ltree_label(token.index_label.replace("Mục", "").strip())
                parent_p = current_chapter.full_path if current_chapter else self.doc_prefix
                sec_path = validate_ltree_path(f"{parent_p}.s_{sec_num}")
                doc_order += 1
                current_section = ASTNode(
                    node_type="SECTION",
                    index_label=token.index_label,
                    title=token.title,
                    full_path=sec_path,
                    depth=3,
                    raw_text=token.content,
                    parent_path=parent_p,
                    display_order=doc_order,
                )
                if current_chapter:
                    current_chapter.children.append(current_section)
                else:
                    root.children.append(current_section)
                current_article = None
                current_clause = None
                current_appendix = None
                continue

            # 3. APPENDIX
            if token.token_type == "APPENDIX":
                app_num = sanitize_index_label(token.index_label.replace("Phụ lục", "").strip())
                app_seg = _disambiguate(root, f"app_{app_num}")
                app_path = validate_ltree_path(f"{self.doc_prefix}.{app_seg}")
                doc_order += 1
                current_appendix = ASTNode(
                    node_type="APPENDIX",
                    index_label=token.index_label,
                    title=token.title,
                    full_path=app_path,
                    depth=7,
                    raw_text=token.content,
                    parent_path=self.doc_prefix,
                    display_order=doc_order,
                )
                root.children.append(current_appendix)
                current_chapter = None
                current_section = None
                current_article = None
                current_clause = None
                continue

            # 4. ARTICLE
            if token.token_type == "ARTICLE":
                art_num = sanitize_ltree_label(token.index_label.replace("Điều", "").strip())
                parent_node = current_section if current_section else current_chapter
                parent_p = parent_node.full_path if parent_node else self.doc_prefix
                art_path = validate_ltree_path(f"{parent_p}.a_{art_num}")
                doc_order += 1
                current_article = ASTNode(
                    node_type="ARTICLE",
                    index_label=token.index_label,
                    title=token.title,
                    full_path=art_path,
                    depth=4,
                    raw_text=token.content,
                    parent_path=parent_p,
                    display_order=doc_order,
                )
                if current_section:
                    current_section.children.append(current_article)
                elif current_chapter:
                    current_chapter.children.append(current_article)
                else:
                    root.children.append(current_article)
                current_clause = None
                continue

            # 5. CLAUSE
            if token.token_type == "CLAUSE" and current_article:
                cl_num = sanitize_ltree_label(token.index_label.replace("Khoản", "").strip())
                cl_seg = _disambiguate(current_article, f"c_{cl_num}")
                cl_path = validate_ltree_path(f"{current_article.full_path}.{cl_seg}")
                doc_order += 1
                # Preserve entire stem clause text, stripping only trailing terminal colon
                lead = re.sub(r":\s*$", "", token.content).strip()
                clause_text = f"{token.index_label}. {token.content}".strip(". ")
                current_clause = ASTNode(
                    node_type="CLAUSE",
                    index_label=token.index_label,
                    title="",
                    full_path=cl_path,
                    depth=5,
                    raw_text=clause_text,
                    lead_sentence=lead,
                    clause_kind="STANDALONE_RULE",
                    parent_path=current_article.full_path,
                    display_order=doc_order,
                )
                current_article.children.append(current_clause)
                continue

            # 6. POINT
            if token.token_type == "POINT" and (current_clause or current_article):
                pt_letter = sanitize_index_label(token.index_label.replace("Điểm", "").strip())
                parent_n = current_clause if current_clause else current_article
                assert parent_n is not None
                if parent_n.node_type == "CLAUSE":
                    parent_n.clause_kind = "CONTAINER_STEM"
                pt_seg = _disambiguate(parent_n, f"p_{pt_letter}")
                pt_path = validate_ltree_path(f"{parent_n.full_path}.{pt_seg}")
                doc_order += 1
                lead = parent_n.lead_sentence or parent_n.raw_text
                point_text = f"{token.index_label}) {token.content}".strip(") ")
                pt_node = ASTNode(
                    node_type="POINT",
                    index_label=token.index_label,
                    title="",
                    full_path=pt_path,
                    depth=6,
                    raw_text=point_text,
                    lead_sentence=lead,
                    parent_path=parent_n.full_path,
                    display_order=doc_order,
                )
                parent_n.children.append(pt_node)
                continue

            # 7. BODY_TEXT
            if token.token_type == "BODY_TEXT":
                if current_clause and current_clause.children:
                    current_clause.children[-1].raw_text += f"\n{token.content}"
                elif current_clause:
                    current_clause.raw_text += f"\n{token.content}"
                    # Update lead sentence if clause still hasn't children
                    if current_clause.clause_kind != "CONTAINER_STEM":
                        current_clause.lead_sentence = re.sub(r":\s*$", "", current_clause.raw_text).strip()
                elif current_article:
                    current_article.raw_text += f"\n{token.content}"
                elif current_appendix:
                    current_appendix.raw_text += f"\n{token.content}"
                elif current_section:
                    current_section.raw_text += f"\n{token.content}"
                elif current_chapter:
                    current_chapter.raw_text += f"\n{token.content}"

        return root
