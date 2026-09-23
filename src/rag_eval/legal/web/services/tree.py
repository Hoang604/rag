"""Document tree hierarchy builder and natural legal path sorting."""

from __future__ import annotations

import re
from typing import ClassVar

from rag_eval.legal.ingestion.staging.session import StagingDocumentSession
from rag_eval.legal.schemas import sanitize_ltree_label
from rag_eval.legal.web.schemas import (
    DocumentTreeNodeResponse,
    DocumentTreeResponse,
)

ROMAN_REGEX = re.compile(
    r"^(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx|xxi|xxii|xxiii|xxiv|xxv|xxvi|xxvii|xxviii|xxix|xxx)$",
    re.IGNORECASE,
)


def roman_to_int(s: str) -> int | None:
    """Parses lower/upper roman numeral into integer (1-30)."""
    clean = s.lower().strip()
    if not ROMAN_REGEX.match(clean):
        return None
    roman_map = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    prev = 0
    for c in reversed(clean):
        curr = roman_map[c]
        if curr >= prev:
            total += curr
        else:
            total -= curr
        prev = curr
    return total


def natural_legal_path_key(path: str) -> list[tuple[str, int, int, str]]:
    """Generates natural hierarchical sort key for Vietnamese legal LTREE paths."""
    keys: list[tuple[str, int, int, str]] = []
    for seg in path.split("."):
        if "_" not in seg:
            keys.append((seg, 0, 0, ""))
            continue
        prefix, rest = seg.split("_", 1)
        if rest.isdigit():
            keys.append((prefix, 0, int(rest), ""))
        else:
            r_int = roman_to_int(rest)
            if r_int is not None:
                keys.append((prefix, 0, r_int, ""))
            else:
                keys.append((prefix, 1, 0, rest.lower()))
    return keys


class TreeHierarchyBuilder:
    """Transforms flat list of StagingChunk models into a full nested hierarchy tree."""

    _TYPE_MAP: ClassVar[dict[str, str]] = {
        "c": "CHAPTER",
        "s": "SECTION",
        "a": "ARTICLE",
        "p": "POINT",
        "app": "APPENDIX",
    }

    @classmethod
    def _parse_segment_metadata(
        cls,
        segment: str,
        is_leaf: bool,
        parent_type: str | None = None,
        chap_titles: dict[str, str] | None = None,
        sec_titles: dict[str, str] | None = None,
        art_titles: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Infers (node_type, human_readable_label) from an LTREE segment string with rich title."""
        if "_" not in segment:
            return "DOCUMENT", segment

        prefix, rest = segment.split("_", 1)
        prefix_lower = prefix.lower()
        rest_key = rest.lower()

        if prefix_lower == "c":
            if parent_type in ("ARTICLE", "CLAUSE"):
                return "CLAUSE", f"Khoản {rest.upper()}"
            c_title = (chap_titles or {}).get(rest_key)
            if c_title:
                return "CHAPTER", f"Chương {rest.upper()}: {c_title}"
            return "CHAPTER", f"Chương {rest.upper()}"

        if prefix_lower == "s":
            s_title = (sec_titles or {}).get(rest_key)
            if s_title:
                return "SECTION", f"Mục {rest.upper()}: {s_title}"
            return "SECTION", f"Mục {rest.upper()}"

        if prefix_lower == "a":
            a_title = (art_titles or {}).get(rest_key)
            if a_title:
                return "ARTICLE", f"Điều {rest.upper()}: {a_title}"
            return "ARTICLE", f"Điều {rest.upper()}"

        if prefix_lower == "p":
            return "POINT", f"Điểm {rest}"

        if prefix_lower == "app":
            return "APPENDIX", f"Phụ lục {rest.upper()}"

        return "SECTION", segment

    def build_tree(self, session: StagingDocumentSession) -> DocumentTreeResponse:
        """Constructs nested tree hierarchy with root node and complete children branches."""
        sanitized_root = sanitize_ltree_label(session.doc_code)

        chap_titles: dict[str, str] = {}
        sec_titles: dict[str, str] = {}
        art_titles: dict[str, str] = {}

        for chunk in session.chunks:
            if chunk.metadata:
                if chunk.metadata.get("chapter_title"):
                    val = str(chunk.metadata["chapter_title"])
                    if " - " in val:
                        c_idx, c_t = val.split(" - ", 1)
                        c_k = sanitize_ltree_label(c_idx.replace("Chương", "").strip().lower())
                        if c_t.strip():
                            chap_titles[c_k] = c_t.strip()
                if chunk.metadata.get("article_title"):
                    val = str(chunk.metadata["article_title"])
                    for seg in chunk.path.split("."):
                        if seg.startswith("a_"):
                            a_k = seg[2:].lower()
                            if val.strip():
                                art_titles[a_k] = val.strip()

            if chunk.contextualized_text:
                m_chap = re.search(r"\[Chương\s+([A-Za-z0-9_]+)\s*[-:]\s*([^\]]+)\]", chunk.contextualized_text)
                if m_chap:
                    c_key = sanitize_ltree_label(m_chap.group(1).lower())
                    c_t = m_chap.group(2).strip()
                    if c_t and c_key not in chap_titles:
                        chap_titles[c_key] = c_t

                m_sec = re.search(r"\[Mục\s+([A-Za-z0-9_]+)\s*[-:]\s*([^\]]+)\]", chunk.contextualized_text)
                if m_sec:
                    s_key = sanitize_ltree_label(m_sec.group(1).lower())
                    s_t = m_sec.group(2).strip()
                    if s_t and s_key not in sec_titles:
                        sec_titles[s_key] = s_t

                m_art = re.search(r"\[Điều\s+([A-Za-z0-9_]+)\s*[-:]\s*([^\]]+)\]", chunk.contextualized_text)
                if m_art:
                    a_key = sanitize_ltree_label(m_art.group(1).lower())
                    a_t = m_art.group(2).strip()
                    if a_t and a_key not in art_titles:
                        art_titles[a_key] = a_t

        if session.raw_text:
            try:
                from rag_eval.legal.ingestion.lexer import LegalLexer
                lexer = LegalLexer(doc_code=session.doc_code)
                for tok in lexer.tokenize(session.raw_text):
                    if tok.token_type == "CHAPTER" and tok.title:
                        c_key = sanitize_ltree_label(tok.index_label.replace("Chương", "").strip().lower())
                        if tok.title.strip() and c_key not in chap_titles:
                            chap_titles[c_key] = tok.title.strip()
                    elif tok.token_type == "SECTION" and tok.title:
                        s_key = sanitize_ltree_label(tok.index_label.replace("Mục", "").strip().lower())
                        if tok.title.strip() and s_key not in sec_titles:
                            sec_titles[s_key] = tok.title.strip()
                    elif tok.token_type == "ARTICLE" and tok.title:
                        a_key = sanitize_ltree_label(tok.index_label.replace("Điều", "").strip().lower())
                        if tok.title.strip() and a_key not in art_titles:
                            art_titles[a_key] = tok.title.strip()
            except (RuntimeError, ValueError, TypeError, OSError):
                pass

        root_node = DocumentTreeNodeResponse(
            path=sanitized_root,
            label=session.title or session.doc_code,
            node_type="DOCUMENT",
            verbatim_text="",
            contextualized_text=f"[{session.title or session.doc_code}]",
            lead_sentence="",
            metadata=session.doc_metadata,
            effective_date=session.effective_date,
            expiration_date=session.expiration_date,
            children=[],
        )

        node_index: dict[str, DocumentTreeNodeResponse] = {sanitized_root: root_node}
        sorted_chunks = sorted(session.chunks, key=lambda c: natural_legal_path_key(c.path))

        for chunk in sorted_chunks:
            segments = chunk.path.split(".")
            current_path_accum = ""
            current_parent_type = "DOCUMENT"

            for idx, seg in enumerate(segments):
                current_path_accum = (
                    seg if not current_path_accum else f"{current_path_accum}.{seg}"
                )
                is_leaf = idx == len(segments) - 1

                if current_path_accum not in node_index:
                    node_type, label = self._parse_segment_metadata(
                        seg,
                        is_leaf=is_leaf,
                        parent_type=current_parent_type,
                        chap_titles=chap_titles,
                        sec_titles=sec_titles,
                        art_titles=art_titles,
                    )
                    parent_path = (
                        current_path_accum.rsplit(".", 1)[0]
                        if "." in current_path_accum
                        else sanitized_root
                    )

                    new_node = DocumentTreeNodeResponse(
                        path=current_path_accum,
                        label=label,
                        node_type=node_type,
                        verbatim_text=chunk.verbatim_text if is_leaf else "",
                        contextualized_text=chunk.contextualized_text if is_leaf else "",
                        lead_sentence=chunk.lead_sentence if is_leaf else "",
                        start_line=chunk.start_line if is_leaf else 1,
                        end_line=chunk.end_line if is_leaf else 1,
                        metadata=chunk.metadata if is_leaf else {},
                        effective_date=chunk.effective_date,
                        expiration_date=chunk.expiration_date,
                        review_status=str(
                            chunk.review_status.value
                            if hasattr(chunk.review_status, "value")
                            else chunk.review_status
                        )
                        if is_leaf
                        else "PENDING",
                        children=[],
                    )

                    node_index[current_path_accum] = new_node
                    parent_node = node_index.get(parent_path, root_node)
                    parent_node.children.append(new_node)
                    current_parent_type = new_node.node_type
                else:
                    existing = node_index[current_path_accum]
                    if is_leaf:
                        existing.verbatim_text = chunk.verbatim_text
                        existing.contextualized_text = chunk.contextualized_text
                        existing.lead_sentence = chunk.lead_sentence
                        existing.start_line = chunk.start_line
                        existing.end_line = chunk.end_line
                        existing.metadata = chunk.metadata
                        existing.effective_date = chunk.effective_date
                        existing.expiration_date = chunk.expiration_date
                        existing.review_status = str(
                            chunk.review_status.value
                            if hasattr(chunk.review_status, "value")
                            else chunk.review_status
                        )
                    current_parent_type = existing.node_type

        def _sort_and_propagate_recursively(node: DocumentTreeNodeResponse) -> None:
            node.children.sort(key=lambda c: natural_legal_path_key(c.path))
            for child in node.children:
                _sort_and_propagate_recursively(child)
            if node.children:
                if all(child.review_status == "FINALIZED" for child in node.children):
                    node.review_status = "FINALIZED"
                else:
                    node.review_status = "PENDING"

        _sort_and_propagate_recursively(root_node)

        total_finalized = sum(
            1
            for c in session.chunks
            if (
                c.review_status == "FINALIZED"
                or (hasattr(c.review_status, "value") and c.review_status.value == "FINALIZED")
            )
        )
        total_pending = len(session.chunks) - total_finalized
        progress_pct = (
            round((total_finalized / len(session.chunks) * 100.0), 1)
            if session.chunks
            else 0.0
        )

        return DocumentTreeResponse(
            doc_code=session.doc_code,
            title=session.title,
            total_nodes=len(node_index),
            total_finalized=total_finalized,
            total_pending=total_pending,
            progress_percent=progress_pct,
            root=root_node,
        )
