from __future__ import annotations

import datetime
import uuid
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rag_eval.legal.schemas import (
    FINALIZATION_STATE_DESCRIPTION,
    ChunkMetadata,
    DanglingDependencyRecord,
    EdgeMetadata,
    FinalizationState,
    parse_flexible_date,
    validate_ltree_path,
)


def _resolve_default_staging_dir() -> Path:
    """Resolves absolute staging directory anchored to repository root or STAGING_DIR env var."""
    import os

    env_dir = os.environ.get("STAGING_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    curr = Path(__file__).resolve().parent
    for parent in [curr, *curr.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "rag_eval").exists():
            return (parent / ".cache" / "stg").resolve()
    return (Path.cwd() / ".cache" / "stg").resolve()


DEFAULT_STAGING_DIR = _resolve_default_staging_dir()


def deep_merge_dict(base: dict[str, object], delta: dict[str, object]) -> dict[str, object]:
    """Recursively merges delta dictionary into base dictionary without clobbering sibling keys."""
    merged = dict(base)
    for key, value in delta.items():
        base_val = merged.get(key)
        if isinstance(base_val, dict) and isinstance(value, dict):
            merged[key] = deep_merge_dict(base_val, value)
        else:
            merged[key] = value
    return merged


class ChunkReviewStatus(str, Enum):
    """Review lifecycle status for an individual statutory chunk within staging."""

    PENDING = "PENDING"
    REVIEWED = "REVIEWED"


class StagingStatus(str, Enum):
    """Lifecycle statuses for statutory staging sessions."""

    DRAFT = "DRAFT"
    AGENT_COMMITTED = "AGENT_COMMITTED"
    APPROVED = "APPROVED"
    PROMOTED = "PROMOTED"
    AMENDMENT = "AMENDMENT"


class RelationType(str, Enum):
    """Canonical legal relation types between statutory provisions."""

    REFERENCES = "REFERENCES"
    SANCTIONS = "SANCTIONS"
    OVERRIDES = "OVERRIDES"
    EXEMPTS = "EXEMPTS"
    MODIFIES_AND_REPLACES = "MODIFIES_AND_REPLACES"
    GUIDES = "GUIDES"
    DEFINES_TERM = "DEFINES_TERM"


class StagingChunkDelta(BaseModel):
    """Dữ liệu cập nhật từng phần cho một đoạn quy phạm trong vùng đệm staging."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(
        ...,
        description="Đường dẫn phân cấp của đoạn quy phạm cần chỉnh sửa hoặc tạo mới, ví dụ: 'nd_100_2019_nd_cp.c_ii.a_5.c_1.p_a'.",
    )
    verbatim_text: str | None = Field(
        None,
        description="Nội dung văn bản nguyên văn mới của điều khoản (bắt buộc khi tạo mới chunk). Khi cập nhật trường này mà không truyền contextualized_text, hệ thống sẽ tự động ghép lại phả hệ ngữ cảnh với nội dung nguyên văn mới.",
    )
    contextualized_text: str | None = Field(
        None,
        description="Nội dung ngữ cảnh đầy đủ mới sau khi ghép chuỗi phả hệ. Nếu để trống khi cập nhật verbatim_text, hệ thống sẽ tự động bảo lưu phả hệ hiện tại và ghép với văn bản nguyên văn mới.",
    )
    lead_sentence: str | None = Field(
        None,
        description="Câu dẫn đề mới của điều khoản cha.",
    )
    start_line: int | None = Field(
        None,
        ge=1,
        description="Số dòng bắt đầu trong văn bản nguồn tính từ 1.",
    )
    end_line: int | None = Field(
        None,
        ge=1,
        description="Số dòng kết thúc trong văn bản nguồn tính từ 1.",
    )
    metadata: ChunkMetadata | None = Field(
        None,
        description="Siêu dữ liệu ngữ nghĩa cần cập nhật bổ sung vào đoạn quy phạm.",
    )
    effective_date: datetime.date | None = Field(
        None,
        description="Ngày bắt đầu có hiệu lực thi hành của quy phạm.",
    )
    expiration_date: datetime.date | None = Field(
        None,
        description="Ngày hết hiệu lực thi hành của quy phạm.",
    )
    review_status: ChunkReviewStatus | None = Field(
        None,
        description="Trạng thái tiến độ rà soát của Agent đối với đoạn quy phạm: PENDING (chờ rà duyệt) hoặc REVIEWED (đã thẩm định xong). Công cụ stg_commit bắt buộc 100% chunk trong phiên phải là REVIEWED mới cho phép commit.",
    )
    finalization_state: FinalizationState | None = Field(
        None,
        description=FINALIZATION_STATE_DESCRIPTION,
    )
    dangling_dependencies: list[DanglingDependencyRecord] | None = Field(
        None,
        description="Danh sách các điều kiện loại trừ hoặc viện dẫn mở chưa hoàn thiện cần cập nhật.",
    )

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: object) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)


class StagingDeltaReport(BaseModel):
    """Summary of applied chunk mutations and cascaded hierarchical updates."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Document statutory code")
    updated_count: int = Field(..., description="Count of directly patched chunks")
    cascaded_count: int = Field(..., description="Count of descendant chunks whose breadcrumbs were updated")
    removed_count: int = Field(..., description="Count of removed chunk paths")
    total_chunks: int = Field(..., description="Total chunks remaining in session")
    fields_modified: list[str] = Field(
        default_factory=list, description="Unique field names modified across all deltas"
    )


class ReparentPathMapping(BaseModel):
    """Pairwise mapping from old ltree path to new ltree path."""

    old_path: str = Field(..., description="Original ltree path before migration")
    new_path: str = Field(..., description="Transformed ltree path after migration")


class StgReparentResult(BaseModel):
    """Result returned by subtree re-parenting operation."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Statutory document code")
    status: str = Field("SUCCESS", description="Operation status")
    dry_run: bool = Field(False, description="Whether mutation was simulated")
    affected_chunks_count: int = Field(..., description="Total count of chunks whose path was migrated")
    affected_edges_count: int = Field(..., description="Total count of internal edges migrated")
    old_path_prefix: str = Field(..., description="Old prefix searched")
    new_path_prefix: str = Field(..., description="New target prefix")
    sample_mappings: list[ReparentPathMapping] = Field(
        default_factory=list, description="Sample of path mappings (up to 10)"
    )


class StagingMutationRecord(BaseModel):
    """Immutable audit trail entry for staging session transformations."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique mutation record ID")
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="UTC timestamp of mutation",
    )
    actor: str = Field(..., description="'SYSTEM' | 'AGENT' | 'HUMAN:<username>'")
    action_type: str = Field(..., description="Action type code")
    description: str = Field(..., description="Human-readable summary of mutation")
    diff_payload: dict[str, object] | None = Field(default=None, description="Detailed mutation payload")


class StagingSessionSummary(BaseModel):
    """Lightweight summary model for dashboard listing."""

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


class RawTextWindow(BaseModel):
    """Encapsulates a bounded line-window of original statutory source text."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Document statutory code")
    start_line: int = Field(..., ge=1, description="1-indexed starting line number")
    end_line: int = Field(..., ge=1, description="1-indexed ending line number")
    total_lines: int = Field(..., ge=0, description="Total line count of source raw text")
    lines: list[str] = Field(default_factory=list, description="Array of sliced raw lines")
    content: str = Field(..., description="Newline-concatenated text of the window slice")


class StagingGrepHit(BaseModel):
    """Represents a matched chunk hit from in-memory staging session grep."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Hierarchical dot-separated ltree path")
    field_matched: str = Field(..., description="'VERBATIM' | 'CONTEXT' | 'PATH' | 'METADATA'")
    match_snippet: str = Field(..., description="Concise snippet highlighting the matched term")
    verbatim_text: str = Field(..., description="Complete verbatim text of the chunk")
    contextualized_text: str = Field(..., description="Full CPHC synthesized context text")
    char_length: int = Field(..., description="Character count of verbatim text")
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata, description="Chunk metadata payload")


class StagingChunk(BaseModel):
    """Represents a candidate statutory chunk within a staging session."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Hierarchical dot-separated ltree path")
    verbatim_text: str = Field(..., description="Verbatim clause/point text")
    contextualized_text: str = Field(..., description="Synthesized CPHC context text")
    start_line: int = Field(default=1, ge=1, description="1-indexed starting line number in source text")
    end_line: int = Field(default=1, ge=1, description="1-indexed ending line number in source text")
    lead_sentence: str = Field("", description="Inherited lead sentence")
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata, description="Dynamic metadata payload")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    char_length: int = Field(default=0, description="Total character count of verbatim text")
    review_status: ChunkReviewStatus = Field(
        default=ChunkReviewStatus.PENDING,
        description="Chunk review lifecycle status ('PENDING' | 'REVIEWED')",
    )
    finalization_state: FinalizationState = Field(
        default=FinalizationState.UNFINALIZED_OPEN_ENDED,
        description="Semantic legal finalization state ('FINALIZED_*' | 'UNFINALIZED_*')",
    )
    dangling_dependencies: list[DanglingDependencyRecord] = Field(
        default_factory=list,
        description="List of declared open caveats or unlinked dependencies",
    )

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: object) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)

    @model_validator(mode="after")
    def compute_char_length(self) -> StagingChunk:
        if not self.char_length and self.verbatim_text:
            self.char_length = len(self.verbatim_text)
        return self


class StagingEdgeFilter(BaseModel):
    """Bộ lọc xác định các cạnh quan hệ đồ thị cần xóa trong vùng đệm staging."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(
        ...,
        description="Đường dẫn ltree của đoạn quy phạm nguồn, ví dụ: '100_2019_nd_cp.c_ii.a_5.c_3.p_a'.",
    )
    target_path: str | None = Field(
        None,
        description="Đường dẫn ltree của đoạn quy phạm đích nội bộ cần xóa (nếu có).",
    )
    target_external_ref: str | None = Field(
        None,
        description="Chuỗi trích dẫn nguyên văn đầy đủ của quy phạm bên ngoài cần xóa (nếu có).",
    )
    relation_type: RelationType | str | None = Field(
        None,
        description="Loại quan hệ pháp lý cần xóa (ví dụ: 'REFERENCES', 'SANCTIONS'). Nếu để trống, sẽ khớp mọi loại quan hệ với đích đã chỉ định.",
    )
    clear_all_targets: bool = Field(
        default=False,
        description="Cờ xác nhận xóa toàn bộ các cạnh xuất phát từ source_path bất kể đích đến. Mặc định là False để phòng tránh xóa nhầm dữ liệu đồ thị.",
    )

    @model_validator(mode="after")
    def validate_target_safety(self) -> StagingEdgeFilter:

        clean_src = self.source_path.strip() if self.source_path else ""
        if not clean_src:
            raise ValueError("source_path không được để trống")
        self.source_path = validate_ltree_path(clean_src)

        clean_tgt = self.target_path.strip() if self.target_path else None
        clean_ext = self.target_external_ref.strip() if self.target_external_ref else None

        if not clean_tgt and not clean_ext and not self.clear_all_targets:
            raise ValueError(
                f"Thao tác xóa cạnh từ '{self.source_path}' yêu cầu phải chỉ định 'target_path' hoặc 'target_external_ref' "
                "để xác định đúng cạnh cần xóa. Nếu thực sự muốn xóa toàn bộ mọi cạnh xuất phát từ nút này, "
                "bắt buộc phải đặt 'clear_all_targets=True'."
            )

        if clean_tgt:
            self.target_path = validate_ltree_path(clean_tgt)
        else:
            self.target_path = None
        self.target_external_ref = clean_ext
        return self


class StagingEdge(BaseModel):
    """Represents a candidate directed relation edge within a staging session."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(
        ...,
        description="Đường dẫn phân cấp ltree của đoạn quy phạm nguồn phát sinh quan hệ.",
    )
    target_path: str | None = Field(
        None,
        description="Đường dẫn phân cấp ltree của đoạn quy phạm đích trong cùng văn bản hoặc văn bản đã nạp.",
    )
    target_external_ref: str | None = Field(
        None,
        description="Chuỗi viện dẫn pháp lý nguyên văn đầy đủ tới văn bản bên ngoài chưa nạp vào CSDL (ví dụ: 'Điều 5 Luật Giao thông đường bộ 2008'). Tuyệt đối không tự bịa đặt mã ltree giả khi văn bản chưa được nạp.",
    )
    relation_type: RelationType = Field(
        default=RelationType.REFERENCES,
        description="Loại quan hệ pháp lý có hướng giữa hai quy phạm.",
    )
    citation_text: str | None = Field(
        None,
        description="Đoạn văn bản nguyên văn trích dẫn làm căn cứ xác lập quan hệ (ví dụ: 'theo quy định tại Điều 5').",
    )
    metadata: EdgeMetadata = Field(
        default_factory=EdgeMetadata,
        description="Siêu dữ liệu ngữ nghĩa bổ trợ cho cạnh quan hệ (điều kiện condition, ghi chú notes, ngày hiệu lực).",
    )

    @model_validator(mode="after")
    def validate_edge_targets(self) -> StagingEdge:

        clean_src = self.source_path.strip() if self.source_path else ""
        if not clean_src:
            raise ValueError("source_path không được để trống")
        self.source_path = validate_ltree_path(clean_src)

        clean_tgt = self.target_path.strip() if self.target_path else None
        clean_ext = self.target_external_ref.strip() if self.target_external_ref else None

        if not clean_tgt and not clean_ext:
            raise ValueError(
                f"Cạnh quan hệ đồ thị xuất phát từ '{self.source_path}' bắt buộc phải có ít nhất một đích đến: "
                "'target_path' (cho liên kết nội bộ) hoặc 'target_external_ref' (cho viện dẫn văn bản ngoài)."
            )

        if clean_tgt:
            self.target_path = validate_ltree_path(clean_tgt)
        else:
            self.target_path = None

        self.target_external_ref = clean_ext
        return self
