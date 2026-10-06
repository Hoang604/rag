from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from rag_eval.legal.schemas.domain import (
    FinalizationState,
    GraphDirection,
    GraphTraversalStep,
    GrepScope,
    TreeNode,
)
from rag_eval.legal.text import address_of_path

_LOW_SIMILARITY: float = 0.86
_LOW_RERANK: float = -1.0
RERANK_POOL: int = 10


class SearchHit(BaseModel):
    """Authoritative canonical model for search, grep, and traversal hits."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str
    doc_title: str
    path: str
    start_line: int
    end_line: int
    verbatim_text: str
    contextualized_text: str
    metadata: dict[str, object] = Field(default_factory=dict)
    effective_date: datetime.date
    expiration_date: datetime.date | None = None
    finalization_state: FinalizationState = FinalizationState.FINALIZED_SELF_CONTAINED
    score: float = Field(default=0.0, exclude=True)
    dense_rank: int | None = Field(default=None, exclude=True)
    sparse_rank: int | None = Field(default=None, exclude=True)
    dense_similarity: float = Field(default=0.0, exclude=True)
    keyword_matched: bool = Field(default=True, exclude=True)
    rerank_score: float | None = Field(default=None, exclude=True)
    rank: int = 1
    is_table: bool = False
    table_summary: str | None = None

    @computed_field
    @property
    def address(self) -> str:
        addr = address_of_path(self.path)
        parts: list[str] = []
        if addr.dieu:
            parts.append(f"Điều {addr.dieu}")
        if addr.khoan:
            parts.append(f"Khoản {addr.khoan}")
        if addr.diem:
            parts.append(f"Điểm {addr.diem}")
        return ", ".join(parts) if parts else ""


class SearchResult(BaseModel):
    """Unified canonical search response."""

    model_config = ConfigDict(extra="ignore")

    query: str = ""
    hits: list[SearchHit]
    total_hits: int = 0
    violation_date: str = ""
    dense_is_informative: bool = True
    expanded_query: str = ""
    elapsed_ms: float = 0.0

    @computed_field
    @property
    def confidence(self) -> str:
        if not self.hits:
            return "none"
        if not any(hit.keyword_matched for hit in self.hits):
            return "none"
        scores = [h.rerank_score for h in self.hits if h.rerank_score is not None]
        if scores and max(scores) < _LOW_RERANK:
            return "low"
        if not self.dense_is_informative:
            return "high"
        if max(hit.dense_similarity for hit in self.hits) < _LOW_SIMILARITY:
            return "low"
        return "high"



class GrepRequest(BaseModel):
    """Request payload for substring or regex grep across chunks."""

    model_config = ConfigDict(extra="ignore")

    pattern: str = Field(..., description="Query substring or regex pattern")
    is_regex: bool = Field(False, description="Whether pattern is a regular expression")
    case_sensitive: bool = Field(False, description="Case-sensitive matching")
    search_in: GrepScope = Field("ALL", description="Target field: ALL, VERBATIM, CONTEXT, PATH, METADATA")
    limit: int = Field(50, description="Max matches to return")


class GrepResult(BaseModel):
    """Canonical grep matches response."""

    model_config = ConfigDict(extra="ignore")

    pattern: str
    is_regex: bool = False
    total_matches: int = 0
    returned: int = 0
    truncated: bool = False
    doc_code: str | None = None
    matches: list[SearchHit] = Field(default_factory=list)


class HierarchicalNavigateResult(BaseModel):
    """Result of hierarchical navigation across provisions."""

    model_config = ConfigDict(extra="ignore")

    anchor_path: str = Field(..., description="Đường dẫn ltree nút gốc")
    direction: str = Field(..., description="Hướng điều hướng")
    total_nodes: int = Field(..., description="Tổng số nút trả về")
    nodes: list[TreeNode] = Field(default_factory=list, description="Danh sách nút")


class GraphTraverseRequest(BaseModel):
    """Request payload to traverse the relational graph starting from a node."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(..., description="LTree path of source chunk")
    nav_direction: GraphDirection = Field(
        default="OUTGOING", description="Direction: OUTGOING | INCOMING | BOTH"
    )
    depth_limit: int = Field(default=2, ge=1, le=5, description="Max traversal depth")
    filter_relations: list[str] | None = None


class GraphTraverseResult(BaseModel):
    """Result of graph traversal."""

    model_config = ConfigDict(extra="ignore")

    source_path: str
    total_paths: int
    paths: list[GraphTraversalStep] = Field(default_factory=list)


class RawTextResult(BaseModel):
    """Canonical result for raw statutory text."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Document statutory code")
    title: str = Field("", description="Document title")
    raw_text: str = Field(..., description="Full or window-sliced raw statutory text")
    start_line: int = Field(1, ge=1, description="1-indexed starting line number")
    end_line: int = Field(1, ge=1, description="1-indexed ending line number")
    total_lines: int = Field(0, ge=0, description="Total line count of source raw text")
    chunks_count: int = Field(0, ge=0, description="Total parsed chunks count")
