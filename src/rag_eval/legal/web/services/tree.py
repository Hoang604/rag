from __future__ import annotations

from typing import ClassVar

from rag_eval.legal.ingestion.staging.session import StagingDocumentSession
from rag_eval.legal.schemas.api import (
    DocumentTreeResponse,
)
from rag_eval.legal.schemas.domain import (
    ChunkReviewStatus,
    TreeNode,
)
from rag_eval.legal.text import (
    natural_legal_path_key,
    sanitize_ltree_label,
)


class TreeHierarchyBuilder:
    """Transforms flat list of StatutoryChunk models into a full nested hierarchy tree."""

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
        current_path: str,
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
            # Lookup section title by full path prefix (e.g. doc.c_i.s_1 or c_i.s_1)
            s_title = (sec_titles or {}).get(current_path)
            if not s_title:
                # Fallback to suffix key if exact path not matched
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
            meta = chunk.metadata
            if not meta:
                continue

            if meta.chapter_title:
                val = str(meta.chapter_title)
                if " - " in val:
                    c_idx, c_t = val.split(" - ", 1)
                    c_k = sanitize_ltree_label(c_idx.replace("Chương", "").strip().lower())
                    if c_t.strip():
                        chap_titles[c_k] = c_t.strip()

            if meta.section_title:
                val = str(meta.section_title)
                s_title_text = val.split(" - ", 1)[1].strip() if " - " in val else val.strip()
                # Find full section path prefix (e.g. sanitized_root.c_i.s_1)
                segs = chunk.path.split(".")
                sec_path_parts: list[str] = []
                for s in segs:
                    sec_path_parts.append(s)
                    if s.lower().startswith("s_"):
                        break
                if sec_path_parts and any(p.lower().startswith("s_") for p in sec_path_parts):
                    sec_full_key = ".".join(sec_path_parts)
                    sec_titles[sec_full_key] = s_title_text

            if meta.article_title:
                val = str(meta.article_title)
                for seg in chunk.path.split("."):
                    if seg.startswith("a_"):
                        a_k = seg[2:].lower()
                        if val.strip():
                            art_titles[a_k] = val.strip()

        root_node = TreeNode(
            path=sanitized_root,
            label=session.title or session.doc_code,
            node_type="DOCUMENT",
            verbatim_text="",
            contextualized_text=f"[{session.title or session.doc_code}]",
            metadata=session.doc_metadata,
            effective_date=session.effective_date,
            expiration_date=session.expiration_date,
            children=[],
        )

        node_index: dict[str, TreeNode] = {sanitized_root: root_node}
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
                        current_path=current_path_accum,
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

                    new_node = TreeNode(
                        path=current_path_accum,
                        label=label,
                        node_type=node_type,
                        verbatim_text=chunk.verbatim_text if is_leaf else "",
                        contextualized_text=chunk.contextualized_text if is_leaf else "",
                        start_line=chunk.start_line if is_leaf else 1,
                        end_line=chunk.end_line if is_leaf else 1,
                        metadata=chunk.metadata.model_dump() if is_leaf else {},
                        effective_date=chunk.effective_date,
                        expiration_date=chunk.expiration_date,
                        review_status=chunk.review_status.value if is_leaf else "PENDING",
                        context_type=chunk.context_type.value if (is_leaf and chunk.context_type) else None,
                        justification=chunk.justification if is_leaf else None,
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
                        existing.start_line = chunk.start_line
                        existing.end_line = chunk.end_line
                        existing.metadata = chunk.metadata.model_dump()
                        existing.effective_date = chunk.effective_date
                        existing.expiration_date = chunk.expiration_date
                        existing.review_status = chunk.review_status.value
                        existing.context_type = chunk.context_type.value if chunk.context_type else None
                        existing.justification = chunk.justification
                    current_parent_type = existing.node_type

        def _sort_and_propagate_recursively(node: TreeNode) -> None:
            node.children.sort(key=lambda c: natural_legal_path_key(c.path))
            for child in node.children:
                _sort_and_propagate_recursively(child)
            if node.children:
                if all(child.review_status == "REVIEWED" for child in node.children):
                    node.review_status = "REVIEWED"
                else:
                    node.review_status = "PENDING"

        _sort_and_propagate_recursively(root_node)

        total_finalized = sum(
            1
            for c in session.chunks
            if c.review_status == ChunkReviewStatus.REVIEWED
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

