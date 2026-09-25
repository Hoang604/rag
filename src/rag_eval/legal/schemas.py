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
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class DocumentRecord(BaseModel):
    """Pydantic model matching the 'documents' table."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Document UUID")
    doc_code: str = Field(..., description="Unique statutory code e.g. 100/2019/NĐ-CP")
    title: str = Field(..., description="Full statutory document title")
    effective_date: datetime.date = Field(..., description="Enactment effective date")
    expiration_date: datetime.date | None = Field(
        None, description="Expiration date (None if indefinitely active)"
    )
    metadata: DocumentMetadata = Field(
        default_factory=DocumentMetadata,
        description="Dynamic metadata (doc_type, authority, signer, url)",
    )
    raw_text: str | None = Field(
        default=None, description="Raw statutory source text"
    )
    created_at: datetime.datetime = Field(default_factory=get_vietnam_now)

    @field_validator("doc_code", mode="after")
    @classmethod
    def validate_doc_code(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("doc_code cannot be empty")
        return s


class CanonicalFullyQualifiedChunk(BaseModel):
    """Pydantic model matching the 'chunks' table (CFQC)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Chunk UUID")
    document_id: uuid.UUID = Field(..., description="Parent document foreign key UUID")
    path: str = Field(..., description="Hierarchical dot-separated ltree path")
    verbatim_text: str = Field(..., description="Raw verbatim statutory clause text")
    contextualized_text: str = Field(
        ..., description="Full CPHC synthesized context text"
    )
    start_line: int = Field(
        default=1, ge=1, description="1-indexed starting line number in source text"
    )
    end_line: int = Field(
        default=1, ge=1, description="1-indexed ending line number in source text"
    )
    embedding: list[float] | None = Field(
        None, description="Normalized dense vector (512-dim)"
    )
    tsv_content: str | None = Field(
        None, description="Full-text search vector representation"
    )
    metadata: ChunkMetadata = Field(
        default_factory=ChunkMetadata,
        description="Siêu dữ liệu ngữ nghĩa có cấu trúc cho từng đoạn quy phạm pháp luật.",
    )
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(
        None, description="Expiration date (None if active)"
    )
    finalization_state: FinalizationState = Field(
        default=FinalizationState.UNFINALIZED_OPEN_ENDED,
        description="Legal finalization state in database",
    )
    dangling_dependencies: list[DanglingDependencyRecord] = Field(
        default_factory=list,
        description="List of declared open or unlinked dependencies",
    )
    created_at: datetime.datetime = Field(default_factory=get_vietnam_now)

    @field_validator("path", mode="after")
    @classmethod
    def validate_path(cls, v: str) -> str:
        return validate_ltree_path(v)


class GraphEdgeRecord(BaseModel):
    """Pydantic model matching the 'graph_edges' table."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Edge UUID")
    source_chunk_id: uuid.UUID = Field(..., description="Source chunk foreign key")
    target_chunk_id: uuid.UUID | None = Field(
        None, description="Target chunk foreign key (None for external references)"
    )
    target_external_ref: str | None = Field(
        None, description="Unresolved citation string if target not in database"
    )
    relation_type: str = Field(
        ...,
        description="Relation type: MODIFIES_AND_REPLACES | REFERENCES | SANCTIONS | OVERRIDES | EXEMPTS | GUIDES",
    )
    citation_text: str | None = Field(
        None, description="Verbatim statutory citation phrase"
    )
    metadata: EdgeMetadata = Field(
        default_factory=EdgeMetadata, description="Dynamic condition logic, context notes"
    )
    created_at: datetime.datetime = Field(default_factory=get_vietnam_now)
