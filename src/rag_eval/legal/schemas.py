from __future__ import annotations

import datetime
import re
import unicodedata
import uuid
import zoneinfo
from dataclasses import dataclass
from enum import Enum
from typing import Literal, get_args

from mcp.shared.exceptions import MCPError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
)

VIETNAM_TZ = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")


def get_vietnam_now() -> datetime.datetime:
    """Returns current timezone-aware datetime in Vietnam jurisdiction timezone (Asia/Ho_Chi_Minh, UTC+7)."""
    return datetime.datetime.now(VIETNAM_TZ)


def get_vietnam_today() -> datetime.date:
    """Returns current date in Vietnam jurisdiction timezone (Asia/Ho_Chi_Minh, UTC+7)."""
    return datetime.datetime.now(VIETNAM_TZ).date()


E_AST_GROUNDING_VALIDATION = -32001
E_STORAGE_CONNECTION = -32002
E_INVALID_DOCUMENT_HIERARCHY = -32003
E_CORPUS_INTEGRITY_VIOLATION = -32004
E_VECTOR_DIMENSION_MISMATCH = -32005


class LegalDomainError(MCPError):
    """Domain-specific exception conforming to JSON-RPC 2.0 error specification and MCPError."""

    def __init__(
        self,
        error_code: int,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code=error_code, message=message, data=data)
        self.error_code = error_code


def parse_flexible_date(val: object) -> datetime.date | None:
    """Parses various date representations (ISO, DD/MM/YYYY, DD-MM-YYYY, and Vietnamese statutory date strings)."""
    if val is None:
        return None
    if isinstance(val, datetime.date):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        pass

    vn_match = re.search(
        r"(?:ngày\s+)?(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
        s,
        re.IGNORECASE,
    )
    if vn_match:
        try:
            day, month, year = (
                int(vn_match.group(1)),
                int(vn_match.group(2)),
                int(vn_match.group(3)),
            )
            return datetime.date(year, month, day)
        except ValueError:
            pass

    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime.date(year, month, day)
        except ValueError:
            pass

    m2 = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", s)
    if m2:
        try:
            year, month, day = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
            return datetime.date(year, month, day)
        except ValueError:
            pass

    raise ValueError(f"Unable to parse date string: '{s}'")


LTREE_LABEL_REGEX = re.compile(r"^[a-zA-Z0-9_]+$")
LTREE_PATH_REGEX = re.compile(r"^[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*$")

_VN_CHAR_MAP: dict[int, str] = str.maketrans(
    {
        "đ": "d",
        "Đ": "d",
        "ð": "d",
        "Ð": "d",
    }
)


_VN_INDEX_MAP: dict[int, str] = str.maketrans(
    {
        "đ": "dd",
        "Đ": "dd",
        "ă": "aw",
        "Ă": "aw",
        "â": "aa",
        "Â": "aa",
        "ê": "ee",
        "Ê": "ee",
        "ô": "oo",
        "Ô": "oo",
        "ơ": "ow",
        "Ơ": "ow",
        "ư": "uw",
        "Ư": "uw",
    }
)


def sanitize_index_label(label: str) -> str:
    """Sanitizes an enumeration label (điểm letter, appendix letter) injectively.

    Use this wherever the label identifies a sibling among an ordered set, so
    that two different labels can never produce the same ltree segment. Use
    `sanitize_ltree_label` for free text such as titles and document codes,
    where readability matters and collisions are not a correctness problem.
    """
    if not label:
        return "node"
    translated = label.translate(_VN_INDEX_MAP)
    nfkd = unicodedata.normalize("NFKD", translated)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", ascii_text.strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "node"


def sanitize_ltree_label(label: str) -> str:
    """Sanitizes an arbitrary string into a valid PostgreSQL ltree label with Vietnamese transliteration."""
    if not label:
        return "root"
    text = label.translate(_VN_CHAR_MAP)
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", ascii_text.strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    if len(clean) > 250:
        clean = clean[:250].rstrip("_")
    return clean or "node"


def validate_ltree_path(path: str) -> str:
    """Validates and normalizes a dot-separated ltree path."""
    if not path or not path.strip():
        raise ValueError("LTREE path cannot be empty")
    clean = path.strip()
    if LTREE_PATH_REGEX.match(clean):
        return clean
    segments = clean.split(".")
    sanitized = [sanitize_ltree_label(s) for s in segments if s]
    res = ".".join(sanitized)
    if not LTREE_PATH_REGEX.match(res):
        raise ValueError(f"Invalid ltree path format: '{path}' -> '{res}'")
    return res


_PATH_ADDRESS = re.compile(
    r"\.a_(?P<dieu>\d+[a-z]?)"
    r"(?:\.c_(?P<khoan>\d+[a-z]?))?"
    r"(?:\.p_(?P<diem>[a-z]+(?:_\d+)?))?"
    r"(?:\.w_\d+)?$"
)


@dataclass(frozen=True)
class Address:
    """A statutory address: Điều, optionally Khoản, optionally Điểm."""

    dieu: str | None = None
    khoan: str | None = None
    diem: str | None = None

    def __bool__(self) -> bool:
        return any((self.dieu, self.khoan, self.diem))


def address_of_path(path: str) -> Address:
    """Reads the statutory address a chunk path encodes."""
    match = _PATH_ADDRESS.search(path)
    if match is None:
        return Address()
    return Address(
        dieu=match.group("dieu"),
        khoan=match.group("khoan"),
        diem=match.group("diem"),
    )


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
    + ". Quy tắc bất biến: Chunk không có viện dẫn mở bắt buộc phải thuộc nhóm FINALIZED; "
    "chunk còn viện dẫn mở bắt buộc phải thuộc nhóm UNFINALIZED. "
    "Khuyến nghị sử dụng công cụ stg_finalize_chunks để hệ thống tự động suy diễn chính xác trạng thái này."
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


class DanglingDependencyRecord(BaseModel):
    """Thông tin về mối phụ thuộc viện dẫn mở hoặc viện dẫn ngoài của đoạn quy phạm."""

    model_config = ConfigDict(extra="ignore")

    dependency_text: str = Field(
        ...,
        description="Nguyên văn câu viện dẫn hoặc điều kiện loại trừ pháp lý chưa được liên kết nội bộ.",
    )
    dependency_type: Literal["OPEN_ENDED", "EXTERNAL_CITATION"] = Field(
        "OPEN_ENDED",
        description="Hình thức phụ thuộc: OPEN_ENDED (dẫn chiếu mở hoặc quy định chung) hoặc EXTERNAL_CITATION (viện dẫn đích danh văn bản bên ngoài).",
    )
    suggested_target_doc: str | None = Field(
        None,
        description="Số hiệu văn bản pháp luật đích gợi ý nếu xác định được, ví dụ: '100/2019/NĐ-CP'.",
    )


class ChunkMetadata(BaseModel):
    """Thông tin siêu dữ liệu ngữ nghĩa có cấu trúc cho từng đoạn quy phạm pháp luật."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    node_type: NodeType | None = Field(
        default=None,
        description=f"Cấp bậc phân cấp của đoạn quy phạm trong cấu trúc văn bản pháp luật ({_NODE_TYPE_CHOICES}).",
    )
    index_label: str | None = Field(
        default=None,
        description="Nhãn định danh hiển thị của điều khoản, ví dụ: 'Điều 5', 'Khoản 1', 'Điểm a'.",
    )
    chapter_title: str | None = Field(
        default=None,
        description="Tiêu đề chương chứa điều khoản, ví dụ: 'Chương II - Quy tắc giao thông đường bộ'.",
    )
    article_title: str | None = Field(
        default=None,
        description="Tiêu đề điều luật chứa đoạn quy phạm, ví dụ: 'Điều 5. Xử phạt người điều khiển xe ô tô vi phạm quy tắc giao thông đường bộ'.",
    )
    window: int | None = Field(
        default=None,
        ge=1,
        description="Thứ tự phân đoạn (bắt đầu từ 1) khi điều khoản dài hoặc bảng biểu bị chia thành nhiều mảnh.",
    )
    window_count: int | None = Field(
        default=None,
        ge=1,
        description="Tổng số phân đoạn của điều khoản bị chia cắt.",
    )
    provision_path: str | None = Field(
        default=None,
        description="Đường dẫn phân cấp gốc của điều khoản trước khi bị chia nhỏ thành các cửa sổ.",
    )

    def get(self, key: str, default: object = None) -> object:
        val = getattr(self, key, None)
        if val is not None:
            return val
        if self.model_extra and key in self.model_extra:
            return self.model_extra[key]
        return default

    def __getitem__(self, key: str) -> object:
        val = getattr(self, key, None)
        if val is not None:
            return val
        if self.model_extra and key in self.model_extra:
            return self.model_extra[key]
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return (hasattr(self, key) and getattr(self, key) is not None) or (
            bool(self.model_extra and key in self.model_extra)
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

    def get(self, key: str, default: object = None) -> object:
        val = getattr(self, key, None)
        if val is not None:
            return val
        if self.model_extra and key in self.model_extra:
            return self.model_extra[key]
        return default

    def __getitem__(self, key: str) -> object:
        val = getattr(self, key, None)
        if val is not None:
            return val
        if self.model_extra and key in self.model_extra:
            return self.model_extra[key]
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return (hasattr(self, key) and getattr(self, key) is not None) or (
            bool(self.model_extra and key in self.model_extra)
        )


class EdgeMetadata(BaseModel):
    """Siêu dữ liệu ngữ nghĩa bổ trợ cho cạnh quan hệ trong đồ thị tri thức pháp lý."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    condition: str | None = Field(
        default=None,
        description="Điều kiện pháp lý hoặc hoàn cảnh áp dụng quan hệ (ví dụ: 'Khi người điều khiển phương tiện chở hàng siêu trường, siêu trọng' hoặc 'Trường hợp có nồng độ cồn vượt quá quy định').",
    )
    notes: str | None = Field(
        default=None,
        description="Ghi chú phân tích căn cứ pháp lý hoặc giải trình chuyên môn của chuyên viên/Agent khi gắn cạnh quan hệ.",
    )
    effective_date: str | None = Field(
        default=None,
        description="Ngày quan hệ pháp lý này bắt đầu phát sinh hiệu lực thi hành riêng biệt (định dạng YYYY-MM-DD), nếu khác với ngày hiệu lực của toàn văn bản.",
    )

    def get(self, key: str, default: object = None) -> object:
        val = getattr(self, key, None)
        if val is not None:
            return val
        if self.model_extra and key in self.model_extra:
            return self.model_extra[key]
        return default

    def __getitem__(self, key: str) -> object:
        val = getattr(self, key, None)
        if val is not None:
            return val
        if self.model_extra and key in self.model_extra:
            return self.model_extra[key]
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return (hasattr(self, key) and getattr(self, key) is not None) or (
            bool(self.model_extra and key in self.model_extra)
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


class HierarchicalDirection(str, Enum):
    """Navigation directions across the statutory LTREE hierarchy."""

    FULL_ARTICLE = "FULL_ARTICLE"
    CHILDREN = "CHILDREN"
    PARENT_CHAIN = "PARENT_CHAIN"
    SIBLINGS = "SIBLINGS"


# Domain Database Entities (Zero DB Defaults, Strictly Non-Nullable Boundary Anchors)


class DocumentEntity(BaseModel):
    """Canonical domain entity matching PostgreSQL 'documents' table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    doc_code: str
    title: str
    effective_date: datetime.date
    expiration_date: datetime.date | None
    metadata: dict[str, object]
    raw_text: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ChunkEntity(BaseModel):
    """Canonical domain entity matching PostgreSQL 'chunks' table (CFQC)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    document_id: uuid.UUID
    path: str
    verbatim_text: str
    contextualized_text: str
    start_line: int
    end_line: int
    embedding: list[float] | None
    tsv_content: str | None
    metadata: dict[str, object]
    effective_date: datetime.date
    expiration_date: datetime.date | None
    finalization_state: FinalizationState
    created_at: datetime.datetime
    updated_at: datetime.datetime


class RelationTypeEntity(BaseModel):
    """Catalog entity matching PostgreSQL 'relation_types' table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: StatutoryRelationType
    description: str
    is_symmetric: bool


class GraphEdgeEntity(BaseModel):
    """Canonical domain entity matching PostgreSQL 'graph_edges' table (Resolved internal edges only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    source_chunk_id: uuid.UUID
    target_chunk_id: uuid.UUID
    relation_type: StatutoryRelationType
    citation_text: str | None
    metadata: dict[str, object]
    created_at: datetime.datetime


class ChunkContextRefEntity(BaseModel):
    """Canonical entity matching PostgreSQL 'chunk_context_refs' table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    chunk_id: uuid.UUID
    char_start: int | None
    char_end: int | None
    citation_phrase: str | None
    target_chunk_id: uuid.UUID | None
    edge_id: uuid.UUID | None
    target_path: str | None
    suggested_doc_code: str | None
    dependency_type: Literal["OPEN_ENDED", "EXTERNAL_CITATION", "INTERNAL_REFERENCE"]
    created_at: datetime.datetime


# Authoritative Domain Transfer Objects (DTOs)


class SearchHitDTO(BaseModel):
    """Authoritative DTO for dense, sparse, and lexical grep search hits."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: uuid.UUID
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
    score: float = 0.0
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_similarity: float = 0.0
    keyword_matched: bool = True
    rerank_score: float | None = None
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


class GraphTraversalStepDTO(BaseModel):
    """Authoritative DTO for knowledge graph traversal steps."""

    model_config = ConfigDict(extra="ignore")

    edge_id: uuid.UUID
    source_chunk_id: uuid.UUID
    target_chunk_id: uuid.UUID
    relation_type: StatutoryRelationType
    citation_text: str | None = None
    depth: int
    target_path: str
    target_text: str


class HierarchyNodeDTO(BaseModel):
    """Authoritative DTO for hierarchical document navigation."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: uuid.UUID
    path: str
    doc_code: str
    start_line: int
    end_line: int
    verbatim_text: str
    contextualized_text: str
    metadata: dict[str, object] = Field(default_factory=dict)
    relative_depth: int


class DocumentStatsDTO(BaseModel):
    """Authoritative DTO for document catalog listing with active status and chunk statistics."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str
    title: str
    effective_date: datetime.date
    expiration_date: datetime.date | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    chunk_count: int
    in_force: bool


class UnresolvedRefBacklogDTO(BaseModel):
    """Authoritative DTO for unresolved statutory references backlog."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: uuid.UUID
    source_path: str
    doc_code: str
    doc_title: str
    target_path: str | None = None
    finalization_state: FinalizationState
    verbatim_text: str
    ref_id: uuid.UUID | None = None
    char_start: int | None = None
    char_end: int | None = None
    citation_phrase: str | None = None
    suggested_doc_code: str | None = None
    dependency_type: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @computed_field
    def context_type(self) -> str | None:
        return self.dependency_type


