from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rag_eval.legal.schemas.domain import (
    ChunkDelta,
    ChunkMetadata,
    ChunkReviewStatus,
    ContextType,
    DocumentMetadata,
    FinalizationState,
    GrepMatchTier,
    NodeType,
    RelationEdge,
    StagingStatus,
    UnresolvedReference,
)
from rag_eval.legal.text import parse_flexible_date


class MutationRecord(BaseModel):
    """Immutable audit trail record for state transformations."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique record ID")
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="UTC timestamp",
    )
    actor: str = Field(..., description="'SYSTEM' | 'AGENT' | 'HUMAN:<username>'")
    action_type: str = Field(..., description="Action type code")
    description: str = Field(..., description="Human-readable summary")
    diff_payload: dict[str, object] | None = Field(default=None, description="Detailed mutation payload")


class MutationResult(BaseModel):
    """Canonical result of state mutation operations."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("SUCCESS", description="Operation status")
    doc_code: str | None = Field(None, description="Document code")
    message: str = Field("", description="Status message")
    affected_count: int = Field(default=0, description="Number of items affected")
    total_count: int = Field(default=0, description="Total items remaining")


class SessionSummary(BaseModel):
    """Summary of a statutory staging session."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Statutory document code")
    title: str = Field(..., description="Document title")
    status: StagingStatus = Field(..., description="Current staging status")
    total_chunks: int = Field(..., description="Total count of staged chunks")
    total_edges: int = Field(..., description="Total count of staged edges")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    created_at: datetime.datetime = Field(..., description="Session creation timestamp")
    updated_at: datetime.datetime = Field(..., description="Session last updated timestamp")
    committed_at: datetime.datetime | None = Field(None, description="Session commit timestamp")
    promoted_at: datetime.datetime | None = Field(None, description="Session promotion timestamp")


class StagedChunkDetail(BaseModel):
    """Canonical inspection payload for a single staged statutory chunk."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Số hiệu văn bản của phiên làm việc staging")
    path: str = Field(..., description="Đường dẫn phân cấp ltree chính xác của đoạn quy phạm")
    parent_context: str = Field(..., description="Ngữ cảnh phân cấp cha mẹ (breadcrumbs)")
    verbatim_text: str = Field(..., description="Nội dung văn bản nguyên văn trọn vẹn")
    start_line: int = Field(..., ge=1, description="Dòng bắt đầu trong văn bản nguồn")
    end_line: int = Field(..., ge=1, description="Dòng kết thúc trong văn bản nguồn")
    metadata: ChunkMetadata = Field(
        default_factory=ChunkMetadata,
        description="Siêu dữ liệu cấu trúc của đoạn quy phạm",
    )
    effective_date: datetime.date = Field(..., description="Ngày có hiệu lực của đoạn quy phạm")
    expiration_date: datetime.date | None = Field(
        default=None,
        description="Ngày hết hiệu lực nếu có (None khi không xác định thời hạn)",
    )
    context_type: ContextType | None = Field(
        default=None,
        description="Phân loại tính độc lập của ngữ cảnh: SELF_CONTAINED hoặc REQUIRES_EXTERNAL_CONTEXT",
    )
    justification: str | None = Field(
        default=None,
        description="Lý giải căn cứ pháp lý cho phân loại",
    )
    review_status: ChunkReviewStatus = Field(..., description="Trạng thái thẩm định của đoạn quy phạm")
    finalization_state: FinalizationState = Field(..., description="Trạng thái chốt nghiệm thu")
    dangling_dependencies: list[UnresolvedReference] = Field(
        default_factory=list,
        description="Danh sách viện dẫn treo hoặc ngoại vi",
    )
    edges: list[RelationEdge] = Field(
        default_factory=list,
        description="Danh sách các cạnh quan hệ đồ thị gắn với chunk",
    )


class StgSessionSummaryItem(BaseModel):
    """Compact summary item of a staging session for MCP discovery."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Số hiệu văn bản")
    status: StagingStatus = Field(..., description="Trạng thái phiên làm việc")
    total_chunks: int = Field(..., description="Tổng số đoạn quy phạm")
    total_edges: int = Field(..., description="Tổng số cạnh quan hệ đồ thị")
    effective_date: datetime.date = Field(..., description="Ngày có hiệu lực của văn bản")
    expiration_date: datetime.date | None = Field(
        default=None,
        description="Ngày hết hiệu lực của văn bản (None khi còn hiệu lực vô thời hạn)",
    )
    title: str = Field(..., description="Tiêu đề văn bản")


class StgListSessionsResponse(BaseModel):
    """Unified single-object list response for staging sessions discovery over MCP."""

    model_config = ConfigDict(extra="ignore")

    total_sessions: int = Field(..., description="Tổng số phiên làm việc")
    sessions: list[StgSessionSummaryItem] = Field(
        ...,
        description="Danh sách tóm tắt các phiên làm việc",
    )


class SessionStatusResult(BaseModel):
    """Result of a session status transition."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Số hiệu văn bản")
    status: str = Field(..., description="Trạng thái phiên làm việc")
    total_chunks: int = Field(..., description="Tổng số đoạn quy phạm")
    total_edges: int = Field(default=0, description="Tổng số cạnh quan hệ")
    transitioned_at: str = Field(..., description="Thời điểm chuyển trạng thái (ISO 8601)")
    message: str = Field("", description="Thông điệp kết quả")


class StatusTransitionRequest(BaseModel):
    """Request payload for session status transition."""

    model_config = ConfigDict(extra="ignore")

    status: StagingStatus = Field(..., description="Target lifecycle status")
    actor: str = Field("HUMAN:reviewer", description="Actor initiating status transition")
    description: str = Field("", description="Reason or notes for transition")


class ReparentPathMapping(BaseModel):
    """Pairwise mapping from old ltree path to new ltree path."""

    old_path: str = Field(..., description="Original ltree path before migration")
    new_path: str = Field(..., description="Transformed ltree path after migration")


class ReparentSubtreeRequest(BaseModel):
    """Request payload to migrate a subtree to a new parent prefix."""

    model_config = ConfigDict(extra="ignore")

    old_path_prefix: str = Field(..., description="Existing path prefix to move")
    new_path_prefix: str = Field(..., description="New target path prefix")
    dry_run: bool = Field(False, description="Whether to simulate mutation")
    actor: str = Field("HUMAN:reviewer", description="Action author")


class ReparentSubtreeResult(BaseModel):
    """Canonical result of subtree re-parenting."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("SUCCESS", description="Operation status")
    doc_code: str = Field(..., description="Statutory document code")
    dry_run: bool = Field(False, description="Whether mutation was simulated")
    affected_chunks_count: int = Field(..., description="Total chunks migrated")
    affected_edges_count: int = Field(..., description="Total internal edges migrated")
    old_path_prefix: str = Field(..., description="Old prefix")
    new_path_prefix: str = Field(..., description="New target prefix")
    total_chunks: int = Field(..., description="Total chunks remaining")
    sample_mappings: list[ReparentPathMapping] = Field(
        default_factory=list, description="Sample of path mappings"
    )


class BatchPatchRequest(BaseModel):
    """Request payload for batch updating and removing chunks."""

    model_config = ConfigDict(extra="ignore")

    updated_chunks: list[ChunkDelta] = Field(
        default_factory=list, description="List of chunk deltas to add or update"
    )
    removed_paths: list[str] = Field(
        default_factory=list, description="List of chunk paths to delete"
    )


class BatchPatchResult(BaseModel):
    """Canonical result returned after applying a chunk batch patch."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("SUCCESS", description="Operation status")
    doc_code: str = Field(..., description="Document statutory code")
    updated_count: int = Field(..., description="Number of chunks updated")
    removed_count: int = Field(default=0, description="Number of chunk paths removed")
    cascaded_count: int = Field(default=0, description="Number of descendant chunks updated")
    total_chunks: int = Field(..., description="Total remaining chunks in session")
    fields_modified: list[str] = Field(
        default_factory=list, description="Unique field names modified across all deltas"
    )


class ChunkProgressStats(BaseModel):
    """Progress statistics for chunk review."""

    model_config = ConfigDict(extra="ignore")

    total_chunks: int = Field(..., description="Tổng số chunk trong văn bản")
    finalized_count: int = Field(..., description="Số chunk đã chốt hoàn tất")
    pending_count: int = Field(..., description="Số chunk còn chờ rà soát")
    progress_percent: float = Field(..., description="Tỷ lệ tiến độ (%)")


class ChunkFinalizeStatus(BaseModel):
    """Finalization status of an individual chunk."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Đường dẫn ltree của đoạn quy phạm")
    review_status: ChunkReviewStatus = Field(..., description="Trạng thái rà soát")
    finalization_state: FinalizationState = Field(..., description="Trạng thái hoàn thiện pháp lý")
    context_type: ContextType | None = Field(default=None, description="Phân loại ngữ nghĩa")


class FinalizeChunksRequest(BaseModel):
    """Request payload to finalize chunks."""

    model_config = ConfigDict(extra="ignore")

    paths: list[str] = Field(..., min_length=1, description="List of chunk paths to finalize")


class FinalizeChunksResult(BaseModel):
    """Result of chunk finalization."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("SUCCESS", description="Operation status")
    doc_code: str = Field(..., description="Document statutory code")
    finalized_count: int = Field(..., description="Number of chunks finalized")
    pending_remaining: int = Field(..., description="Remaining pending chunks")
    paths: list[str] = Field(default_factory=list, description="Finalized chunk paths")
    results: list[ChunkFinalizeStatus] = Field(
        default_factory=list, description="Detailed finalization status"
    )


class UnfinalizeChunksRequest(BaseModel):
    """Request payload to unfinalize chunks."""

    model_config = ConfigDict(extra="ignore")

    paths: list[str] = Field(..., min_length=1, description="List of chunk paths to unfinalize")


class UnfinalizeChunksResult(BaseModel):
    """Result of chunk unfinalization."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("SUCCESS", description="Operation status")
    doc_code: str = Field(..., description="Document statutory code")
    unfinalized_count: int = Field(..., description="Number of chunks unfinalized")
    pending_count: int = Field(..., description="Number of pending chunks")
    paths: list[str] = Field(default_factory=list, description="Unfinalized chunk paths")


class PendingChunkLeaf(BaseModel):
    """Lightweight leaf provision node for staging review with strict coordinate invariants."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(
        ...,
        description="Đường dẫn phân cấp ltree đầy đủ của đoạn quy phạm (ví dụ: '100_2019_nd_cp.c_ii.a_5.c_1.p_a')",
    )
    verbatim_text: str = Field(..., description="Nội dung nguyên văn của đoạn quy phạm")
    start_line: int = Field(..., ge=1, description="Dòng bắt đầu trong văn bản nguồn")
    end_line: int = Field(..., ge=1, description="Dòng kết thúc trong văn bản nguồn")
    dangling_dependencies: list[UnresolvedReference] = Field(
        default_factory=list,
        description="Danh sách các viện dẫn luật cần gắn kết đồ thị",
    )
    context_type: ContextType | None = Field(
        default=None,
        description="Phân loại ngữ nghĩa: SELF_CONTAINED hoặc REQUIRES_EXTERNAL_CONTEXT",
    )
    justification: str | None = Field(
        default=None,
        description="Căn cứ thẩm định giải trình tính tự chứa hoặc tóm tắt phụ thuộc",
    )


class PendingChunkGroup(BaseModel):
    """Group of leaf provisions sharing an immediate parent legislative context."""

    model_config = ConfigDict(extra="ignore")

    parent_path: str = Field(..., description="Đường dẫn phân cấp ltree của cấp cha (Điều hoặc Khoản)")
    parent_context: str = Field(..., description="Tiêu đề Điều và câu dẫn Khoản cha dùng chung cho cả nhóm")
    chunks: list[PendingChunkLeaf] = Field(..., description="Danh sách các đoạn quy phạm con trong nhóm")


class PendingChunksResult(BaseModel):
    """Hierarchically grouped pending chunks queue polling result with explicit batch count."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Số hiệu văn bản")
    progress: ChunkProgressStats = Field(..., description="Thống kê tiến độ rà soát")
    limit: int = Field(..., description="Giới hạn số chunk tối đa của đợt rút việc")
    has_more: bool = Field(..., description="Còn chunk chưa chốt hay không")
    returned_chunks: int = Field(..., description="Tổng số đoạn quy phạm con được trả về trong đợt này")
    groups: list[PendingChunkGroup] = Field(..., description="Các nhóm quy phạm kèm ngữ cảnh cha")






class ValidationIssue(BaseModel):
    """Discrete rule check violation."""

    model_config = ConfigDict(extra="ignore")

    rule: str = Field(..., description="Rule code identifier")
    severity: str = Field("ERROR", description="'ERROR' | 'WARNING'")
    path: str | None = Field(None, description="Affected chunk path or entity")
    message: str = Field(..., description="Human-readable violation description")
    blocking: bool = Field(True, description="Whether this issue blocks promotion")
    remediation_hint: str | None = Field(
        default=None, description="Actionable remediation instructions"
    )


class PreFlightValidationResponse(BaseModel):
    """Pre-flight verification checklist result."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field(..., description="'PASSED' | 'FAILED'")
    passed: bool = Field(..., description="True if all blocking checks passed")
    total_checks: int = Field(..., description="Total automated integrity checks run")
    issues: list[ValidationIssue] = Field(default_factory=list, description="Validation issues")
    summary: dict[str, object] = Field(default_factory=dict, description="Summary breakdown")


class PromoteSessionRequest(BaseModel):
    """Payload to trigger human promotion to PostgreSQL."""

    model_config = ConfigDict(extra="ignore")

    reviewer_notes: str | None = Field(None, description="Optional reviewer audit notes")
    compute_embeddings: bool = Field(True, description="Whether to compute vector embeddings")


class PromotionResultResponse(BaseModel):
    """Result of promotion to PostgreSQL."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("SUCCESS", description="'SUCCESS' | 'FAILED'")
    doc_code: str = Field(..., description="Promoted document code")
    document_id: str = Field(..., description="PostgreSQL document UUID")
    chunks_promoted: int = Field(..., description="Chunks persisted")
    edges_promoted: int = Field(..., description="Edges persisted")
    promoted_at: str = Field(..., description="ISO 8601 promotion timestamp")
    message: str = Field("", description="Status message")


class ReplayVerificationResponse(BaseModel):
    """Result of deterministic replay from genesis baseline."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("SUCCESS", description="Replay status")
    doc_code: str = Field(..., description="Document statutory code")
    applied_lsn: int = Field(..., description="Highest LSN applied")
    is_deterministic: bool = Field(True, description="Whether replay reproduced state")
    total_chunks: int = Field(..., description="Total chunks reconstructed")
    total_edges: int = Field(..., description="Total edges reconstructed")
    message: str = Field("", description="Verification message")


class CreateSessionRequest(BaseModel):
    """Request payload to create a new session from raw statutory text."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Unique statutory document code")
    title: str = Field(..., description="Full document title")
    raw_text: str = Field(..., description="Raw text of statutory document")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    metadata: DocumentMetadata | dict[str, object] = Field(
        default_factory=dict, description="Document metadata"
    )

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: object) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)


class GrepHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(..., ge=1, description="Thứ hạng kết quả (1-indexed)")
    score: float = Field(..., ge=0.0, le=1.0, description="Điểm số liên quan chuẩn hóa")
    path: str = Field(..., min_length=1, description="Đường dẫn ltree định danh duy nhất")
    doc_code: str = Field(..., min_length=1, description="Mã văn bản sở tại")
    address: str = Field(..., min_length=1, description="Địa chỉ nhân bản: Điều X Khoản Y")
    node_type: NodeType = Field(..., description="Loại nút AST chuẩn")
    matched_in: list[GrepMatchTier] = Field(..., min_length=1, description="Vị trí khớp quy phạm")
    snippet: str = Field(..., min_length=1, description="Đoạn trích dẫn văn cảnh có highlight **từ khóa**")
    start_line: int = Field(..., ge=1, description="Dòng bắt đầu trong văn bản nguồn (1-indexed)")
    end_line: int = Field(..., ge=1, description="Dòng kết thúc trong văn bản nguồn (1-indexed)")


class StgGrepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: str = Field(..., min_length=1, description="Từ khóa hoặc regex bắt buộc tìm kiếm")
    doc_code: str | None = Field(None, description="Mã văn bản (None nếu quét toàn bộ kho staging)")
    heading_hint: str | None = Field(None, description="Gợi ý tiêu đề Điều/Chương để cộng điểm rank")
    body_hint: str | None = Field(None, description="Gợi ý nội dung Khoản/Điểm để cộng điểm rank")
    is_regex: bool = Field(False, description="True nếu pattern là regex")
    case_sensitive: bool = Field(False, description="True nếu phân biệt chữ hoa/thường")
    limit: int = Field(default=15, ge=1, le=30, description="Số lượng hit tối đa trả về")


class StgGrepResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_matches: int = Field(..., ge=0, description="Tổng số chunks thỏa mãn điều kiện")
    returned: int = Field(..., ge=0, description="Số lượng hit thực tế trả về trong đợt này")
    has_more: bool = Field(..., description="True nếu còn kết quả chưa được hiển thị")
    hits: list[GrepHit] = Field(default_factory=list, description="Danh sách các hit đã được xếp hạng")
