"""Output schemas and data transfer models for Vietnamese Traffic Law MCP tools."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingGrepHit,
)


def extract_metadata_dict(raw: Any) -> dict[str, Any]:
    """Helper to safely coerce database metadata column into Python dict."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
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
    metadata: dict[str, Any] = Field(default_factory=dict)
    effective_date: str
    expiration_date: str | None = None
    score: float
    # The magnitudes the fused score is computed from and then discards.
    dense_similarity: float = 0.0
    keyword_matched: bool = True
    # Set when a cross-encoder reordered these hits. `score` stays the fused
    # rank so the two orderings can be compared.
    rerank_score: float | None = None


# Below this cosine similarity the answer is usually unrelated to the question.
# Highest cut with 0% false alarms: the answerable minimum measured 0.861.
LOW_SIMILARITY: float = 0.86

# Cross-encoder logit below which the reranker's own best candidate is a
# warning rather than an answer.
LOW_RERANK: float = -1.0

# How many candidates the cross-encoder is given when reranking is on.
RERANK_POOL: int = 10


class AddMetadataResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    annotation_id: str
    chunk_id: str
    recorded_at: str
    total_annotations: int


class HybridSearchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_hits: int
    hits: list[SearchHit]
    temporal_as_of: str | None = None
    # False when the query carries no tone marks. The corpus is embedded from
    # accented text, so cosine is depressed for reasons other than relevance.
    dense_is_informative: bool = True
    # The text the sparse ranker actually matched on, which is not the text the
    # caller typed once colloquial wording has been expanded.
    expanded_query: str = ""

    # A plain @property is invisible to `model_dump`, so this was computed on
    # the server and then dropped before the agent ever saw it.
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
    metadata: dict[str, Any] = Field(default_factory=dict)
    relative_depth: int = 0


class HierarchicalNavigateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    anchor_path: str
    direction: str
    total_nodes: int
    nodes: list[HierarchyNode]


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

    source_chunk_id: str
    total_paths: int
    paths: list[GraphTraversalStep]


class GraphEdgeWriteResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    edge_id: str
    status: str
    relation_type: str


class CorpusValidateResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    total_documents: int
    total_chunks: int
    total_edges: int
    orphan_chunks_count: int = 0
    issues: list[str] = Field(default_factory=list)


class StgPreviewHit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    lead_sentence: str
    preview_text: str
    char_length: int = 0
    is_truncated: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


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


class StgFinalizeResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Số hiệu văn bản")
    status: str = Field("SUCCESS", description="Trạng thái thực thi")
    finalized_count: int = Field(..., description="Số lượng chunk vừa được chốt")
    pending_remaining: int = Field(..., description="Số lượng chunk còn lại chưa chốt")
    paths: list[str] = Field(default_factory=list, description="Danh sách các đường dẫn đã chốt")
