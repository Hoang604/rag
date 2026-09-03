"""Service layer for Human Promotion Engine, Pre-Flight Integrity Verification,

Document Tree Hierarchy Construction, and Version Mutation Diff Calculation.
"""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

import asyncpg

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingDocumentSession,
    StagingManager,
    StagingMutationRecord,
    StagingStatus,
)
from rag_eval.legal.schemas import (
    E_CORPUS_INTEGRITY_VIOLATION,
    LTREE_PATH_REGEX,
    CanonicalFullyQualifiedChunk,
    DocumentRecord,
    GraphEdgeRecord,
    LegalDomainError,
    get_vietnam_now,
    sanitize_ltree_label,
)
from rag_eval.legal.web.schemas import (
    AuditDiffEntry,
    DocumentTreeNodeResponse,
    DocumentTreeResponse,
    PreFlightValidationResponse,
    PromotionResultResponse,
    SessionDiffResponse,
    ValidationIssue,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# 1. Pre-Flight Integrity Validator
# ------------------------------------------------------------------------------
class PreFlightValidator:
    """Runs automated integrity checks against a StagingDocumentSession before promotion."""

    TOTAL_CHECKS = 7

    def validate(self, session: StagingDocumentSession) -> PreFlightValidationResponse:
        """Executes all 7 integrity validation rules against the session."""
        issues: list[ValidationIssue] = []
        summary: dict[str, Any] = {}

        # 1. LTREE Path Syntax Check
        invalid_path_count = 0
        for chunk in session.chunks:
            if not chunk.path or not LTREE_PATH_REGEX.match(chunk.path.strip()):
                invalid_path_count += 1
                issues.append(
                    ValidationIssue(
                        rule="LTREE_PATH_SYNTAX",
                        severity="ERROR",
                        path=chunk.path,
                        message=f"Chunk path '{chunk.path}' violates LTREE dot-syntax regex.",
                        blocking=True,
                    )
                )
        summary["ltree_path_syntax"] = {
            "passed": invalid_path_count == 0,
            "violations": invalid_path_count,
        }

        # 2. Root Code Alignment Check
        sanitized_doc_code = sanitize_ltree_label(session.doc_code)
        mismatched_root_count = 0
        for chunk in session.chunks:
            prefix = chunk.path.split(".")[0] if "." in chunk.path else chunk.path
            if prefix != sanitized_doc_code and not prefix.startswith(sanitized_doc_code):
                mismatched_root_count += 1
                issues.append(
                    ValidationIssue(
                        rule="ROOT_CODE_ALIGNMENT",
                        severity="ERROR",
                        path=chunk.path,
                        message=(
                            f"Chunk root prefix '{prefix}' does not align with sanitized "
                            f"document code '{sanitized_doc_code}'."
                        ),
                        blocking=True,
                    )
                )
        summary["root_code_alignment"] = {
            "passed": mismatched_root_count == 0,
            "violations": mismatched_root_count,
        }

        # 3. Parent-Child Continuity & Structural Integrity
        continuity_violations = 0
        staged_paths = {c.path for c in session.chunks}
        if not session.chunks:
            continuity_violations += 1
            issues.append(
                ValidationIssue(
                    rule="PARENT_CHILD_CONTINUITY",
                    severity="ERROR",
                    path=None,
                    message="Staging session contains zero chunks.",
                    blocking=True,
                )
            )

        for chunk in session.chunks:
            segments = chunk.path.split(".")
            # Verify segments follow standard legal division prefixes
            for seg in segments[1:]:
                if not re.match(r"^(?:c|s|a|p|app|doc)_[a-zA-Z0-9_]+$", seg):
                    continuity_violations += 1
                    issues.append(
                        ValidationIssue(
                            rule="PARENT_CHILD_CONTINUITY",
                            severity="WARNING",
                            path=chunk.path,
                            message=f"Path segment '{seg}' in '{chunk.path}' has non-standard prefix format.",
                            blocking=False,
                        )
                    )

        summary["parent_child_continuity"] = {
            "passed": continuity_violations == 0,
            "violations": continuity_violations,
        }

        # 4. Statutory Dates Validation
        date_violations = 0
        if session.effective_date is None:
            date_violations += 1
            issues.append(
                ValidationIssue(
                    rule="STATUTORY_DATES",
                    severity="ERROR",
                    path=None,
                    message="Document effective_date cannot be null.",
                    blocking=True,
                )
            )
        if (
            session.effective_date is not None
            and session.expiration_date is not None
            and session.expiration_date < session.effective_date
        ):
            date_violations += 1
            issues.append(
                ValidationIssue(
                    rule="STATUTORY_DATES",
                    severity="ERROR",
                    path=None,
                    message=(
                        f"Document expiration_date ({session.expiration_date}) cannot be earlier "
                        f"than effective_date ({session.effective_date})."
                    ),
                    blocking=True,
                )
            )

        for chunk in session.chunks:
            if chunk.effective_date is None:
                date_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="STATUTORY_DATES",
                        severity="ERROR",
                        path=chunk.path,
                        message=f"Chunk '{chunk.path}' has null effective_date.",
                        blocking=True,
                    )
                )
            if (
                chunk.effective_date is not None
                and chunk.expiration_date is not None
                and chunk.expiration_date < chunk.effective_date
            ):
                date_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="STATUTORY_DATES",
                        severity="ERROR",
                        path=chunk.path,
                        message=(
                            f"Chunk '{chunk.path}' expiration_date ({chunk.expiration_date}) is earlier "
                            f"than effective_date ({chunk.effective_date})."
                        ),
                        blocking=True,
                    )
                )

        summary["statutory_dates"] = {
            "passed": date_violations == 0,
            "violations": date_violations,
        }

        # 5. Content Grounding (Verbatim & Contextualized Text Non-Empty)
        empty_text_violations = 0
        for chunk in session.chunks:
            if not chunk.verbatim_text or not chunk.verbatim_text.strip():
                empty_text_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="CONTENT_GROUNDING",
                        severity="ERROR",
                        path=chunk.path,
                        message=f"Chunk '{chunk.path}' has empty verbatim_text.",
                        blocking=True,
                    )
                )
            if not chunk.contextualized_text or not chunk.contextualized_text.strip():
                empty_text_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="CONTENT_GROUNDING",
                        severity="ERROR",
                        path=chunk.path,
                        message=f"Chunk '{chunk.path}' has empty contextualized_text.",
                        blocking=True,
                    )
                )

        summary["content_grounding"] = {
            "passed": empty_text_violations == 0,
            "violations": empty_text_violations,
        }

        # 6. Graph Edge Integrity (Source grounding & Target validity)
        edge_violations = 0
        for edge in session.edges:
            if edge.source_path not in staged_paths:
                edge_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="GRAPH_EDGE_INTEGRITY",
                        severity="ERROR",
                        path=edge.source_path,
                        message=(
                            f"Graph edge source_path '{edge.source_path}' does not exist "
                            f"in staged chunks for this document."
                        ),
                        blocking=True,
                    )
                )
            # Target must exist in staged chunks OR have a target_external_ref OR have a cross-doc path
            if not edge.target_path and not edge.target_external_ref:
                edge_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="GRAPH_EDGE_INTEGRITY",
                        severity="ERROR",
                        path=edge.source_path,
                        message=(
                            f"Graph edge from source '{edge.source_path}' must specify either "
                            f"a target_path or target_external_ref."
                        ),
                        blocking=True,
                    )
                )

        summary["graph_edge_integrity"] = {
            "passed": edge_violations == 0,
            "violations": edge_violations,
        }

        # 7. Duplicate Path Collision Check
        seen_paths: set[str] = set()
        duplicate_paths: set[str] = set()
        for chunk in session.chunks:
            if chunk.path in seen_paths:
                duplicate_paths.add(chunk.path)
            seen_paths.add(chunk.path)

        if duplicate_paths:
            for dp in duplicate_paths:
                issues.append(
                    ValidationIssue(
                        rule="DUPLICATE_PATH_COLLISION",
                        severity="ERROR",
                        path=dp,
                        message=f"Duplicate chunk path collision detected: '{dp}'.",
                        blocking=True,
                    )
                )
        summary["duplicate_path_collision"] = {
            "passed": len(duplicate_paths) == 0,
            "violations": len(duplicate_paths),
        }

        blocking_issues = [i for i in issues if i.blocking]
        passed = len(blocking_issues) == 0
        status = "PASSED" if passed else "FAILED"

        return PreFlightValidationResponse(
            status=status,
            passed=passed,
            total_checks=self.TOTAL_CHECKS,
            issues=issues,
            summary=summary,
        )


# ------------------------------------------------------------------------------
# 2. Document Tree Hierarchy Builder & Natural Legal Path Sorting
# ------------------------------------------------------------------------------
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
    """Generates natural hierarchical sort key for Vietnamese legal LTREE paths.
    
    Ensures that numeric and roman segments sort in ascending human order:
    e.g. c_1 < c_2 < ... < c_9 < c_10 < c_11, and c_i < c_ii < c_ix < c_x.
    """
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
            # If under an article, 'c' is Clause (Khoản), otherwise Chapter (Chương)
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

        # 1. Dynamically extract chapter, section, and article titles from chunks
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

        # If raw_text is present, also extract via LegalLexer tokens to catch chapters without chunks
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

        # Index intermediate and leaf nodes by full path
        node_index: dict[str, DocumentTreeNodeResponse] = {sanitized_root: root_node}

        # Sort chunks with natural sort key for ascending top-down insertion
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
                        metadata=chunk.metadata if is_leaf else {},
                        effective_date=chunk.effective_date,
                        expiration_date=chunk.expiration_date,
                        children=[],
                    )

                    node_index[current_path_accum] = new_node

                    # Attach to parent
                    parent_node = node_index.get(parent_path, root_node)
                    parent_node.children.append(new_node)
                    current_parent_type = new_node.node_type
                else:
                    existing = node_index[current_path_accum]
                    if is_leaf:
                        existing.verbatim_text = chunk.verbatim_text
                        existing.contextualized_text = chunk.contextualized_text
                        existing.lead_sentence = chunk.lead_sentence
                        existing.metadata = chunk.metadata
                        existing.effective_date = chunk.effective_date
                        existing.expiration_date = chunk.expiration_date
                    current_parent_type = existing.node_type

        # Recursively ensure all children nodes are strictly sorted in natural ascending order
        def _sort_children_recursively(node: DocumentTreeNodeResponse) -> None:
            node.children.sort(key=lambda c: natural_legal_path_key(c.path))
            for child in node.children:
                _sort_children_recursively(child)

        _sort_children_recursively(root_node)

        return DocumentTreeResponse(
            doc_code=session.doc_code,
            title=session.title,
            total_nodes=len(node_index),
            root=root_node,
        )


# ------------------------------------------------------------------------------
# 3. Version Mutation Diff Calculator
# ------------------------------------------------------------------------------
class DiffCalculator:
    """Calculates 4-stage version mutation differences between initial AST baseline and current state."""

    def compute_diff(self, session: StagingDocumentSession) -> SessionDiffResponse:
        """Computes added, modified, deleted chunks and detailed diff entries."""
        initial_map: dict[str, dict[str, Any]] = {}
        if session.raw_ast_snapshot:
            for item in session.raw_ast_snapshot:
                if isinstance(item, dict) and "path" in item:
                    initial_map[item["path"]] = item

        current_map: dict[str, StagingChunk] = {c.path: c for c in session.chunks}

        added_chunks: list[StagingChunk] = []
        deleted_chunks: list[dict[str, Any]] = []
        modified_chunks: list[dict[str, Any]] = []
        diff_entries: list[AuditDiffEntry] = []

        # Find added chunks
        for path, chunk in current_map.items():
            if path not in initial_map:
                added_chunks.append(chunk)
                diff_entries.append(
                    AuditDiffEntry(
                        path=path,
                        change_type="ADDED",
                        field_name=None,
                        old_value=None,
                        new_value=chunk.model_dump(mode="json"),
                        description=f"Chunk '{path}' was added after initial AST parse.",
                    )
                )

        # Find deleted chunks
        for path, raw_item in initial_map.items():
            if path not in current_map:
                deleted_chunks.append(raw_item)
                diff_entries.append(
                    AuditDiffEntry(
                        path=path,
                        change_type="DELETED",
                        field_name=None,
                        old_value=raw_item,
                        new_value=None,
                        description=f"Chunk '{path}' was deleted from staging session.",
                    )
                )

        # Find modified chunks
        for path, chunk in current_map.items():
            if path in initial_map:
                init_item = initial_map[path]
                modified_fields: list[str] = []

                if chunk.verbatim_text != init_item.get("verbatim_text"):
                    modified_fields.append("verbatim_text")
                    diff_entries.append(
                        AuditDiffEntry(
                            path=path,
                            change_type="MODIFIED",
                            field_name="verbatim_text",
                            old_value=init_item.get("verbatim_text"),
                            new_value=chunk.verbatim_text,
                            description=f"Verbatim text updated on '{path}'.",
                        )
                    )

                if chunk.contextualized_text != init_item.get("contextualized_text"):
                    modified_fields.append("contextualized_text")
                    diff_entries.append(
                        AuditDiffEntry(
                            path=path,
                            change_type="MODIFIED",
                            field_name="contextualized_text",
                            old_value=init_item.get("contextualized_text"),
                            new_value=chunk.contextualized_text,
                            description=f"Contextualized text updated on '{path}'.",
                        )
                    )

                if chunk.metadata != init_item.get("metadata", {}):
                    modified_fields.append("metadata")
                    diff_entries.append(
                        AuditDiffEntry(
                            path=path,
                            change_type="MODIFIED",
                            field_name="metadata",
                            old_value=init_item.get("metadata"),
                            new_value=chunk.metadata,
                            description=f"Metadata payload updated on '{path}'.",
                        )
                    )

                if modified_fields:
                    modified_chunks.append({
                        "path": path,
                        "modified_fields": modified_fields,
                        "current": chunk.model_dump(mode="json"),
                        "baseline": init_item,
                    })

        # Relational Edge diffs
        edge_diffs: list[dict[str, Any]] = [e.model_dump(mode="json") for e in session.edges]

        return SessionDiffResponse(
            doc_code=session.doc_code,
            total_changes=len(diff_entries),
            added_chunks=added_chunks,
            modified_chunks=modified_chunks,
            deleted_chunks=deleted_chunks,
            edge_diffs=edge_diffs,
            diff_entries=diff_entries,
        )


# ------------------------------------------------------------------------------
# 4. Human Promotion Engine
# ------------------------------------------------------------------------------
class HumanPromotionEngine:
    """Executes atomic promotion of approved staging sessions into PostgreSQL production tables."""

    def __init__(
        self,
        staging_manager: StagingManager | None = None,
        validator: PreFlightValidator | None = None,
    ) -> None:
        self.staging_manager = staging_manager or StagingManager()
        self.validator = validator or PreFlightValidator()

    async def promote_session(
        self,
        doc_code: str,
        reviewer_notes: str | None = None,
        compute_embeddings: bool = True,
        pool: asyncpg.Pool | None = None,
    ) -> PromotionResultResponse:
        """Validates and atomically promotes a staging session into PostgreSQL."""
        session = self.staging_manager.load_session(doc_code)

        # 1. Run Pre-Flight Integrity Verification
        validation = self.validator.validate(session)
        if not validation.passed:
            violation_msgs = [f"[{i.rule}] {i.message}" for i in validation.issues if i.blocking]
            error_details = "; ".join(violation_msgs)
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Pre-flight validation failed with {len(violation_msgs)} blocking issue(s): {error_details}",
                data={"issues": [i.model_dump() for i in validation.issues]},
            )

        # 2. Acquire PostgreSQL Connection Pool
        target_pool = pool if pool is not None else await get_db_pool()
        loader = PostgresBulkLoader(pool=target_pool, compute_embeddings=compute_embeddings)

        # 3. Create DocumentRecord & Persist
        doc_record = DocumentRecord(
            doc_code=session.doc_code,
            title=session.title,
            effective_date=session.effective_date,
            expiration_date=session.expiration_date,
            metadata=session.doc_metadata,
        )
        doc_id = await loader.load_document(doc_record)

        # 4. Convert Staged Chunks to Canonical Chunks & Bulk Persist
        canonical_chunks = [
            CanonicalFullyQualifiedChunk(
                document_id=doc_id,
                path=c.path,
                verbatim_text=c.verbatim_text,
                contextualized_text=c.contextualized_text,
                metadata=c.metadata,
                effective_date=c.effective_date,
                expiration_date=c.expiration_date,
            )
            for c in session.chunks
        ]
        path_to_uuid = await loader.load_chunks(canonical_chunks)

        # 5. Build GraphEdgeRecords with Cross-Document Resolution
        graph_edge_records: list[GraphEdgeRecord] = []
        unresolved_target_paths: list[str] = [
            e.target_path
            for e in session.edges
            if e.target_path and e.target_path not in path_to_uuid
        ]

        # Batch resolve external target paths in PostgreSQL
        external_path_to_uuid: dict[str, Any] = {}
        if unresolved_target_paths:
            external_path_to_uuid = await loader.resolve_chunk_paths(unresolved_target_paths)

        for edge in session.edges:
            src_uuid = path_to_uuid.get(edge.source_path)
            if src_uuid is None:
                raise LegalDomainError(
                    error_code=E_CORPUS_INTEGRITY_VIOLATION,
                    message=f"Source chunk '{edge.source_path}' was not assigned a valid UUID during promotion.",
                    data={"source_path": edge.source_path},
                )

            tgt_uuid = None
            target_ext = edge.target_external_ref

            if edge.target_path:
                if edge.target_path in path_to_uuid:
                    tgt_uuid = path_to_uuid[edge.target_path]
                elif edge.target_path in external_path_to_uuid:
                    tgt_uuid = external_path_to_uuid[edge.target_path]
                elif not target_ext:
                    target_ext = edge.target_path

            graph_edge_records.append(
                GraphEdgeRecord(
                    source_chunk_id=src_uuid,
                    target_chunk_id=tgt_uuid,
                    target_external_ref=target_ext,
                    relation_type=edge.relation_type,
                    citation_text=edge.citation_text,
                    metadata=edge.metadata,
                )
            )

        edges_promoted_count = await loader.load_graph_edges(graph_edge_records)

        # 6. Update Staging Session Status & Record Audit Log
        now = get_vietnam_now()
        session.status = StagingStatus.PROMOTED
        session.promoted_at = now
        session.updated_at = now

        audit_record = StagingMutationRecord(
            actor="HUMAN:reviewer",
            action_type="PROMOTED_TO_PRODUCTION",
            description=(
                f"Successfully promoted document '{doc_code}' to PostgreSQL: "
                f"{len(canonical_chunks)} chunks, {edges_promoted_count} edges."
                + (f" Reviewer notes: {reviewer_notes}" if reviewer_notes else "")
            ),
            timestamp=now,
            diff_payload={
                "document_id": str(doc_id),
                "chunks_promoted": len(canonical_chunks),
                "edges_promoted": edges_promoted_count,
                "reviewer_notes": reviewer_notes,
            },
        )
        session.mutation_history.append(audit_record)

        self.staging_manager.save_session(session)
        logger.info(
            "Successfully promoted session '%s' (Doc UUID: %s) to PostgreSQL.",
            doc_code,
            doc_id,
        )

        return PromotionResultResponse(
            status="SUCCESS",
            doc_code=session.doc_code,
            document_id=str(doc_id),
            chunks_promoted=len(canonical_chunks),
            edges_promoted=edges_promoted_count,
            promoted_at=now.isoformat(),
            message=(
                f"Successfully promoted {len(canonical_chunks)} chunks and "
                f"{edges_promoted_count} graph edges into PostgreSQL."
            ),
        )
