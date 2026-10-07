from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from rag_eval.legal.schemas.domain import (
    ChunkReviewStatus,
    ContextType,
    FinalizationState,
)
from rag_eval.legal.schemas.staging import (
    PreFlightValidationResponse,
    ValidationIssue,
)
from rag_eval.legal.text import (
    is_text_grounded,
    sanitize_ltree_label,
    slice_raw_text,
)

if TYPE_CHECKING:
    from rag_eval.legal.ingestion.staging.session import StagingDocumentSession

_LTREE_SYNTAX_REGEX = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")


class PreFlightValidator:
    """Authoritative integrity verification engine executing 9 automated validation rules."""

    TOTAL_CHECKS: int = 9

    def __init__(self, staging_dir: Path | str | None = None) -> None:
        if staging_dir is not None:
            self.staging_dir = Path(staging_dir)
        else:
            from rag_eval.legal.ingestion.staging.manager import DEFAULT_STAGING_DIR

            self.staging_dir = DEFAULT_STAGING_DIR

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
                        remediation_hint=(
                            "Định danh phân cấp quy phạm (LTREE) yêu cầu tuân thủ cấu trúc nhãn chữ thường, số "
                            "và dấu gạch dưới, phân tách bởi dấu chấm đơn (ví dụ: <doc>.<chuong>.<dieu>.<khoan>.<diem>). "
                            "Cần kiểm tra lại bộ phân rã AST hoặc cấu trúc tiền tố phân cấp của phân đoạn để bảo đảm "
                            "không tồn tại ký tự hoa, khoảng trắng hay dấu phân cách bất thường."
                        ),
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
                        remediation_hint=(
                            "Mọi phân đoạn quy phạm trong phiên làm việc bắt buộc phải thuộc về chính văn bản đó "
                            "thông qua tiền tố gốc đã chuẩn hóa. Cần rà soát nguồn gốc xuất xứ của phân đoạn để "
                            "xác định xem phân đoạn có bị gán nhầm từ văn bản khác hay chưa được đồng nhất tiền tố gốc."
                        ),
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
                    remediation_hint=(
                        "Một văn bản pháp luật hợp lệ phải sở hữu ít nhất một đơn vị quy phạm có hiệu lực. "
                        "Cần rà soát lại toàn văn bản gốc (raw text) và bộ bóc tách cấu trúc để đảm bảo văn bản "
                        "đã được phân rã đúng thành các đơn vị điều khoản trước khi tiến hành thẩm định."
                    ),
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
                    remediation_hint=(
                        "Mốc thời gian có hiệu lực là trục tham chiếu bắt buộc để áp dụng pháp luật theo thời gian. "
                        "Cần tra cứu điều khoản thi hành của văn bản gốc để xác định chính xác ngày văn bản bắt đầu phát sinh hiệu lực."
                    ),
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
                    remediation_hint=(
                        "Quy phạm không thể hết hiệu lực trước thời điểm bắt đầu có hiệu lực thi hành. "
                        "Cần kiểm tra lại các văn bản sửa đổi, bổ sung, bãi bỏ hoặc thời hạn áp dụng được tuyên trong văn bản gốc."
                    ),
                )
            )
        summary["statutory_dates"] = {
            "passed": date_violations == 0,
            "violations": date_violations,
        }

        # 5. CONTENT_GROUNDING
        content_violations = 0
        total_raw_lines = len(session.raw_text.splitlines()) if session.raw_text else 0
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
                        remediation_hint=(
                            "Nguyên tắc bảo chứng pháp lý đòi hỏi mọi đơn vị quy phạm phải chứa toàn văn câu chữ được ban hành. "
                            "Cần đối chiếu lại tọa độ dòng và văn bản gốc để khôi phục đúng nội dung nguyên văn của phân đoạn."
                        ),
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
                        remediation_hint=(
                            "Ngữ cảnh phả hệ điều luật bảo đảm tính tự thân trọn vẹn khi truy xuất độc lập. "
                            "Cần tổng hợp lại chuỗi tiêu đề từ cấp văn bản, chương, mục đến điều để hoàn thiện ngữ cảnh đầy đủ cho phân đoạn."
                        ),
                    )
                )
            if session.raw_text and 1 <= chunk.start_line <= chunk.end_line <= total_raw_lines:
                expected_slice = slice_raw_text(session.raw_text, chunk.start_line, chunk.end_line)
                if not is_text_grounded(chunk.verbatim_text, expected_slice):
                    content_violations += 1
                    issues.append(
                        ValidationIssue(
                            rule="CONTENT_GROUNDING",
                            severity="ERROR",
                            path=chunk.path,
                            message=(
                                f"Nội dung verbatim_text của chunk '{chunk.path}' không khớp với "
                                f"lát cắt văn bản gốc tại tọa độ dòng [{chunk.start_line}..{chunk.end_line}]."
                            ),
                            blocking=True,
                            remediation_hint=(
                                "Nội dung nguyên văn của đoạn quy phạm bắt buộc phải bảo đảm tính bảo chứng (grounding), "
                                "trùng khớp hoàn toàn với câu chữ được ban hành trong văn bản gốc tại khoảng dòng tương ứng."
                            ),
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
                        remediation_hint=(
                            "Một quy phạm không thể tự viện dẫn hoặc áp dụng chế tài lên chính nó. "
                            "Cần phân tích bản chất quan hệ viện dẫn để xác định chính xác phân đoạn đích mà quy phạm đang hướng tới."
                        ),
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
                        remediation_hint=(
                            "Mọi quan hệ pháp lý phải xuất phát từ một phân đoạn quy phạm đang thực sự tồn tại trong phiên làm việc. "
                            "Cần kiểm tra lại lịch sử tái phân cấp hoặc đường dẫn nguồn để định vị chính xác điểm neo của quan hệ."
                        ),
                    )
                )

            # Intra vs Cross-document target validation
            target_root = edge.target_path.split(".", 1)[0]
            if target_root == sanitized_root:
                if edge.target_path not in staged_paths:
                    edge_violations += 1
                    issues.append(
                        ValidationIssue(
                            rule="GRAPH_EDGE_INTEGRITY",
                            severity="ERROR",
                            path=edge.target_path,
                            message=f"Intra-document edge target '{edge.target_path}' not found in staged chunks.",
                            blocking=True,
                            remediation_hint=(
                                "Viện dẫn nội bộ phải trỏ tới một điều, khoản hoặc điểm có thực trong cùng văn bản. "
                                "Cần kiểm tra lại cấu trúc cây quy phạm để xác định đúng tọa độ của điều khoản được dẫn chiếu."
                            ),
                        )
                    )
            else:
                target_session_dir = self.staging_dir / target_root
                if not target_session_dir.exists():
                    edge_violations += 1
                    issues.append(
                        ValidationIssue(
                            rule="GRAPH_EDGE_INTEGRITY",
                            severity="ERROR",
                            path=edge.target_path,
                            message=(
                                f"Cross-document edge target '{edge.target_path}' points to non-existent document '{target_root}'. "
                                "Văn bản đích không tồn tại trong hệ thống. Cấm tạo cạnh đồ thị ảo. "
                                "Phải khai báo vào dangling_dependencies dạng EXTERNAL_CITATION."
                            ),
                            blocking=True,
                            remediation_hint="Văn bản đích phải thuộc danh mục văn bản có thực trong corpus/staging.",
                        )
                    )
                else:
                    from rag_eval.legal.ingestion.wal import WALSessionStore

                    target_wal = WALSessionStore(target_session_dir)
                    target_session = target_wal.load_materialized_session()
                    target_paths = {c.path for c in target_session.chunks}
                    if edge.target_path not in target_paths:
                        edge_violations += 1
                        issues.append(
                            ValidationIssue(
                                rule="GRAPH_EDGE_INTEGRITY",
                                severity="ERROR",
                                path=edge.target_path,
                                message=f"Cross-document edge target '{edge.target_path}' not found in document '{target_root}'.",
                                blocking=True,
                                remediation_hint="Phân đoạn đích phải là một chunk có thực trong văn bản đích.",
                            )
                        )
        summary["graph_edge_integrity"] = {
            "passed": edge_violations == 0,
            "violations": edge_violations,
        }

        # 7. COORDINATE_CONTINUITY
        coord_violations = 0
        total_raw_lines = len(session.raw_text.splitlines()) if session.raw_text else 0
        for chunk in session.chunks:
            if (
                chunk.start_line < 1
                or chunk.end_line < chunk.start_line
                or (total_raw_lines > 0 and chunk.end_line > total_raw_lines)
            ):
                coord_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="COORDINATE_CONTINUITY",
                        severity="ERROR",
                        path=chunk.path,
                        message=(
                            f"Invalid line coordinates [{chunk.start_line}..{chunk.end_line}] "
                            f"for chunk '{chunk.path}' (total raw lines: {total_raw_lines})."
                        ),
                        blocking=True,
                        remediation_hint=(
                            "Tọa độ dòng trong văn bản nguồn phải là chỉ số 1-indexed hợp lệ, có phạm vi đóng "
                            "(end_line >= start_line) và không vượt quá tổng số dòng của văn bản nguồn."
                        ),
                    )
                )

            chunk_len = len(chunk.verbatim_text)
            for dep in chunk.dangling_dependencies:
                char_start = dep.char_start
                char_end = dep.char_end
                if char_start is None and dep.dependency_text and chunk.verbatim_text:
                    pos = chunk.verbatim_text.find(dep.dependency_text.strip())
                    if pos != -1:
                        char_start = pos
                        char_end = pos + len(dep.dependency_text.strip())

                if char_start is not None and char_end is not None:
                    if char_start < 0 or char_end <= char_start or char_end > chunk_len:
                        coord_violations += 1
                        issues.append(
                            ValidationIssue(
                                rule="COORDINATE_CONTINUITY",
                                severity="ERROR",
                                path=chunk.path,
                                message=(
                                    f"Invalid span coordinates [char_start={char_start}, char_end={char_end}] "
                                    f"exceeding text length ({chunk_len}) for chunk '{chunk.path}'."
                                ),
                                blocking=True,
                                remediation_hint=(
                                    "Phạm vi ký tự của điểm neo viện dẫn bắt buộc phải nằm trọn vẹn trong chuỗi văn bản nguyên văn của phân đoạn. "
                                    "Cần đối chiếu vị trí xuất hiện của cụm từ viện dẫn trong nội dung quy phạm để căn chỉnh lại tọa độ ký tự chính xác."
                                ),
                            )
                        )
                    elif dep.dependency_type == "EXTERNAL_CITATION":
                        actual = chunk.verbatim_text[char_start:char_end]
                        if actual != dep.dependency_text.strip():
                            coord_violations += 1
                            issues.append(
                                ValidationIssue(
                                    rule="COORDINATE_CONTINUITY",
                                    severity="ERROR",
                                    path=chunk.path,
                                    message=(
                                        f"Span slice [{char_start}:{char_end}] '{actual}' does not match "
                                        f"dependency_text '{dep.dependency_text}' on chunk '{chunk.path}'."
                                    ),
                                    blocking=True,
                                    remediation_hint=(
                                        "Đoạn trích ký tự [char_start:char_end] phải khớp chính xác từng ký tự với nội dung viện dẫn khai báo. "
                                        "Cần tìm vị trí chuỗi con thực tế của cụm từ viện dẫn trong câu chữ nguyên văn để cập nhật lại tọa độ lát cắt."
                                    ),
                                )
                            )
                elif dep.dependency_type == "EXTERNAL_CITATION":
                    coord_violations += 1
                    issues.append(
                        ValidationIssue(
                            rule="COORDINATE_CONTINUITY",
                            severity="ERROR",
                            path=chunk.path,
                            message=(
                                f"External citation '{dep.dependency_text}' was not found in verbatim_text "
                                f"for chunk '{chunk.path}'."
                            ),
                            blocking=True,
                            remediation_hint=(
                                "Chuỗi văn bản viện dẫn ngoại vi bắt buộc phải tồn tại trong nội dung nguyên văn của phân đoạn. "
                                "Cần kiểm tra lại câu chữ nguyên văn hoặc chỉnh sửa nội dung chuỗi viện dẫn cho khớp từng ký tự."
                            ),
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
                        remediation_hint=(
                            "Mỗi đơn vị quy phạm phải sở hữu một định danh phân cấp duy nhất trên toàn văn bản. "
                            "Xung đột đường dẫn biểu thị việc phân rã trùng lặp hoặc nhập nhằng giữa các khoản/điểm khác nhau; "
                            "cần kiểm tra lại phả hệ cấu trúc để phân định ranh giới độc lập cho từng quy phạm."
                        ),
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
                        remediation_hint=(
                            "Văn bản chỉ đủ điều kiện ban hành vào hệ thống khi toàn bộ các đơn vị quy phạm đã được kiểm tra và nghiệm thu. "
                            "Cần rà soát nội dung nguyên văn, ngữ cảnh và các mối quan hệ liên kết của phân đoạn để hoàn tất quy trình thẩm định."
                        ),
                    )
                )

            # 2. ContextType classification check
            if chunk.context_type is None:
                finalization_violations += 1
                issues.append(
                    ValidationIssue(
                        rule="FINALIZATION_DEPENDENCY_ALIGNMENT",
                        severity="ERROR",
                        path=chunk.path,
                        message=f"Chunk '{chunk.path}' chưa được phân loại context_type qua stg_patch trước khi chốt nghiệm thu.",
                        blocking=True,
                        remediation_hint=(
                            "Mọi quy phạm phải được phân loại rõ ràng: 'SELF_CONTAINED' (tự thân) hoặc 'REQUIRES_EXTERNAL_CONTEXT' (có phụ thuộc) trước khi chốt nghiệm thu."
                        ),
                    )
                )
            else:
                chunk_edges = [e for e in session.edges if e.source_path == chunk.path]
                if chunk.context_type == ContextType.SELF_CONTAINED:
                    if chunk_edges:
                        finalization_violations += 1
                        issues.append(
                            ValidationIssue(
                                rule="FINALIZATION_DEPENDENCY_ALIGNMENT",
                                severity="ERROR",
                                path=chunk.path,
                                message=f"Chunk '{chunk.path}' được khai báo SELF_CONTAINED nhưng tồn tại {len(chunk_edges)} cạnh quan hệ trong đồ thị.",
                                blocking=True,
                                remediation_hint="Cần xóa các cạnh thừa hoặc chuyển context_type sang REQUIRES_EXTERNAL_CONTEXT.",
                            )
                        )
                    if chunk.dangling_dependencies:
                        finalization_violations += 1
                        issues.append(
                            ValidationIssue(
                                rule="FINALIZATION_DEPENDENCY_ALIGNMENT",
                                severity="ERROR",
                                path=chunk.path,
                                message=f"Chunk '{chunk.path}' được khai báo SELF_CONTAINED nhưng tồn tại {len(chunk.dangling_dependencies)} viện dẫn dở dang trong dangling_dependencies.",
                                blocking=True,
                                remediation_hint="Cần xóa dangling_dependencies hoặc chuyển context_type sang REQUIRES_EXTERNAL_CONTEXT.",
                            )
                        )
                elif chunk.context_type == ContextType.REQUIRES_EXTERNAL_CONTEXT:
                    if not chunk_edges and not chunk.dangling_dependencies:
                        finalization_violations += 1
                        issues.append(
                            ValidationIssue(
                                rule="FINALIZATION_DEPENDENCY_ALIGNMENT",
                                severity="ERROR",
                                path=chunk.path,
                                message=f"Chunk '{chunk.path}' được khai báo REQUIRES_EXTERNAL_CONTEXT nhưng không có cạnh quan hệ nào và cũng không có dangling_dependencies.",
                                blocking=True,
                                remediation_hint="Cần tạo cạnh quan hệ bằng stg_add_edges hoặc khai báo viện dẫn ngoài trong dangling_dependencies qua stg_patch.",
                            )
                        )

            # 3. Semantic alignment check
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
                        remediation_hint=(
                            "Quy phạm không thể ở trạng thái hoàn tất (FINALIZED) nếu vẫn còn các viện dẫn pháp lý dở dang chưa được khép kín. "
                            "Cần thẩm định thực chất các viện dẫn mở này (liên kết với điều khoản đích tương ứng) hoặc duy trì trạng thái chưa hoàn tất (UNFINALIZED) nếu viện dẫn trỏ ra ngoài phạm vi văn bản."
                        ),
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
                        remediation_hint=(
                            "Trạng thái chưa hoàn tất (UNFINALIZED) chỉ có hiệu lực khi quy phạm thực sự còn tồn tại viện dẫn mở cần xử lý. "
                            "Nếu quy phạm đã trọn vẹn về mặt ngữ nghĩa và không dẫn chiếu tới quy định nào khác, trạng thái cấu trúc của nó phải phản ánh đúng tính tự thân hoàn chỉnh."
                        ),
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
