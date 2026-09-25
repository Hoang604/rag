from __future__ import annotations

import datetime
import re
import unicodedata
import uuid
import zoneinfo
from dataclasses import dataclass
from enum import Enum

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


class DanglingDependencyRecord(BaseModel):
    """Represents an open or external citation dependency declared on a chunk."""

    model_config = ConfigDict(extra="ignore")

    dependency_text: str = Field(..., description="Verbatim phrasing of caveat or citation")
    dependency_type: str = Field("OPEN_ENDED", description="'OPEN_ENDED' | 'EXTERNAL_CITATION'")
    suggested_target_doc: str | None = Field(None, description="Suggested target document code")


class ChunkMetadata(BaseModel):
    """Structured semantic payload for statutory chunks."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    doc_code: str | None = None
    node_type: str | None = None
    index_label: str | None = None
    clause_kind: str | None = None
    chapter_title: str | None = None
    article_title: str | None = None
    vehicle_classes: list[str] | None = None
    provision_role: str | None = None
    window: str | None = None
    window_count: str | None = None
    provision_path: str | None = None

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
    """Metadata payload for knowledge graph relation edges."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    condition: str | None = None
    notes: str | None = None
    effective_date: str | None = None

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
        description="Dynamic semantic payload (fines, vehicles, norm_roles, exceptions)",
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
