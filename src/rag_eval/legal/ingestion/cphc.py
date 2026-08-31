"""Context-Preserving Hierarchical Chunking (CPHC) Engine.

Synthesizes self-contained atomic chunks by inheriting full ancestral lineage
from Document -> Chapter -> Article -> Clause down to each individual Point.
"""

from __future__ import annotations

import datetime
import uuid

from rag_eval.legal.ingestion.parser import ASTNode
from rag_eval.legal.schemas import CanonicalFullyQualifiedChunk


def synthesize_cphc_prefix(
    doc_title: str,
    chapter_title: str = "",
    article_label: str = "",
    article_title: str = "",
    clause_label: str = "",
    lead_sentence: str = "",
) -> str:
    """Synthesizes a standardized hierarchical context prefix for embedding and LLM comprehension."""
    parts: list[str] = [f"[{doc_title.strip()}]"]
    if chapter_title.strip():
        parts.append(f"[{chapter_title.strip()}]")
    if article_label.strip() or article_title.strip():
        art_str = f"{article_label}: {article_title}".strip(": ")
        parts.append(f"[{art_str}]")
    if clause_label.strip() or lead_sentence.strip():
        cl_str = f"{clause_label}: {lead_sentence}".strip(": ")
        parts.append(f"[{cl_str}]")
    return " > ".join(parts)


class CPHCEngine:
    """Transforms an AST hierarchy into a flat list of CanonicalFullyQualifiedChunks."""

    def __init__(
        self,
        document_id: uuid.UUID,
        doc_code: str,
        doc_title: str,
        effective_date: datetime.date,
        expiration_date: datetime.date | None = None,
    ) -> None:
        self.document_id = document_id
        self.doc_code = doc_code
        self.doc_title = doc_title
        self.effective_date = effective_date
        self.expiration_date = expiration_date

    def chunk_ast(self, root: ASTNode) -> list[CanonicalFullyQualifiedChunk]:
        """Flattens the AST into atomic leaf chunks with full context lineage."""
        chunks: list[CanonicalFullyQualifiedChunk] = []

        def _traverse(
            node: ASTNode,
            chap_title: str,
            art_label: str,
            art_title: str,
            cl_label: str,
            lead: str,
        ) -> None:
            cur_chap = (
                f"{node.index_label} - {node.title}".strip(" -")
                if node.node_type == "CHAPTER"
                else chap_title
            )
            cur_art_label = node.index_label if node.node_type == "ARTICLE" else art_label
            cur_art_title = node.title if node.node_type == "ARTICLE" else art_title
            cur_cl_label = node.index_label if node.node_type == "CLAUSE" else cl_label
            cur_lead = node.lead_sentence if node.lead_sentence else lead

            if not node.children and node.node_type in ("POINT", "CLAUSE", "ARTICLE"):
                prefix = synthesize_cphc_prefix(
                    doc_title=self.doc_title or self.doc_code,
                    chapter_title=cur_chap,
                    article_label=cur_art_label,
                    article_title=cur_art_title,
                    clause_label=cur_cl_label if node.node_type == "POINT" else "",
                    lead_sentence=cur_lead,
                )
                verbatim = node.raw_text.strip()
                contextualized = f"{prefix}\n{verbatim}" if prefix else verbatim

                chunk_id = uuid.uuid5(
                    uuid.NAMESPACE_DNS, f"{self.doc_code}:{node.full_path}"
                )
                chunk = CanonicalFullyQualifiedChunk(
                    id=chunk_id,
                    document_id=self.document_id,
                    path=node.full_path,
                    verbatim_text=verbatim,
                    contextualized_text=contextualized,
                    effective_date=self.effective_date,
                    expiration_date=self.expiration_date,
                    metadata={
                        "doc_code": self.doc_code,
                        "node_type": node.node_type,
                        "index_label": node.index_label,
                    },
                )
                chunks.append(chunk)

            for child in node.children:
                _traverse(
                    child,
                    cur_chap,
                    cur_art_label,
                    cur_art_title,
                    cur_cl_label,
                    cur_lead,
                )

        _traverse(root, "", "", "", "", "")
        return chunks
