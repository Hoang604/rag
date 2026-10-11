from __future__ import annotations

from enum import Enum
from typing import Final

from pydantic import (
    BaseModel,
    ConfigDict,
)


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


STATUTORY_RELATION_DESCRIPTIONS: Final[dict[StatutoryRelationType, str]] = {
    StatutoryRelationType.MODIFIES_AND_REPLACES: "Sửa đổi, bổ sung hoặc thay thế quy định",
    StatutoryRelationType.SANCTIONS: "Quy định chế tài xử phạt hành vi vi phạm",
    StatutoryRelationType.OVERRIDES: "Áp dụng ưu tiên khi có xung đột quy phạm",
    StatutoryRelationType.EXEMPTS: "Miễn trừ hoặc ngoại lệ đối với quy định chung",
    StatutoryRelationType.GUIDES: "Hướng dẫn chi tiết thi hành quy định",
    StatutoryRelationType.DEFINES_TERM: "Giải thích từ ngữ, định nghĩa thuật ngữ pháp lý",
    StatutoryRelationType.REFERENCES: "Dẫn chiếu hoặc viện dẫn đến quy định khác",
    StatutoryRelationType.CONFLICTS_WITH: "Mâu thuẫn hoặc xung đột quy phạm",
    StatutoryRelationType.SEE_ALSO: "Liên quan hoặc xem thêm về mặt nội dung",
}

assert set(STATUTORY_RELATION_DESCRIPTIONS) == set(StatutoryRelationType), (
    f"Thiếu description cho StatutoryRelationType: {set(StatutoryRelationType) - set(STATUTORY_RELATION_DESCRIPTIONS)}"
)


def format_statutory_relation_docs() -> str:
    return ", ".join(f"'{k.value}' ({desc})" for k, desc in STATUTORY_RELATION_DESCRIPTIONS.items())


class GraphDirection(str, Enum):
    """Direction for traversing statutory reference graph."""

    OUTGOING = "OUTGOING"
    INCOMING = "INCOMING"
    BOTH = "BOTH"


GRAPH_DIRECTION_DESCRIPTIONS: Final[dict[GraphDirection, str]] = {
    GraphDirection.OUTGOING: "Các liên kết do nút này trỏ tới (viện dẫn nằm trong nút nguồn)",
    GraphDirection.INCOMING: "Các quy định khác trỏ tới nút này (viện dẫn nằm trong nút đích)",
    GraphDirection.BOTH: "Duyệt liên kết theo cả hai hướng (cả trỏ tới và được trỏ tới)",
}

assert set(GRAPH_DIRECTION_DESCRIPTIONS) == set(GraphDirection), (
    f"Thiếu description cho GraphDirection: {set(GraphDirection) - set(GRAPH_DIRECTION_DESCRIPTIONS)}"
)


def format_graph_direction_docs() -> str:
    return ", ".join(f"'{k.value}' ({desc})" for k, desc in GRAPH_DIRECTION_DESCRIPTIONS.items())


class CitationDirection(str, Enum):
    """Direction of a citation edge relative to the current provision."""

    OUTGOING = "OUTGOING"
    INCOMING = "INCOMING"


CITATION_DIRECTION_DESCRIPTIONS: Final[dict[CitationDirection, str]] = {
    CitationDirection.OUTGOING: "Cụm viện dẫn nằm trong from_path và trỏ tới các đoạn đến được",
    CitationDirection.INCOMING: "Cụm viện dẫn nằm trong từng đoạn đến được và trỏ về from_path",
}

assert set(CITATION_DIRECTION_DESCRIPTIONS) == set(CitationDirection), (
    f"Thiếu description cho CitationDirection: {set(CitationDirection) - set(CITATION_DIRECTION_DESCRIPTIONS)}"
)


class LegalToolName(str, Enum):
    """Exhaustive catalog of legal MCP tools."""

    SEARCH = "search"
    HIERARCHICAL_NAVIGATE = "hierarchical_navigate"
    GRAPH_TRAVERSE = "graph_traverse"
    GET_RAW = "get_raw"
    GRAPH_ADD_EDGES = "graph_add_edges"
    GRAPH_REMOVE_EDGES = "graph_remove_edges"


LEGAL_TOOL_DESCRIPTIONS: Final[dict[LegalToolName, str]] = {
    LegalToolName.SEARCH: "Tìm kiếm quy phạm kết hợp ngữ nghĩa và nguyên văn",
    LegalToolName.HIERARCHICAL_NAVIGATE: "Đọc phân cấp các đoạn quy phạm theo cây văn bản",
    LegalToolName.GRAPH_TRAVERSE: "Duyệt đồ thị quan hệ dẫn chiếu giữa các điều khoản",
    LegalToolName.GET_RAW: "Đọc nguyên văn văn bản gốc theo số dòng",
    LegalToolName.GRAPH_ADD_EDGES: "Thêm cạnh quan hệ dẫn chiếu mới vào đồ thị",
    LegalToolName.GRAPH_REMOVE_EDGES: "Gỡ bỏ cạnh quan hệ sai khỏi đồ thị",
}

assert set(LEGAL_TOOL_DESCRIPTIONS) == set(LegalToolName), (
    f"Thiếu description cho LegalToolName: {set(LegalToolName) - set(LEGAL_TOOL_DESCRIPTIONS)}"
)


def format_legal_tool_docs() -> str:
    return ", ".join(f"'{k.value}' ({desc})" for k, desc in LEGAL_TOOL_DESCRIPTIONS.items())


class GraphTraversalStep(BaseModel):
    """One edge walked by a graph traversal, from the node already reached to the next."""

    model_config = ConfigDict(extra="ignore")

    from_path: str
    to_path: str
    relation_type: StatutoryRelationType
    citation_text: str
    direction: CitationDirection  # OUTGOING: citation_text is in from_path; INCOMING: it is in to_path
    depth: int
