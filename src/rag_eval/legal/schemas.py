"""Core Pydantic v2 schemas and domain models for the Ultra-Lean 3-Table Agent-First legal system.

Matches PostgreSQL 3-table schema (documents, chunks, graph_edges) with zero-bloat dynamic metadata.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
import uuid
from typing import Any

from mcp.shared.exceptions import MCPError
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ------------------------------------------------------------------------------
# Standard Domain Error Codes & Exceptions
# ------------------------------------------------------------------------------
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
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=error_code, message=message, data=data)
        self.error_code = error_code


# ------------------------------------------------------------------------------
# Flexible Statutory Date Parsing
# ------------------------------------------------------------------------------
def parse_flexible_date(val: str | datetime.date | None) -> datetime.date | None:
    """Parses various date representations (ISO, DD/MM/YYYY, DD-MM-YYYY) into datetime.date."""
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

    # Match DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return datetime.date(year, month, day)

    # Match YYYY/MM/DD
    m2 = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", s)
    if m2:
        year, month, day = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        return datetime.date(year, month, day)

    raise ValueError(f"Unable to parse date string: '{s}'")


# ------------------------------------------------------------------------------
# LTREE Path Sanitization & Validation
# ------------------------------------------------------------------------------
LTREE_LABEL_REGEX = re.compile(r"^[a-zA-Z0-9_]+$")
LTREE_PATH_REGEX = re.compile(r"^[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*$")

_VN_CHAR_MAP: dict[int, str] = str.maketrans({
    "đ": "d",
    "Đ": "d",
    "ð": "d",
    "Ð": "d",
})


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


# ------------------------------------------------------------------------------
# 1. Document Record (Table: documents)
# ------------------------------------------------------------------------------
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
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Dynamic metadata (doc_type, authority, signer, url)",
    )
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

    @field_validator("doc_code", mode="after")
    @classmethod
    def validate_doc_code(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("doc_code cannot be empty")
        return s


# ------------------------------------------------------------------------------
# 2. Canonical Fully Qualified Chunk (Table: chunks)
# ------------------------------------------------------------------------------
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
    embedding: list[float] | None = Field(
        None, description="Normalized dense vector (384-dim)"
    )
    tsv_content: str | None = Field(
        None, description="Full-text search vector representation"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Dynamic semantic payload (fines, vehicles, norm_roles, exceptions)",
    )
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(
        None, description="Expiration date (None if active)"
    )
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

    @field_validator("path", mode="after")
    @classmethod
    def validate_path(cls, v: str) -> str:
        return validate_ltree_path(v)


# ------------------------------------------------------------------------------
# 3. Graph Edge Record (Table: graph_edges)
# ------------------------------------------------------------------------------
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
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Dynamic condition logic, context notes"
    )
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
