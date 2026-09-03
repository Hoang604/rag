"""Context-Preserving Hierarchical Chunking (CPHC) Engine.

Synthesizes self-contained atomic chunks by inheriting full ancestral lineage
from Document -> Chapter -> Article -> Clause down to each individual Point.
"""

from __future__ import annotations

import datetime
import re
import uuid

from rag_eval.legal.ingestion.parser import ASTNode
from rag_eval.legal.schemas import (
    E_INVALID_DOCUMENT_HIERARCHY,
    CanonicalFullyQualifiedChunk,
    LegalDomainError,
)

# The embedding model truncates at 512 tokens, silently. A clause longer than
# that is indexed in full by the sparse half (tsvector covers the whole text)
# but its tail is invisible to semantic search -- retrievable only by someone
# who already guessed a keyword from the part they cannot see.
#
# Calibrated on this corpus against intfloat/multilingual-e5-small: the densest
# of 3,882 chunks measured 2.09 characters per token, so 1,000 characters cannot
# exceed 479 tokens and always fits. Counting characters keeps this module free
# of an ML dependency, which matters because parsing must run without one.
EMBEDDING_CHAR_BUDGET = 1_000
_PASSAGE_PREFIX_ALLOWANCE = len("passage: ")
# Statutory prose breaks at these marks. Splitting only on whitespace runs
# guarantees no token -- and so no monetary figure -- is ever cut in half.
_SENTENCE_BREAK = re.compile(r"(?<=[.;:])\s+|\n+")
_WHITESPACE_RUN = re.compile(r"\s+")
# When a lead sentence makes the synthesized prefix so long that little room is
# left, the prefix yields rather than the statute. Context is regenerable; text
# is not.
_MIN_BODY_BUDGET = 400


def _fit_prefix(prefix: str) -> str:
    """Caps the synthesized prefix so the provision always keeps room."""
    ceiling = EMBEDDING_CHAR_BUDGET - _PASSAGE_PREFIX_ALLOWANCE - _MIN_BODY_BUDGET
    if len(prefix) <= ceiling:
        return prefix
    return prefix[: ceiling - 4].rstrip() + " ...]"


def _pack(pieces: list[str], budget: int) -> list[str]:
    """Greedily groups pieces into runs no longer than `budget`."""
    parts: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current} {piece}".strip() if current else piece
        if current and len(candidate) > budget:
            parts.append(current)
            current = piece
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def split_for_embedding(body: str, budget: int) -> list[str]:
    """Splits text into windows that fit `budget` characters, never mid-token.

    Sentence boundaries are preferred; a single sentence over budget falls back
    to whitespace runs. Nothing is dropped and no word is broken, so every part
    remains a contiguous span of the source document and the ingestion
    grounding check still holds over the set.
    """
    if len(body) <= budget or budget <= 0:
        return [body]

    parts = _pack([p for p in _SENTENCE_BREAK.split(body) if p and p.strip()], budget)
    if all(len(part) <= budget for part in parts):
        return parts

    resolved: list[str] = []
    for part in parts:
        if len(part) <= budget:
            resolved.append(part)
        else:
            resolved.extend(_pack(_WHITESPACE_RUN.split(part), budget))
    return resolved


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
            appendix: str = "",
        ) -> None:
            cur_chap = (
                f"{node.index_label} - {node.title}".strip(" -")
                if node.node_type == "CHAPTER"
                else chap_title
            )
            cur_art_label = node.index_label if node.node_type == "ARTICLE" else art_label
            cur_art_title = node.title if node.node_type == "ARTICLE" else art_title
            cur_cl_label = (
                node.index_label
                if node.node_type in ("CLAUSE", "APPENDIX_ITEM")
                else cl_label
            )
            cur_appendix = (
                f"{node.index_label} - {node.title}".strip(" -")
                if node.node_type == "APPENDIX"
                else appendix
            )
            
            # Inherit lead sentence from container stem clauses
            cur_lead = (
                node.lead_sentence
                if node.node_type in ("CLAUSE", "APPENDIX_ITEM", "APPENDIX")
                and node.clause_kind == "CONTAINER_STEM"
                else lead
            )

            if not node.children and node.node_type in (
                "POINT",
                "CLAUSE",
                "ARTICLE",
                "APPENDIX",
                "APPENDIX_ITEM",
            ):
                verbatim = node.raw_text.strip()
                
                if node.node_type == "POINT":
                    prefix = synthesize_cphc_prefix(
                        doc_title=self.doc_title or self.doc_code,
                        chapter_title=cur_chap or cur_appendix,
                        article_label=cur_art_label,
                        article_title=cur_art_title,
                        clause_label=cur_cl_label,
                        lead_sentence=cur_lead,
                    )
                elif node.node_type == "CLAUSE":
                    # Standalone clause rule: omit lead_sentence to prevent redundant duplication
                    prefix = synthesize_cphc_prefix(
                        doc_title=self.doc_title or self.doc_code,
                        chapter_title=cur_chap,
                        article_label=cur_art_label,
                        article_title=cur_art_title,
                        clause_label=node.index_label,
                        lead_sentence="",
                    )
                elif node.node_type == "ARTICLE":
                    prefix = synthesize_cphc_prefix(
                        doc_title=self.doc_title or self.doc_code,
                        chapter_title=cur_chap,
                        article_label=node.index_label,
                        article_title=node.title,
                    )
                elif node.node_type == "APPENDIX_ITEM":
                    # The appendix heading is the item's only ancestor context,
                    # and it carries the classification: an item of Phụ lục B is
                    # a prohibitory sign, one of Phụ lục C a warning sign. Two
                    # items can otherwise read almost identically.
                    prefix = (
                        f"[{self.doc_title or self.doc_code}] > "
                        f"[{cur_appendix}] > [{node.index_label}]"
                    )
                else:  # APPENDIX
                    prefix = f"[{self.doc_title or self.doc_code}] > [{node.index_label}: {node.title}]".strip(": ]") + "]"

                # A long lead sentence can leave almost no room for the
                # provision itself. Where the two compete, the synthesized
                # context is what gives way: it can be regenerated from the
                # hierarchy at any time, whereas statute pushed outside the
                # window is simply unfindable by semantic search.
                prefix = _fit_prefix(prefix)
                body_budget = (
                    EMBEDDING_CHAR_BUDGET - _PASSAGE_PREFIX_ALLOWANCE - len(prefix) - 1
                )
                windows = split_for_embedding(verbatim, body_budget)

                for position, window in enumerate(windows, start=1):
                    # A single-window provision keeps its own path, so nothing
                    # about the common case changes. A split one gets sibling
                    # paths under it: every part carries the full hierarchy
                    # prefix, so each is independently interpretable, and
                    # `hierarchical_navigate` reassembles the provision from the
                    # parent address.
                    if len(windows) == 1:
                        path = node.full_path
                        label = node.index_label
                    else:
                        path = f"{node.full_path}.w_{position}"
                        label = f"{node.index_label} (phần {position}/{len(windows)})"
                    chunks.append(
                        CanonicalFullyQualifiedChunk(
                            id=uuid.uuid5(
                                uuid.NAMESPACE_DNS, f"{self.doc_code}:{path}"
                            ),
                            document_id=self.document_id,
                            path=path,
                            verbatim_text=window,
                            contextualized_text=f"{prefix}\n{window}"
                            if prefix
                            else window,
                            effective_date=self.effective_date,
                            expiration_date=self.expiration_date,
                            metadata={
                                "doc_code": self.doc_code,
                                "node_type": node.node_type,
                                "index_label": label,
                                "clause_kind": getattr(node, "clause_kind", "NONE"),
                            }
                            | (
                                {}
                                if len(windows) == 1
                                else {
                                    "window": str(position),
                                    "window_count": str(len(windows)),
                                    "provision_path": node.full_path,
                                }
                            ),
                        )
                    )

            for child in node.children:
                _traverse(
                    child,
                    cur_chap,
                    cur_art_label,
                    cur_art_title,
                    cur_cl_label,
                    cur_lead,
                    cur_appendix,
                )

        _traverse(root, "", "", "", "", "", "")
        _assert_paths_unique(chunks, self.doc_code)
        return chunks


def _assert_paths_unique(
    chunks: list[CanonicalFullyQualifiedChunk], doc_code: str
) -> None:
    """Fails the parse when two chunks claim the same ltree path.

    `chunks.path` is UNIQUE in the schema, so a collision reaching the database
    either aborts the load or overwrites a real provision -- and the overwrite
    is silent, leaving retrieval to answer with the wrong clause. Checking here
    turns that into a parse failure naming the paths, because the collision is
    a defect in label encoding rather than in the source document.
    """
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for chunk in chunks:
        previous = seen.get(chunk.path)
        if previous is not None:
            label = str(chunk.metadata.get("index_label", "?"))
            collisions.append(f"{chunk.path} ({previous!r} vs {label!r})")
        else:
            seen[chunk.path] = str(chunk.metadata.get("index_label", "?"))

    if collisions:
        preview = "; ".join(collisions[:5])
        suffix = f" (+{len(collisions) - 5} more)" if len(collisions) > 5 else ""
        raise LegalDomainError(
            error_code=E_INVALID_DOCUMENT_HIERARCHY,
            message=(
                f"{len(collisions)} chunk path collision(s) in '{doc_code}'. "
                f"Distinct provisions would overwrite each other. {preview}{suffix}"
            ),
            data={"doc_code": doc_code, "collisions": collisions[:50]},
        )
