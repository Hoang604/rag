"""Pydantic v2 schemas and request/response models for the Legal Staging Reviewer Web API."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingEdge,
    StagingMutationRecord,
    StagingStatus,
)
from rag_eval.legal.schemas import parse_flexible_date


# ------------------------------------------------------------------------------
# 1. Staging Session Schemas
# ------------------------------------------------------------------------------
class StagingSessionSummaryResponse(BaseModel):
    """Summary response for staging sessions discovery listing."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Statutory document code e.g. 100/2019/NĐ-CP")
    title: str = Field(..., description="Document title")
    status: StagingStatus = Field(..., description="Current staging lifecycle status")
    total_chunks: int = Field(..., description="Total count of candidate chunks")
    total_edges: int = Field(..., description="Total count of relational graph edges")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    created_at: datetime.datetime = Field(..., description="Session creation timestamp")
    updated_at: datetime.datetime = Field(..., description="Session last updated timestamp")
    committed_at: datetime.datetime | None = Field(None, description="Agent commit timestamp")
    promoted_at: datetime.datetime | None = Field(None, description="Human promotion timestamp")


class StagingSessionDetailResponse(BaseModel):
    """Detailed response for a staging document session."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Statutory document code")
    title: str = Field(..., description="Document title")
    status: StagingStatus = Field(..., description="Current staging status")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    created_at: datetime.datetime = Field(..., description="Session creation timestamp")
    updated_at: datetime.datetime = Field(..., description="Session last updated timestamp")
    committed_at: datetime.datetime | None = Field(None, description="Agent commit timestamp")
    promoted_at: datetime.datetime | None = Field(None, description="Human promotion timestamp")
    raw_text: str | None = Field(None, description="Raw statutory source text")
    doc_metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    chunks: list[StagingChunk] = Field(default_factory=list, description="Candidate chunks")
    edges: list[StagingEdge] = Field(default_factory=list, description="Relational graph edges")
    raw_ast_snapshot: list[dict[str, Any]] | None = Field(
        None, description="Initial AST baseline snapshot"
    )
    mutation_history: list[StagingMutationRecord] = Field(
        default_factory=list, description="Audit log of mutations"
    )


class CreateSessionRequest(BaseModel):
    """Request payload to create a new staging session from raw statutory text."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Unique statutory document code")
    title: str = Field(..., description="Full document title")
    raw_text: str = Field(..., description="Raw text of statutory document")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic document metadata")

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)


# ------------------------------------------------------------------------------
# 2. Document Hierarchy Tree Schemas
# ------------------------------------------------------------------------------
class DocumentTreeNodeResponse(BaseModel):
    """Node representation in the document hierarchy tree canvas."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Hierarchical dot-separated ltree path")
    label: str = Field(..., description="Human-readable node label")
    node_type: str = Field(
        ...,
        description="Node division type: DOCUMENT | CHAPTER | SECTION | ARTICLE | CLAUSE | POINT | APPENDIX",
    )
    verbatim_text: str = Field("", description="Raw verbatim statutory text")
    contextualized_text: str = Field("", description="Synthesized contextual text")
    lead_sentence: str = Field("", description="Stem / lead sentence")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Node semantic metadata")
    effective_date: datetime.date | None = Field(None, description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    children: list[DocumentTreeNodeResponse] = Field(
        default_factory=list, description="Child nodes in hierarchy"
    )


class DocumentTreeResponse(BaseModel):
    """Full nested tree hierarchy for interactive visualizer canvas."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Document code")
    title: str = Field(..., description="Document title")
    total_nodes: int = Field(..., description="Total nodes count in hierarchy")
    root: DocumentTreeNodeResponse = Field(..., description="Root document node")


# ------------------------------------------------------------------------------
# 3. Surgical Chunk Patching & Edges Schemas
# ------------------------------------------------------------------------------
class ChunkPatchItem(BaseModel):
    """Single chunk payload for surgical in-place patch supporting partial delta fields."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Dot-separated ltree path")
    verbatim_text: str | None = Field(None, description="Raw verbatim statutory text (optional for deltas)")
    contextualized_text: str | None = Field(None, description="Synthesized contextual text (optional for deltas)")
    lead_sentence: str | None = Field(None, description="Lead sentence (optional for deltas)")
    metadata: dict[str, Any] | None = Field(None, description="Dynamic chunk metadata to deep-merge (optional)")
    effective_date: datetime.date | None = Field(None, description="Effective date (optional for deltas)")
    expiration_date: datetime.date | None = Field(None, description="Expiration date (optional for deltas)")

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)


class BatchPatchRequest(BaseModel):
    """Request payload for batch updating and removing chunks."""

    model_config = ConfigDict(extra="ignore")

    updated_chunks: list[ChunkPatchItem] = Field(
        default_factory=list, description="List of chunks to add or update"
    )
    removed_paths: list[str] = Field(
        default_factory=list, description="List of chunk paths to delete"
    )


class BatchPatchResponse(BaseModel):
    """Response returned after applying a chunk batch patch."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("SUCCESS", description="Operation status")
    doc_code: str = Field(..., description="Document code")
    updated_count: int = Field(..., description="Number of chunks updated")
    removed_count: int = Field(..., description="Number of chunk paths removed")
    total_chunks: int = Field(..., description="Total remaining chunks in session")


class CreateEdgeRequest(BaseModel):
    """Request payload to create or update a relational graph edge."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(..., description="Source chunk ltree path")
    target_path: str | None = Field(None, description="Target chunk ltree path")
    target_external_ref: str | None = Field(
        None, description="External citation text if uningested"
    )
    relation_type: str = Field(..., description="Relation type enum string")
    citation_text: str | None = Field(None, description="Verbatim statutory citation phrase")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic edge metadata")


class DeleteEdgeRequest(BaseModel):
    """Request payload to delete a relational graph edge."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(..., description="Source chunk ltree path")
    target_path: str | None = Field(None, description="Target chunk ltree path")
    relation_type: str = Field(..., description="Relation type enum string")


class StagingEdgeResponse(BaseModel):
    """Response model for a relational graph edge."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(..., description="Source chunk ltree path")
    target_path: str | None = Field(None, description="Target chunk ltree path")
    target_external_ref: str | None = Field(None, description="External citation text")
    relation_type: str = Field(..., description="Relation type enum string")
    citation_text: str | None = Field(None, description="Verbatim statutory citation phrase")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic edge metadata")


class StatusTransitionRequest(BaseModel):
    """Request payload to transition staging session status."""

    model_config = ConfigDict(extra="ignore")

    status: StagingStatus = Field(..., description="Target staging lifecycle status")
    actor: str = Field("HUMAN:reviewer", description="Actor initiating status transition")
    description: str = Field("", description="Reason or notes for transition")


# ------------------------------------------------------------------------------
# 4. Version Mutation Diff Schemas
# ------------------------------------------------------------------------------
class AuditDiffEntry(BaseModel):
    """Single item representing a detected mutation difference."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Target chunk path")
    change_type: str = Field(..., description="'ADDED' | 'MODIFIED' | 'DELETED'")
    field_name: str | None = Field(None, description="Specific field changed")
    old_value: Any | None = Field(None, description="Baseline / prior value")
    new_value: Any | None = Field(None, description="Current / updated value")
    description: str = Field("", description="Human-readable summary of difference")


class SessionDiffResponse(BaseModel):
    """Response payload detailing 4-stage version mutation differences."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Document code")
    total_changes: int = Field(..., description="Total count of diff entries")
    added_chunks: list[StagingChunk] = Field(
        default_factory=list, description="Chunks added since baseline parse"
    )
    modified_chunks: list[dict[str, Any]] = Field(
        default_factory=list, description="Chunks modified since baseline parse"
    )
    deleted_chunks: list[dict[str, Any]] = Field(
        default_factory=list, description="Chunks removed since baseline parse"
    )
    edge_diffs: list[dict[str, Any]] = Field(
        default_factory=list, description="Relational graph edge differences"
    )
    diff_entries: list[AuditDiffEntry] = Field(
        default_factory=list, description="Detailed audit diff entries"
    )


# ------------------------------------------------------------------------------
# 5. Pre-Flight Validation & Promotion Schemas
# ------------------------------------------------------------------------------
class ValidationIssue(BaseModel):
    """Represents a discrete rule check violation."""

    model_config = ConfigDict(extra="ignore")

    rule: str = Field(..., description="Rule code identifier")
    severity: str = Field("ERROR", description="'ERROR' | 'WARNING'")
    path: str | None = Field(None, description="Affected chunk path or entity")
    message: str = Field(..., description="Human-readable violation description")
    blocking: bool = Field(True, description="Whether this issue blocks promotion")


class PreFlightValidationResponse(BaseModel):
    """Automated pre-flight integrity verification checklist results."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field(..., description="'PASSED' | 'FAILED'")
    passed: bool = Field(..., description="True if all blocking checks passed")
    total_checks: int = Field(..., description="Total automated integrity checks run")
    issues: list[ValidationIssue] = Field(
        default_factory=list, description="List of detected validation issues"
    )
    summary: dict[str, Any] = Field(
        default_factory=dict, description="Summary breakdown of check results"
    )


class PromoteSessionRequest(BaseModel):
    """Request payload to trigger human promotion to PostgreSQL."""

    model_config = ConfigDict(extra="ignore")

    reviewer_notes: str | None = Field(None, description="Optional reviewer audit notes")
    compute_embeddings: bool = Field(
        True, description="Whether to compute 384-dim dense vector embeddings"
    )


class PromotionResultResponse(BaseModel):
    """Result of human promotion to PostgreSQL production tables."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("SUCCESS", description="'SUCCESS' | 'FAILED'")
    doc_code: str = Field(..., description="Promoted statutory document code")
    document_id: str = Field(..., description="Authoritative PostgreSQL document UUID")
    chunks_promoted: int = Field(..., description="Total chunks persisted into chunks table")
    edges_promoted: int = Field(..., description="Total edges persisted into graph_edges table")
    promoted_at: str = Field(..., description="ISO 8601 promotion timestamp")
    message: str = Field("", description="Status message")


# ------------------------------------------------------------------------------
# 6. Utility & Health Schemas
# ------------------------------------------------------------------------------
class HealthResponse(BaseModel):
    """System health probe response."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("OK", description="Service health status")
    database: str = Field("CONNECTED", description="PostgreSQL connection health")
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class RawTextResponse(BaseModel):
    """Raw statutory text payload for dual-view split screen."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Document code")
    title: str = Field(..., description="Document title")
    raw_text: str = Field(..., description="Full raw statutory text")
    chunks_count: int = Field(..., description="Total parsed chunks count")


class GenericSuccessResponse(BaseModel):
    """Generic status response model."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field("SUCCESS", description="Operation status")
    message: str = Field("", description="Operation message")
    doc_code: str | None = Field(None, description="Affected document code")


class ReparentSubtreeRequest(BaseModel):
    """Request payload to migrate a subtree to a new parent ltree prefix."""

    model_config = ConfigDict(extra="ignore")

    old_path_prefix: str = Field(..., description="Existing ltree path prefix to move")
    new_path_prefix: str = Field(..., description="New target ltree path prefix")
    dry_run: bool = Field(False, description="Whether to simulate mutation")
    actor: str = Field("HUMAN:reviewer", description="Action author")


class ReparentSubtreeResponse(BaseModel):
    """Response returned after subtree re-parenting."""

    model_config = ConfigDict(extra="ignore")

    status: str = "SUCCESS"
    doc_code: str
    dry_run: bool
    affected_chunks_count: int
    affected_edges_count: int
    old_path_prefix: str
    new_path_prefix: str
    total_chunks: int
