from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rag_eval.legal.schemas.domain import (
    ChunkReviewStatus,
    FinalizationState,
)
from rag_eval.legal.schemas.staging import (
    PreFlightValidationResponse,
    ValidationIssue,
)
from rag_eval.legal.text import (
    sanitize_ltree_label,
)

if TYPE_CHECKING:
    from rag_eval.legal.ingestion.staging.session import StagingDocumentSession

_LTREE_SYNTAX_REGEX = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")


class PreFlightValidator:
    """Authoritative integrity verification engine executing 9 automated validation rules."""

    TOTAL_CHECKS: int = 9

    def validate(self, session: StagingDocumentSession) -> PreFlightValidationResponse:
        """Executes all 9 automated integrity checks against session state."""
        issues: list[ValidationIssue] = []
        summary: dict[str, object] = {}
        sanitized_root = sanitize_ltree_label(session.doc_code)

        # 1. LTREE_PATH_SYNTAX
        syntax_violations = 0
        for chunk in session.chunks:
            if not _LTREE_SYNTAX_REGEX.match(chunk.path):
                syntax_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="LTREE_PATH_SYNTAX",
                        severity="ERROR",
                        path=chunk.path,
                        message=f"Chunk path '{chunk.path}' violates LTREE dot-syntax specification.",
                        blocking=True,
                    )
                )
        summary["ltree_path_syntax"] = {
            "passed": syntax_violations == 0,
            "violations": syntax_violations,
        }

        # 2. ROOT_CODE_ALIGNMENT
        root_violations = 0
        for chunk in session.chunks:
            root_seg = chunk.path.split(".", 1)[0]
            if root_seg != sanitized_root:
                root_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="ROOT_CODE_ALIGNMENT",
                        severity="ERROR",
                        path=chunk.path,
                        message=f"Chunk root prefix '{root_seg}' does not match sanitized doc_code '{sanitized_root}'.",
                        blocking=True,
                    )
                )
        summary["root_code_alignment"] = {
            "passed": root_violations == 0,
            "violations": root_violations,
        }

        # 3. PARENT_CHILD_CONTINUITY
        continuity_violations = 0
        if not session.chunks:
            continuity_violations += 1
            issues.append(
                ValidationIssue(
                    rule="PARENT_CHILD_CONTINUITY",
                    severity="ERROR",
                    path=sanitized_root,
                    message="Staging session contains 0 chunks.",
                    blocking=True,
                )
            )
        summary["parent_child_continuity"] = {
            "passed": continuity_violations == 0,
            "violations": continuity_violations,
        }

        # 4. STATUTORY_DATES
        date_violations = 0
        if not session.effective_date:
            date_violations += 1
            issues.append(
                ValidationIssue(
                    rule="STATUTORY_DATES",
                    severity="ERROR",
                    path=sanitized_root,
                    message="Document effective_date is missing.",
                    blocking=True,
                )
            )
        elif session.expiration_date and session.expiration_date < session.effective_date:
            date_violations += 1
            issues.append(
                ValidationIssue(
                    rule="STATUTORY_DATES",
                    severity="ERROR",
                    path=sanitized_root,
                    message=f"expiration_date ({session.expiration_date}) cannot precede effective_date ({session.effective_date}).",
                    blocking=True,
                )
            )
        summary["statutory_dates"] = {
            "passed": date_violations == 0,
            "violations": date_violations,
        }

        # 5. CONTENT_GROUNDING
        content_violations = 0
        for chunk in session.chunks:
            if not chunk.verbatim_text or not chunk.verbatim_text.strip():
                content_violations += 1
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
                content_violations += 1
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
            "passed": content_violations == 0,
            "violations": content_violations,
        }

        # 6. GRAPH_EDGE_INTEGRITY
        staged_paths = {c.path for c in session.chunks}
        edge_violations = 0
        for edge in session.edges:
            # Self-referencing loop prevention
            if edge.source_path == edge.target_path:
                edge_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="GRAPH_EDGE_INTEGRITY",
                        severity="ERROR",
                        path=edge.source_path,
                        message=f"Self-referencing edge loop detected: source '{edge.source_path}' == target '{edge.target_path}'.",
                        blocking=True,
                    )
                )

            if edge.source_path not in staged_paths:
                edge_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="GRAPH_EDGE_INTEGRITY",
                        severity="ERROR",
                        path=edge.source_path,
                        message=f"Edge source path '{edge.source_path}' not grounded in staged chunks.",
                        blocking=True,
                    )
                )

            # Self-reference check
            if edge.source_path == edge.target_path:
                edge_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="GRAPH_EDGE_INTEGRITY",
                        severity="ERROR",
                        path=edge.source_path,
                        message=f"Self-referencing edge loop detected on '{edge.source_path}'.",
                        blocking=True,
                    )
                )

            # Intra-document target validation
            target_root = edge.target_path.split(".", 1)[0]
            if target_root == sanitized_root and edge.target_path not in staged_paths:
                edge_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="GRAPH_EDGE_INTEGRITY",
                        severity="ERROR",
                        path=edge.target_path,
                        message=f"Intra-document edge target '{edge.target_path}' not found in staged chunks.",
                        blocking=True,
                    )
                )
        summary["graph_edge_integrity"] = {
            "passed": edge_violations == 0,
            "violations": edge_violations,
        }

        # 7. COORDINATE_CONTINUITY
        coord_violations = 0
        for chunk in session.chunks:
            if chunk.start_line < 1 or chunk.end_line < chunk.start_line:
                coord_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="COORDINATE_CONTINUITY",
                        severity="ERROR",
                        path=chunk.path,
                        message=f"Invalid line coordinates [{chunk.start_line}..{chunk.end_line}] for chunk '{chunk.path}'.",
                        blocking=True,
                    )
                )

            chunk_len = len(chunk.verbatim_text)
            for dep in chunk.dangling_dependencies:
                if dep.char_start is not None and dep.char_end is not None:
                    if dep.char_start < 0 or dep.char_end <= dep.char_start or dep.char_end > chunk_len:
                        coord_violations += 1
                        issues.append(
                            ValidationIssue(
                                rule="COORDINATE_CONTINUITY",
                                severity="ERROR",
                                path=chunk.path,
                                message=(
                                    f"Invalid span coordinates [char_start={dep.char_start}, char_end={dep.char_end}] "
                                    f"exceeding text length ({chunk_len}) for chunk '{chunk.path}'."
                                ),
                                blocking=True,
                            )
                        )
                    elif dep.dependency_type == "EXTERNAL_CITATION":
                        actual = chunk.verbatim_text[dep.char_start:dep.char_end]
                        if actual != dep.dependency_text.strip():
                            coord_violations += 1
                            issues.append(
                                ValidationIssue(
                                    rule="COORDINATE_CONTINUITY",
                                    severity="ERROR",
                                    path=chunk.path,
                                    message=(
                                        f"Span slice [{dep.char_start}:{dep.char_end}] '{actual}' does not match "
                                        f"dependency_text '{dep.dependency_text}' on chunk '{chunk.path}'."
                                    ),
                                    blocking=True,
                                )
                            )
        summary["coordinate_continuity"] = {
            "passed": coord_violations == 0,
            "violations": coord_violations,
        }

        # 8. DUPLICATE_PATH_COLLISION
        seen_paths: set[str] = set()
        duplicate_violations = 0
        for chunk in session.chunks:
            if chunk.path in seen_paths:
                duplicate_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="DUPLICATE_PATH_COLLISION",
                        severity="ERROR",
                        path=chunk.path,
                        message=f"Duplicate chunk path collision detected: '{chunk.path}'.",
                        blocking=True,
                    )
                )
            seen_paths.add(chunk.path)
        summary["duplicate_path_collision"] = {
            "passed": duplicate_violations == 0,
            "violations": duplicate_violations,
        }

        # 9. FINALIZATION_DEPENDENCY_ALIGNMENT
        finalization_violations = 0
        for chunk in session.chunks:
            # 1. Review status check
            chunk_status_str = chunk.review_status.value
            if chunk_status_str != ChunkReviewStatus.REVIEWED.value:
                finalization_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="FINALIZATION_DEPENDENCY_ALIGNMENT",
                        severity="ERROR",
                        path=chunk.path,
                        message=f"Chunk '{chunk.path}' review_status is '{chunk_status_str}' (must be REVIEWED).",
                        blocking=True,
                    )
                )

            # 2. Semantic alignment check
            is_finalized = chunk.finalization_state in (
                FinalizationState.FINALIZED_SELF_CONTAINED,
                FinalizationState.FINALIZED_FULLY_LINKED,
            )
            has_dangling = len(chunk.dangling_dependencies) > 0

            if is_finalized and has_dangling:
                finalization_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="FINALIZATION_DEPENDENCY_ALIGNMENT",
                        severity="ERROR",
                        path=chunk.path,
                        message=(
                            f"Chunk '{chunk.path}' is marked '{chunk.finalization_state.value}' "
                            f"but retains {len(chunk.dangling_dependencies)} unresolved dangling dependencies."
                        ),
                        blocking=True,
                    )
                )
            elif not is_finalized and not has_dangling:
                finalization_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="FINALIZATION_DEPENDENCY_ALIGNMENT",
                        severity="ERROR",
                        path=chunk.path,
                        message=(
                            f"Chunk '{chunk.path}' is unfinalized ('{chunk.finalization_state.value}') "
                            "but declares 0 dangling dependencies justifying its incomplete state."
                        ),
                        blocking=True,
                    )
                )

        summary["finalization_dependency_alignment"] = {
            "passed": finalization_violations == 0,
            "violations": finalization_violations,
        }

        has_blocking = any(issue.blocking for issue in issues)
        passed = not has_blocking

        return PreFlightValidationResponse(
            status="PASSED" if passed else "FAILED",
            passed=passed,
            total_checks=self.TOTAL_CHECKS,
            issues=issues,
            summary=summary,
        )
