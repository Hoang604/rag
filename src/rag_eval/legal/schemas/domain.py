from __future__ import annotations

import datetime
from enum import Enum
from typing import Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from rag_eval.legal.text import (
    parse_flexible_date,
    validate_ltree_path,
)


class ContextType(str, Enum):
    """Semantic context classification determining relational dependency."""

    SELF_CONTAINED = "SELF_CONTAINED"
    REQUIRES_EXTERNAL_CONTEXT = "REQUIRES_EXTERNAL_CONTEXT"


CONTEXT_TYPE_DOCS: dict[ContextType, str] = {
    ContextType.SELF_CONTAINED: "Quy phạm tự thân trọn vẹn, không có viện dẫn hoặc điều kiện phụ thuộc ngoại vi.",
    ContextType.REQUIRES_EXTERNAL_CONTEXT: "Quy phạm có chứa viện dẫn hoặc phụ thuộc vào điều khoản, quy phạm khác.",
}


class FinalizationState(str, Enum):
    """Semantic legal completeness lifecycle status for statutory chunks."""

    FINALIZED_SELF_CONTAINED = "FINALIZED_SELF_CONTAINED"
    FINALIZED_FULLY_LINKED = "FINALIZED_FULLY_LINKED"
    UNFINALIZED_PENDING_EXTERNAL = "UNFINALIZED_PENDING_EXTERNAL"
    UNFINALIZED_OPEN_ENDED = "UNFINALIZED_OPEN_ENDED"


FINALIZATION_STATE_DOCS: dict[FinalizationState, str] = {
    FinalizationState.FINALIZED_SELF_CONTAINED: "tự thân trọn vẹn, không có viện dẫn",
    FinalizationState.FINALIZED_FULLY_LINKED: "có viện dẫn và đã nối cạnh quan hệ đồ thị đầy đủ",
    FinalizationState.UNFINALIZED_PENDING_EXTERNAL: "còn viện dẫn ngoài chưa nạp",
    FinalizationState.UNFINALIZED_OPEN_ENDED: "còn dẫn chiếu mở chưa khép kín",
}

assert set(FINALIZATION_STATE_DOCS.keys()) == set(FinalizationState), (
    "Thiếu mô tả cho trạng thái FinalizationState mới!"
)

FINALIZATION_STATE_DESCRIPTION = (
    "Trạng thái cấu trúc ngữ nghĩa pháp lý của quy phạm: "
    + "; ".join(f"{state.value} ({desc})" for state, desc in FINALIZATION_STATE_DOCS.items())
    + ". Quy tắc bất biến: Chunk bắt buộc phải được phân loại context_type ('SELF_CONTAINED' hoặc 'REQUIRES_EXTERNAL_CONTEXT') "
    "kèm quan hệ đồ thị tương ứng tại stg_patch trước khi chốt nghiệm thu bằng stg_finalize_chunks."
)

NodeType = Literal[
    "DOCUMENT",
    "CHAPTER",
    "SECTION",
    "ARTICLE",
    "CLAUSE",
    "POINT",
    "APPENDIX",
    "APPENDIX_ITEM",
]

_NODE_TYPE_CHOICES = ", ".join(get_args(NodeType))


class StatutoryRelationType(str, Enum):
    """Authoritative statutory relation type catalog in Vietnamese jurisprudence."""

    MODIFIES_AND_REPLACES = "MODIFIES_AND_REPLACES"
    SANCTIONS = "SANCTIONS"
    OVERRIDES = "OVERRIDES"
    EXEMPTS = "EXEMPTS"
    GUIDES = "GUIDES"
    DEFINES_TERM = "DEFINES_TERM"
    REFERENCES = "REFERENCES"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    SEE_ALSO = "SEE_ALSO"


class HierarchicalDirection(str, Enum):
    """Navigation directions across the statutory LTREE hierarchy."""

    FULL_ARTICLE = "FULL_ARTICLE"
    CHILDREN = "CHILDREN"
    PARENT_CHAIN = "PARENT_CHAIN"
    SIBLINGS = "SIBLINGS"


HIERARCHICAL_DIRECTION_DOCS: dict[str, str] = {
    "FULL_ARTICLE": "Mở rộng trọn vẹn toàn bộ các khoản và điểm thuộc Điều luật chứa nút này.",
    "CHILDREN": "Lấy toàn bộ các nút con trực tiếp cấp dưới.",
    "PARENT_CHAIN": "Truy ngược chuỗi phả hệ cha lên tới đỉnh văn bản.",
    "SIBLINGS": "Lấy các nút anh chị em cùng cấp cha.",
}

HIERARCHICAL_DIRECTION_DESCRIPTION: str = (
    "Hướng điều hướng cây phân cấp: "
    "'FULL_ARTICLE' (mở rộng toàn văn Điều chứa nút hiện tại), "
    "'CHILDREN' (lấy các nút con trực tiếp), "
    "'PARENT_CHAIN' (lấy chuỗi các nút cha tới gốc), "
    "'SIBLINGS' (lấy các nút cùng cấp)."
)

GraphDirection = Literal["OUTGOING", "INCOMING", "BOTH"]
GrepMatchTier = Literal[
    "BODY",
    "ARTICLE_HEADING",
    "SECTION_HEADING",
    "CHAPTER_HEADING",
    "PATH",
    "HEADING_HINT",
    "BODY_HINT",
]


class ChunkReviewStatus(str, Enum):
    """Review lifecycle status for an individual statutory chunk."""

    PENDING = "PENDING"
    REVIEWED = "REVIEWED"


class StagingStatus(str, Enum):
    """Lifecycle statuses for statutory staging sessions."""

    DRAFT = "DRAFT"
    AGENT_COMMITTED = "AGENT_COMMITTED"
    APPROVED = "APPROVED"
    PROMOTED = "PROMOTED"
    AMENDMENT = "AMENDMENT"


class ChunkMetadata(BaseModel):
    """Structured semantic metadata for statutory provisions."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    node_type: NodeType | None = Field(
        default=None,
        description=f"Cấp bậc phân cấp của đoạn quy phạm ({_NODE_TYPE_CHOICES}).",
    )
    index_label: str | None = Field(
        default=None,
        description="Nhãn định danh hiển thị của điều khoản, ví dụ: 'Điều 5', 'Khoản 1', 'Điểm a'.",
    )
    chapter_title: str | None = Field(
        default=None,
        description="Tiêu đề chương chứa điều khoản.",
    )
    section_title: str | None = Field(
        default=None,
        description="Tiêu đề mục chứa điều khoản.",
    )
    article_title: str | None = Field(
        default=None,
        description="Tiêu đề điều luật chứa đoạn quy phạm.",
    )


class DocumentMetadata(BaseModel):
    """Structured statutory metadata for legal documents."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    amends: str | None = None
    consolidates: list[str] | None = None
    in_force: bool | None = None
    superseded_by: str | None = None
    source_urls: list[str] | None = None
    doc_type: str | None = None
    issuing_authority: str | None = None
    signer: str | None = None


class UnresolvedReference(BaseModel):
    """Canonical model for open-ended or unresolved external statutory dependencies."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(
        ...,
        description="Đường dẫn phân cấp ltree của chunk chứa tham chiếu nguồn.",
    )
    dependency_text: str = Field(
        ...,
        description="Nguyên văn câu viện dẫn hoặc điều kiện loại trừ pháp lý chưa được liên kết nội bộ.",
    )
    dependency_type: str = Field(
        "OPEN_ENDED",
        description="Hình thức phụ thuộc: OPEN_ENDED hoặc EXTERNAL_CITATION.",
    )
    char_start: int | None = Field(
        default=None,
        exclude=True,
        description="Vị trí bắt đầu trong văn bản chunk (nội bộ hệ thống tự tính từ verbatim_text, Agent không cần cung cấp).",
    )
    char_end: int | None = Field(
        default=None,
        exclude=True,
        description="Vị trí kết thúc trong văn bản chunk (nội bộ hệ thống tự tính từ verbatim_text, Agent không cần cung cấp).",
    )
    reason: str = Field(
        "DOC_NOT_IN_CORPUS",
        description="Lý do tham chiếu chưa được liên kết nội bộ.",
    )

    @model_validator(mode="after")
    def validate_span_geometry(self) -> UnresolvedReference:
        if (self.char_start is None and self.char_end is not None) or (
            self.char_start is not None and self.char_end is None
        ):
            raise ValueError("char_start và char_end phải cùng có giá trị hoặc cùng là None.")

        if (
            self.char_start is not None
            and self.char_end is not None
            and (self.char_start < 0 or self.char_end <= self.char_start)
        ):
            raise ValueError("char_end phải lớn hơn char_start và char_start >= 0.")

        return self


class UnresolvedReferenceDelta(BaseModel):
    """Client and agent mutation payload for unresolved dependencies without internal char offsets."""

    model_config = ConfigDict(extra="forbid")

    dependency_text: str = Field(
        ...,
        description="Nguyên văn câu viện dẫn hoặc điều kiện loại trừ pháp lý trong chunk.",
    )
    dependency_type: str = Field(
        "OPEN_ENDED",
        description="Hình thức phụ thuộc: OPEN_ENDED hoặc EXTERNAL_CITATION.",
    )
    reason: str = Field(
        "DOC_NOT_IN_CORPUS",
        description="Lý do tham chiếu chưa được liên kết nội bộ.",
    )


class RelationEdge(BaseModel):
    """Canonical directed relation edge in statutory knowledge graph."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(
        ...,
        description="Đường dẫn phân cấp ltree của đoạn quy phạm nguồn.",
    )
    target_path: str = Field(
        ...,
        description="Đường dẫn phân cấp ltree của đoạn quy phạm đích.",
    )
    relation_type: StatutoryRelationType = Field(
        ...,
        description="Loại quan hệ pháp lý có hướng giữa hai quy phạm.",
    )
    citation_text: str | None = Field(
        None,
        description="Đoạn văn bản nguyên văn trích dẫn làm căn cứ xác lập quan hệ.",
    )

    @model_validator(mode="after")
    def validate_edge_targets(self) -> RelationEdge:
        clean_src = self.source_path.strip() if self.source_path else ""
        if not clean_src:
            raise ValueError("source_path không được để trống")
        self.source_path = validate_ltree_path(clean_src)

        clean_tgt = self.target_path.strip() if self.target_path else ""
        if not clean_tgt:
            raise ValueError("target_path không được để trống")
        self.target_path = validate_ltree_path(clean_tgt)

        if self.source_path == self.target_path:
            raise ValueError(f"Cạnh quan hệ không được tự trỏ tới chính nó: '{self.source_path}'")

        return self


class RelationEdgeFilter(BaseModel):
    """Canonical filter criteria for selecting or removing relation edges."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(
        ...,
        description="Đường dẫn ltree của đoạn quy phạm nguồn.",
    )
    target_path: str | None = Field(
        None,
        description="Đường dẫn ltree của đoạn quy phạm đích nội bộ.",
    )
    relation_type: StatutoryRelationType | str | None = Field(
        None,
        description="Loại quan hệ pháp lý cần lọc.",
    )
    clear_all_targets: bool = Field(
        default=False,
        description="Cờ xác nhận chọn/xóa toàn bộ các cạnh xuất phát từ source_path.",
    )

    @model_validator(mode="after")
    def validate_target_safety(self) -> RelationEdgeFilter:
        clean_src = self.source_path.strip() if self.source_path else ""
        if not clean_src:
            raise ValueError("source_path không được để trống")
        self.source_path = validate_ltree_path(clean_src)

        clean_tgt = self.target_path.strip() if self.target_path else None

        if not clean_tgt and not self.clear_all_targets:
            raise ValueError(
                f"Bộ lọc cạnh từ '{self.source_path}' yêu cầu chỉ định 'target_path' hoặc 'clear_all_targets=True'."
            )

        if clean_tgt:
            self.target_path = validate_ltree_path(clean_tgt)
        else:
            self.target_path = None
        return self


class StatutoryChunk(BaseModel):
    """Canonical representation of a statutory chunk across ingestion and storage."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Đường dẫn phân cấp ltree")
    verbatim_text: str = Field(..., description="Nội dung văn bản nguyên văn")
    contextualized_text: str = Field(..., description="Nội dung ngữ cảnh đầy đủ")
    start_line: int = Field(default=1, ge=1, description="Dòng bắt đầu tính từ 1")
    end_line: int = Field(default=1, ge=1, description="Dòng kết thúc tính từ 1")
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata, description="Siêu dữ liệu")
    effective_date: datetime.date = Field(..., description="Ngày có hiệu lực")
    expiration_date: datetime.date | None = Field(None, description="Ngày hết hiệu lực")
    review_status: ChunkReviewStatus = Field(
        default=ChunkReviewStatus.PENDING,
        description="Trạng thái rà soát",
    )
    finalization_state: FinalizationState = Field(
        default=FinalizationState.UNFINALIZED_OPEN_ENDED,
        description=FINALIZATION_STATE_DESCRIPTION,
    )
    dangling_dependencies: list[UnresolvedReference] = Field(
        default_factory=list,
        description="Danh sách viện dẫn mở hoặc chưa liên kết",
    )
    context_type: ContextType | None = Field(
        default=None,
        description="Phân loại ngữ nghĩa: SELF_CONTAINED (tự chứa) hoặc REQUIRES_EXTERNAL_CONTEXT (cần liên kết ngoài).",
    )
    justification: str | None = Field(
        default=None,
        description="Căn cứ thẩm định: giải trình vì sao tự chứa hoặc tóm tắt các điểm cần liên kết.",
    )

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: object) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)


class StagingChunkDelta(BaseModel):
    """Client and agent mutation payload with review status strictly forbidden."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="Đường dẫn phân cấp ltree")
    verbatim_text: str | None = Field(None, description="Nội dung nguyên văn mới")
    contextualized_text: str | None = Field(None, description="Nội dung ngữ cảnh mới")
    start_line: int | None = Field(None, ge=1, description="Dòng bắt đầu")
    end_line: int | None = Field(None, ge=1, description="Dòng kết thúc")
    metadata: ChunkMetadata | None = Field(None, description="Siêu dữ liệu mới")
    effective_date: datetime.date | None = Field(None, description="Ngày hiệu lực mới")
    expiration_date: datetime.date | None = Field(None, description="Ngày hết hiệu lực mới")
    dangling_dependencies: list[UnresolvedReferenceDelta] | None = Field(
        None, description="Danh sách phụ thuộc mới"
    )
    context_type: ContextType | None = Field(
        None, description="Phân loại ngữ nghĩa: SELF_CONTAINED hoặc REQUIRES_EXTERNAL_CONTEXT"
    )
    justification: str | None = Field(
        None, description="Căn cứ thẩm định giải trình tính tự chứa hoặc tóm tắt phụ thuộc"
    )

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: object) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)


ChunkDelta = StagingChunkDelta


class TreeNode(BaseModel):
    """Canonical tree node for hierarchy navigation and canvas visualization."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Đường dẫn phân cấp ltree")
    doc_code: str = Field("", description="Số hiệu văn bản")
    label: str = Field("", description="Nhãn hiển thị")
    node_type: str = Field("", description="Cấp bậc phân cấp")
    verbatim_text: str = Field("", description="Nội dung nguyên văn")
    contextualized_text: str = Field("", description="Nội dung ngữ cảnh")
    start_line: int = Field(default=1, ge=1, description="Dòng bắt đầu")
    end_line: int = Field(default=1, ge=1, description="Dòng kết thúc")
    metadata: dict[str, object] = Field(default_factory=dict, description="Siêu dữ liệu")
    effective_date: datetime.date = Field(..., description="Ngày hiệu lực")
    expiration_date: datetime.date | None = Field(None, description="Ngày hết hiệu lực")
    review_status: str = Field(default="PENDING", description="Trạng thái rà soát")
    context_type: str | None = Field(default=None, description="Phân loại ngữ nghĩa")
    justification: str | None = Field(default=None, description="Căn cứ thẩm định")
    relative_depth: int = Field(default=0, description="Độ sâu tương đối")
    children: list[TreeNode] = Field(default_factory=list, description="Các nút con")

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: object) -> datetime.date | None:
        return parse_flexible_date(v) if v is not None else None


class GraphTraversalStep(BaseModel):
    """Step in a knowledge graph path traversal."""

    model_config = ConfigDict(extra="ignore")

    source_path: str
    target_path: str
    relation_type: StatutoryRelationType | str
    citation_text: str | None = None
    depth: int
    target_text: str | None = None
