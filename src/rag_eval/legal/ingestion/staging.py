"""Disk-based Staging Store and Manager for Two-Phase Statutory Ingestion.

Provides isolated staging sessions stored under .cache/stg/<doc_code>.json, allowing
external LLMs to preview, patch candidate chunks, and attach relational graph edges
before committing to the production 3-table database.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.schemas import (
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
    parse_flexible_date,
    sanitize_ltree_label,
    validate_ltree_path,
)

logger = logging.getLogger(__name__)
DEFAULT_STAGING_DIR = Path(".cache/stg")


class StagingStatus(str, Enum):
    """Lifecycle statuses for statutory staging sessions."""

    DRAFT = "DRAFT"
    AGENT_COMMITTED = "AGENT_COMMITTED"
    APPROVED = "APPROVED"
    PROMOTED = "PROMOTED"


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


class StagingChunk(BaseModel):
    """Represents a candidate statutory chunk within a staging session."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Hierarchical dot-separated ltree path")
    verbatim_text: str = Field(..., description="Verbatim clause/point text")
    contextualized_text: str = Field(..., description="Synthesized CPHC context text")
    lead_sentence: str = Field("", description="Inherited lead sentence")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic metadata payload")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)


class StagingEdge(BaseModel):
    """Represents a candidate directed relation edge within a staging session."""

    model_config = ConfigDict(extra="ignore")

    source_path: str = Field(..., description="Source chunk ltree path")
    target_path: str | None = Field(None, description="Target chunk ltree path")
    target_external_ref: str | None = Field(None, description="External citation text")
    relation_type: str = Field(..., description="Graph relation type enum string")
    citation_text: str | None = Field(None, description="Verbatim statutory citation phrase")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic edge metadata")


class StagingDocumentSession(BaseModel):
    """Represents a persisted staging document session."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Statutory document code")
    title: str = Field(..., description="Document title")
    status: StagingStatus = Field(default=StagingStatus.DRAFT, description="Current staging status")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="Session creation timestamp",
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="Session last update timestamp",
    )
    committed_at: datetime.datetime | None = Field(None, description="Session commit timestamp")
    promoted_at: datetime.datetime | None = Field(None, description="Session promotion timestamp")
    raw_text: str | None = Field(default=None, description="Raw statutory source text")
    doc_metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    chunks: list[StagingChunk] = Field(default_factory=list, description="List of staged chunks")
    edges: list[StagingEdge] = Field(default_factory=list, description="List of staged graph edges")
    raw_ast_snapshot: list[dict[str, Any]] | None = Field(
        default=None, description="Initial AST/CPHC baseline snapshot for version diffing"
    )
    mutation_history: list[StagingMutationRecord] = Field(
        default_factory=list, description="Audit trail of mutations"
    )

    @field_validator("effective_date", "expiration_date", mode="before")
    @classmethod
    def parse_dates(cls, v: Any) -> datetime.date | None:
        if v is None:
            return None
        return parse_flexible_date(v)


class StagingManager:
    """Manages disk-based staging sessions for two-phase statutory ingestion."""

    def __init__(self, staging_dir: Path | str = DEFAULT_STAGING_DIR) -> None:
        self.staging_dir = Path(staging_dir)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, doc_code: str) -> Path:
        sanitized = sanitize_ltree_label(doc_code)
        return self.staging_dir / f"{sanitized}.json"

    def create_session_from_raw(
        self,
        doc_code: str,
        title: str,
        raw_text: str,
        effective_date: datetime.date,
        expiration_date: datetime.date | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StagingDocumentSession:
        """Parses raw text via AST and CPHC into a fresh StagingDocumentSession and persists to disk."""
        parser = LegalASTParser(doc_code=doc_code)
        root = parser.parse(raw_text, doc_title=title)

        temp_doc_id = uuid.uuid4()
        cphc = CPHCEngine(
            document_id=temp_doc_id,
            doc_code=doc_code,
            doc_title=title,
            effective_date=effective_date,
            expiration_date=expiration_date,
        )
        canonical_chunks = cphc.chunk_ast(root)

        stg_chunks = [
            StagingChunk(
                path=c.path,
                verbatim_text=c.verbatim_text,
                contextualized_text=c.contextualized_text,
                lead_sentence="",
                metadata=c.metadata,
                effective_date=c.effective_date,
                expiration_date=c.expiration_date,
            )
            for c in canonical_chunks
        ]

        now = datetime.datetime.now(datetime.UTC)
        initial_mutation = StagingMutationRecord(
            actor="SYSTEM",
            action_type="CREATED",
            description=f"Created initial staging session from raw text ({len(stg_chunks)} chunks).",
            timestamp=now,
            diff_payload={"total_chunks": len(stg_chunks)},
        )

        raw_ast_snapshot = [c.model_dump(mode="json") for c in stg_chunks]

        session = StagingDocumentSession(
            doc_code=doc_code,
            title=title,
            status=StagingStatus.DRAFT,
            effective_date=effective_date,
            expiration_date=expiration_date,
            created_at=now,
            updated_at=now,
            committed_at=None,
            promoted_at=None,
            raw_text=raw_text,
            doc_metadata=metadata or {},
            chunks=stg_chunks,
            edges=[],
            raw_ast_snapshot=raw_ast_snapshot,
            mutation_history=[initial_mutation],
        )
        self.save_session(session)
        return session

    def load_session(self, doc_code: str) -> StagingDocumentSession:
        """Loads an existing staging session from disk."""
        p = self._get_session_path(doc_code)
        if not p.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {p}",
                data={"doc_code": doc_code, "staging_path": str(p)},
            )
        try:
            content = p.read_text(encoding="utf-8")
            raw_data = json.loads(content)
            return StagingDocumentSession.model_validate(raw_data)
        except json.JSONDecodeError as exc:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' is corrupted: {exc}",
                data={"doc_code": doc_code},
            ) from exc

    def save_session(self, session: StagingDocumentSession) -> Path:
        """Saves a staging session to disk atomically using POSIX tempfile rename."""
        p = self._get_session_path(session.doc_code)
        p.parent.mkdir(parents=True, exist_ok=True)
        content = session.model_dump_json(indent=2)

        tmp_p = p.parent / f"{p.name}.tmp.{uuid.uuid4()}"
        try:
            with open(tmp_p, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            tmp_p.replace(p)
        except (OSError, RuntimeError):
            if tmp_p.exists():
                tmp_p.unlink(missing_ok=True)
            raise
        return p

    def patch_chunks(
        self,
        doc_code: str,
        updated_chunks: list[StagingChunk],
        removed_paths: list[str] | None = None,
    ) -> StagingDocumentSession:
        """Surgically updates or removes chunks within an existing staging session."""
        session = self.load_session(doc_code)
        chunk_map: dict[str, StagingChunk] = {c.path: c for c in session.chunks}

        # Apply removals
        if removed_paths:
            for rp in removed_paths:
                clean_rp = validate_ltree_path(rp)
                chunk_map.pop(clean_rp, None)

        # Apply surgical updates
        for uc in updated_chunks:
            clean_p = validate_ltree_path(uc.path)
            uc.path = clean_p
            chunk_map[clean_p] = uc

        # Sort chunks by path for deterministic hierarchy
        sorted_chunks = sorted(chunk_map.values(), key=lambda x: x.path)
        session.chunks = sorted_chunks

        now = datetime.datetime.now(datetime.UTC)
        session.updated_at = now
        session.mutation_history.append(
            StagingMutationRecord(
                actor="AGENT",
                action_type="CHUNK_PATCHED",
                description=f"Patched {len(updated_chunks)} chunks and removed {len(removed_paths or [])} paths.",
                timestamp=now,
                diff_payload={
                    "updated_count": len(updated_chunks),
                    "removed_paths": removed_paths or [],
                },
            )
        )

        self.save_session(session)
        return session

    def add_edges(
        self,
        doc_code: str,
        edges: list[StagingEdge],
    ) -> StagingDocumentSession:
        """Appends and deduplicates graph relationship edges in the staging session."""
        session = self.load_session(doc_code)
        existing_edges: dict[tuple[str, str | None, str], StagingEdge] = {
            (e.source_path, e.target_path, e.relation_type): e for e in session.edges
        }

        for new_edge in edges:
            clean_src = validate_ltree_path(new_edge.source_path)
            clean_tgt = validate_ltree_path(new_edge.target_path) if new_edge.target_path else None
            new_edge.source_path = clean_src
            new_edge.target_path = clean_tgt
            key = (clean_src, clean_tgt, new_edge.relation_type)
            existing_edges[key] = new_edge

        session.edges = list(existing_edges.values())

        now = datetime.datetime.now(datetime.UTC)
        session.updated_at = now
        session.mutation_history.append(
            StagingMutationRecord(
                actor="AGENT",
                action_type="EDGES_ADDED",
                description=f"Added or updated {len(edges)} relation edges.",
                timestamp=now,
                diff_payload={"edges_count": len(edges)},
            )
        )

        self.save_session(session)
        return session

    def list_sessions(self) -> list[StagingSessionSummary]:
        """Discovers and lists summaries of all staging sessions in the staging directory."""
        summaries: list[StagingSessionSummary] = []
        if not self.staging_dir.exists():
            return summaries
        for file_path in sorted(self.staging_dir.glob("*.json")):
            if file_path.name.startswith("."):
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
                data = json.loads(content)
                session = StagingDocumentSession.model_validate(data)
                summaries.append(
                    StagingSessionSummary(
                        doc_code=session.doc_code,
                        title=session.title,
                        status=session.status,
                        total_chunks=len(session.chunks),
                        total_edges=len(session.edges),
                        effective_date=session.effective_date,
                        expiration_date=session.expiration_date,
                        created_at=session.created_at,
                        updated_at=session.updated_at,
                        committed_at=session.committed_at,
                        promoted_at=session.promoted_at,
                    )
                )
            except (json.JSONDecodeError, ValueError, KeyError, OSError) as exc:
                logger.warning("Skipping unreadable staging session file %s: %s", file_path, exc)
        return summaries

    def update_session_status(
        self,
        doc_code: str,
        status: StagingStatus,
        actor: str,
        description: str,
    ) -> StagingDocumentSession:
        """Updates the status of an existing staging session and records the transition in mutation history."""
        session = self.load_session(doc_code)
        old_status = session.status
        session.status = status
        now = datetime.datetime.now(datetime.UTC)
        session.updated_at = now

        if status == StagingStatus.AGENT_COMMITTED and not session.committed_at:
            session.committed_at = now
        elif status == StagingStatus.PROMOTED and not session.promoted_at:
            session.promoted_at = now

        session.mutation_history.append(
            StagingMutationRecord(
                actor=actor,
                action_type=f"STATUS_TRANSITION_{status.value}",
                description=description or f"Transitioned status from {old_status.value} to {status.value}",
                timestamp=now,
                diff_payload={"old_status": old_status.value, "new_status": status.value},
            )
        )
        self.save_session(session)
        return session

    def delete_session(self, doc_code: str) -> bool:
        """Deletes a staging session file after successful promotion to PostgreSQL."""
        p = self._get_session_path(doc_code)
        if p.exists():
            p.unlink()
            return True
        return False
