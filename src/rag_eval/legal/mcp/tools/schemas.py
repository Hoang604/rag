from __future__ import annotations

import json
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class HierarchicalDirection(str, Enum):
    """Hướng điều hướng trên cây phân cấp văn bản pháp luật."""

    FULL_ARTICLE = "FULL_ARTICLE"
    CHILDREN = "CHILDREN"
    PARENT_CHAIN = "PARENT_CHAIN"
    SIBLINGS = "SIBLINGS"


HIERARCHICAL_DIRECTION_DOCS: dict[HierarchicalDirection, str] = {
    HierarchicalDirection.FULL_ARTICLE: (
        "Mở rộng trọn vẹn phạm vi Điều luật chứa nút mục tiêu (từ Điều cha kéo xuống mọi Khoản/Điểm). "
        "Chỉ áp dụng cho Điều, Khoản hoặc Điểm; không áp dụng cho Chương/Mục."
    ),
    HierarchicalDirection.CHILDREN: "Lấy các phân vị con trực tiếp (cấp nlevel + 1).",
    HierarchicalDirection.PARENT_CHAIN: "Lấy chuỗi phả hệ tổ tiên từ Văn bản gốc xuống đến nút cha trực tiếp.",
    HierarchicalDirection.SIBLINGS: "Lấy các nút anh em cùng cấp dưới cùng một nút cha.",
}

assert set(HIERARCHICAL_DIRECTION_DOCS.keys()) == set(HierarchicalDirection), (
    "Thiếu mô tả cho hướng điều hướng HierarchicalDirection mới!"
)

HIERARCHICAL_DIRECTION_DESCRIPTION = (
    "Hướng điều hướng trên cây phân cấp: "
    + "; ".join(f"'{k.value}': {v}" for k, v in HIERARCHICAL_DIRECTION_DOCS.items())
)

GraphDirection = Literal["OUTGOING", "INCOMING", "BOTH"]
StgGrepScope = Literal["ALL", "VERBATIM", "CONTEXT", "PATH", "METADATA"]
StagingStatusFilter = Literal[
    "DRAFT", "AGENT_COMMITTED", "APPROVED", "PROMOTED", "AMENDMENT", ""
]
RelationTypeFilter = Literal[
    "REFERENCES",
    "SANCTIONS",
    "OVERRIDES",
    "EXEMPTS",
    "MODIFIES_AND_REPLACES",
    "GUIDES",
    "DEFINES_TERM",
    "",
]
BacklogFinalizationStateFilter = Literal[
    "UNFINALIZED_PENDING_EXTERNAL", "UNFINALIZED_OPEN_ENDED", ""
]

from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingGrepHit,
)
from rag_eval.legal.ingestion.staging.models import (
    ChunkReviewStatus,
    StagingSessionSummary,
)
from rag_eval.legal.schemas import FinalizationState


def extract_metadata_dict(raw: object) -> dict[str, object]:
    """Helper to safely coerce database metadata column into Python dict."""
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items()}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return {str(k): v for k, v in parsed.items()} if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    doc_code: str
    doc_title: str
    path: str
    verbatim_text: str
    contextualized_text: str
    metadata: dict[str, object] = Field(default_factory=dict)
    effective_date: str
    expiration_date: str | None = None
    score: float
    dense_similarity: float = 0.0
    keyword_matched: bool = True
    rerank_score: float | None = None


LOW_SIMILARITY: float = 0.86

LOW_RERANK: float = -1.0

RERANK_POOL: int = 10


class HybridSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_hits: int
    hits: list[SearchHit]
    temporal_as_of: str | None = None
    dense_is_informative: bool = True
    expanded_query: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def confidence(self) -> str:
        """Reports how much the caller should trust these hits.

        Three signals, each catching a failure the others miss.

        "none" means the keyword side matched nothing at all, which over 400
        answerable questions was wrong 0 times and caught 25 of 25 meaningless
        ones.

        A very negative cross-encoder score means the reranker judged even its
        best candidate irrelevant. This catches the case the other two cannot:
        a question in this domain whose answer is outside this corpus. The two
        distributions overlap, so this is a warning and never a suppression.

        "low" is also the softer cosine signal, withheld where cosine is known
        to be depressed for reasons other than relevance: unaccented queries
        were 100% of the false warnings before this exception.
        """
        if not self.hits:
            return "none"
        if not any(hit.keyword_matched for hit in self.hits):
            return "none"
        scores = [h.rerank_score for h in self.hits if h.rerank_score is not None]
        if scores and max(scores) < LOW_RERANK:
            return "low"
        if not self.dense_is_informative:
            return "high"
        if max(hit.dense_similarity for hit in self.hits) < LOW_SIMILARITY:
            return "low"
        return "high"


class VerbatimGrepResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pattern: str
    is_regex: bool
    total_matches: int
    """Uncapped number of matching chunks in the corpus, not the number returned."""
    returned: int
    truncated: bool
    """True when total_matches exceeds the requested limit."""
    matches: list[SearchHit]


class HierarchyNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    path: str
    doc_code: str
    verbatim_text: str
    contextualized_text: str
    metadata: dict[str, object] = Field(default_factory=dict)
    relative_depth: int = Field(
        default=0,
        description="Độ sâu tương đối so với nút neo gốc (âm: tổ tiên, 0: cùng cấp hoặc chính nút neo, dương: con cháu)",
    )


class HierarchicalNavigateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    anchor_path: str = Field(..., description="Đường dẫn ltree của nút gốc làm mốc điều hướng")
    direction: str = Field(..., description="Hướng điều hướng đã thực hiện")
    total_nodes: int = Field(..., description="Tổng số nút quy phạm trả về")
    nodes: list[HierarchyNode] = Field(
        default_factory=list,
        description="Danh sách phẳng các nút quy phạm được sắp xếp theo đúng thứ tự đọc của văn bản",
    )


class GraphTraversalStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    edge_id: str
    source_chunk_id: str
    target_chunk_id: str | None
    target_external_ref: str | None
    relation_type: str
    citation_text: str | None
    depth: int
    target_path: str | None = None
    target_text: str | None = None


class GraphTraverseResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_path: str
    total_paths: int
    paths: list[GraphTraversalStep]



class StgPreviewHit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    lead_sentence: str
    preview_text: str
    char_length: int = 0
    is_truncated: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class StgPreviewResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    title: str
    total_chunks: int
    total_edges: int
    total_matched: int = 0
    limit: int = 50
    offset: int = 0
    has_more: bool = False
    chunks: list[StgPreviewHit]


class StgGetChunkResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    chunk: StagingChunk


class StgGetRawResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    start_line: int
    end_line: int
    total_lines: int
    content: str


class StgGrepResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    pattern: str
    is_regex: bool
    total_matches: int
    matches: list[StagingGrepHit]


class StgPatchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    status: str = "SUCCESS"
    updated_count: int = 0
    cascaded_count: int = 0
    removed_count: int = 0
    total_chunks_after_patch: int
    fields_modified: list[str] = Field(default_factory=list)


class StgAddEdgesResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    status: str
    total_edges: int


class StgCommitResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str
    status: str = "AGENT_COMMITTED"
    total_chunks: int
    total_edges: int
    committed_at: str
    message: str


class ChunkProgressStats(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_chunks: int = Field(..., description="Tổng số chunk trong văn bản")
    finalized_count: int = Field(..., description="Số chunk đã chốt hoàn tất")
    pending_count: int = Field(..., description="Số chunk còn chờ rà soát")
    progress_percent: float = Field(..., description="Tỷ lệ tiến độ (%)")


class StgPollPendingResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Số hiệu văn bản")
    progress: ChunkProgressStats = Field(..., description="Thống kê tiến độ rà soát")
    limit: int = Field(..., description="Giới hạn số chunk trả về trong đợt này")
    has_more: bool = Field(..., description="Còn chunk chưa chốt hay không")
    chunks: list[StagingChunk] = Field(..., description="Danh sách các chunk chờ xử lý")


class ChunkFinalizeStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Đường dẫn ltree của đoạn quy phạm")
    review_status: ChunkReviewStatus = Field(..., description="Trạng thái rà soát (REVIEWED)")
    finalization_state: FinalizationState = Field(
        ..., description="Trạng thái hoàn thiện pháp lý được tự động suy diễn"
    )


class StgFinalizeResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Số hiệu văn bản")
    status: str = Field("SUCCESS", description="Trạng thái thực thi")
    finalized_count: int = Field(..., description="Số lượng chunk vừa được chốt")
    pending_remaining: int = Field(..., description="Số lượng chunk còn lại chưa chốt")
    paths: list[str] = Field(default_factory=list, description="Danh sách các đường dẫn đã chốt")
    results: list[ChunkFinalizeStatus] = Field(
        default_factory=list,
        description="Chi tiết trạng thái pháp lý được suy diễn tự động của từng chunk",
    )


class StgReopenResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Số hiệu văn bản")
    status: str = Field("AMENDMENT", description="Trạng thái phiên làm việc sau khi mở lại")
    total_chunks: int = Field(..., description="Tổng số đoạn quy phạm trong phiên làm việc")
    reopened_at: str = Field(..., description="Thời điểm mở lại phiên làm việc (ISO 8601)")
    message: str = Field(..., description="Thông điệp kết quả")


class StgRemoveEdgeResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Số hiệu văn bản")
    status: str = Field("SUCCESS", description="Trạng thái thực thi")
    removed_count: int = Field(default=1, description="Số lượng cạnh quan hệ đã xóa")
    total_edges: int = Field(..., description="Tổng số cạnh quan hệ còn lại")
    message: str = Field(..., description="Thông điệp kết quả")


class StgListSessionsResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_sessions: int = Field(..., description="Tổng số phiên làm việc trong staging")
    sessions: list[StagingSessionSummary] = Field(default_factory=list, description="Danh sách tóm tắt các phiên làm việc")


class DanglingBacklogItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    doc_code: str
    path: str
    finalization_state: str
    verbatim_text: str
    dependency_text: str | None = None
    dependency_type: str | None = None
    suggested_target_doc: str | None = None


class ChunkBacklogResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_unfinalized: int
    returned: int
    items: list[DanglingBacklogItem]


CorpusBacklogResult = ChunkBacklogResult
