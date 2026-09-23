"""Domain models and DTO schemas for statutory staging sessions."""

from __future__ import annotations

import datetime
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rag_eval.legal.schemas import parse_flexible_date


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


def deep_merge_dict(base: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """Recursively merges delta dictionary into base dictionary without clobbering sibling keys."""
    merged = dict(base)
    for key, value in delta.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


class ChunkReviewStatus(str, Enum):
    """Review lifecycle status for an individual statutory chunk within staging."""

    PENDING = "PENDING"
    FINALIZED = "FINALIZED"


class StagingStatus(str, Enum):
    """Lifecycle statuses for statutory staging sessions."""

    DRAFT = "DRAFT"
    AGENT_COMMITTED = "AGENT_COMMITTED"
    APPROVED = "APPROVED"
    PROMOTED = "PROMOTED"


class StagingChunkDelta(BaseModel):
    """Payload representing partial field updates to an existing staged chunk."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Target dot-separated ltree path to patch")
    verbatim_text: str | None = Field(None, description="Optional updated verbatim clause text")
    contextualized_text: str | None = Field(None, description="Optional updated CPHC contextual text")
    lead_sentence: str | None = Field(None, description="Optional updated lead sentence")
    start_line: int | None = Field(None, ge=1, description="Optional updated starting line number")
    end_line: int | None = Field(None, ge=1, description="Optional updated ending line number")
    metadata: dict[str, Any] | None = Field(None, description="Optional partial metadata dictionary to deep-merge")
    effective_date: datetime.date | None = Field(None, description="Optional updated effective date")
    expiration_date: datetime.date | None = Field(None, description="Optional updated expiration date")
    review_status: ChunkReviewStatus | None = Field(
        None, description="Optional updated review status ('PENDING' | 'FINALIZED')"
    )

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> datetime.date | None:
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
    diff_payload: dict[str, Any] | None = Field(default=None, description="Detailed mutation payload")


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
    metadata: dict[str, Any] = Field(default_factory=dict, description="Chunk metadata payload")


class StagingChunk(BaseModel):
    """Represents a candidate statutory chunk within a staging session."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Hierarchical dot-separated ltree path")
    verbatim_text: str = Field(..., description="Verbatim clause/point text")
    contextualized_text: str = Field(..., description="Synthesized CPHC context text")
    start_line: int = Field(default=1, ge=1, description="1-indexed starting line number in source text")
    end_line: int = Field(default=1, ge=1, description="1-indexed ending line number in source text")
    lead_sentence: str = Field("", description="Inherited lead sentence")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic metadata payload")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    char_length: int = Field(default=0, description="Total character count of verbatim text")
    review_status: ChunkReviewStatus = Field(
        default=ChunkReviewStatus.PENDING,
        description="Chunk review lifecycle status ('PENDING' | 'FINALIZED')",
    )

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)

    @model_validator(mode="after")
    def compute_char_length(self) -> StagingChunk:
        if not self.char_length and self.verbatim_text:
            self.char_length = len(self.verbatim_text)
        return self


class StagingEdge(BaseModel):
    """Represents a candidate directed relation edge within a staging session."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(..., description="Source chunk ltree path")
    target_path: str | None = Field(None, description="Target chunk ltree path")
    target_external_ref: str | None = Field(None, description="External citation text")
    relation_type: str = Field(..., description="Graph relation type enum string")
    citation_text: str | None = Field(None, description="Verbatim statutory citation phrase")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic edge metadata")
