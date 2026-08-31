"""Abstract Syntax Tree (AST) parser for Vietnamese statutory legal texts.

Parses arbitrary legal documents into a clean hierarchical tree of ASTNode elements
with deterministic ltree paths and automatic lead sentence propagation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rag_eval.legal.ingestion.grammar import (
    ARTICLE_PATTERN,
    CHAPTER_PATTERN,
    CLAUSE_PATTERN,
    POINT_PATTERN,
)
from rag_eval.legal.schemas import sanitize_ltree_label, validate_ltree_path


@dataclass
class ASTNode:
    """Represents a hierarchical node in the legal syntax tree."""

    node_type: str  # DOCUMENT | CHAPTER | SECTION | ARTICLE | CLAUSE | POINT | APPENDIX
    index_label: str  # e.g., "Điều 5", "Khoản 3", "Điểm a"
    title: str  # Section/Article title or heading
    full_path: str  # ltree path e.g. "doc_100_2019.c_ii.a5.c3.p_a"
    depth: int  # 1=Doc, 2=Chapter, 3=Section, 4=Article, 5=Clause, 6=Point
    raw_text: str  # Raw text content of this division
    lead_sentence: str = ""  # Inherited lead sentence (for clauses/points)
    parent_path: str | None = None
    display_order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[ASTNode] = field(default_factory=list)


class LegalASTParser:
    """Recursively parses raw statutory text into a hierarchy of ASTNode objects."""

    def __init__(self, doc_code: str) -> None:
        self.doc_code = doc_code
        self.doc_prefix = sanitize_ltree_label(doc_code)

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

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return root

        current_chapter: ASTNode | None = None
        current_article: ASTNode | None = None
        current_clause: ASTNode | None = None

        doc_order = 0

        for line in lines:
            # Check Chapter
            chap_match = CHAPTER_PATTERN.match(line)
            if chap_match:
                chap_num = chap_match.group(1).lower()
                chap_title = (chap_match.group(2) or "").strip()
                chap_path = validate_ltree_path(f"{self.doc_prefix}.c_{chap_num}")
                doc_order += 1
                current_chapter = ASTNode(
                    node_type="CHAPTER",
                    index_label=f"Chương {chap_num.upper()}",
                    title=chap_title,
                    full_path=chap_path,
                    depth=2,
                    raw_text=line,
                    parent_path=self.doc_prefix,
                    display_order=doc_order,
                )
                root.children.append(current_chapter)
                current_article = None
                current_clause = None
                continue

            # Check Article
            art_match = ARTICLE_PATTERN.match(line)
            if art_match:
                art_num = art_match.group(1).lower()
                art_title = (art_match.group(2) or "").strip()
                parent_p = current_chapter.full_path if current_chapter else self.doc_prefix
                art_path = validate_ltree_path(f"{parent_p}.a_{art_num}")
                doc_order += 1
                current_article = ASTNode(
                    node_type="ARTICLE",
                    index_label=f"Điều {art_num}",
                    title=art_title,
                    full_path=art_path,
                    depth=4,
                    raw_text=line,
                    parent_path=parent_p,
                    display_order=doc_order,
                )
                if current_chapter:
                    current_chapter.children.append(current_article)
                else:
                    root.children.append(current_article)
                current_clause = None
                continue

            # Check Clause
            cl_match = CLAUSE_PATTERN.match(line)
            if cl_match and current_article:
                cl_num = cl_match.group(1)
                cl_content = cl_match.group(2).strip()
                cl_path = validate_ltree_path(f"{current_article.full_path}.c_{cl_num}")
                doc_order += 1

                lead = cl_content.split(":")[0] if ":" in cl_content else cl_content
                current_clause = ASTNode(
                    node_type="CLAUSE",
                    index_label=f"Khoản {cl_num}",
                    title="",
                    full_path=cl_path,
                    depth=5,
                    raw_text=line,
                    lead_sentence=lead,
                    parent_path=current_article.full_path,
                    display_order=doc_order,
                )
                current_article.children.append(current_clause)
                continue

            # Check Point
            pt_match = POINT_PATTERN.match(line)
            if pt_match and (current_clause or current_article):
                pt_letter = pt_match.group(1).lower()
                parent_node = current_clause if current_clause else current_article
                assert parent_node is not None
                pt_path = validate_ltree_path(f"{parent_node.full_path}.p_{pt_letter}")
                doc_order += 1
                lead = parent_node.lead_sentence or parent_node.raw_text
                pt_node = ASTNode(
                    node_type="POINT",
                    index_label=f"Điểm {pt_letter}",
                    title="",
                    full_path=pt_path,
                    depth=6,
                    raw_text=line,
                    lead_sentence=lead,
                    parent_path=parent_node.full_path,
                    display_order=doc_order,
                )
                parent_node.children.append(pt_node)
                continue

            # Append raw text to current context
            if current_clause and current_clause.children:
                current_clause.children[-1].raw_text += f"\n{line}"
            elif current_clause:
                current_clause.raw_text += f"\n{line}"
            elif current_article:
                current_article.raw_text += f"\n{line}"

        return root
