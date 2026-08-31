"""Disk-based Staging Store and Manager for Two-Phase Statutory Ingestion.

Provides isolated staging sessions stored under .cache/stg/<doc_code>.json, allowing
external LLMs to preview, patch candidate chunks, and attach relational graph edges
before committing to the production 3-table database.
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.schemas import (
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
    sanitize_ltree_label,
    validate_ltree_path,
)

logger = logging.getLogger(__name__)
DEFAULT_STAGING_DIR = Path(".cache/stg")


class StagingChunk(BaseModel):
    """Represents a candidate statutory chunk within a staging session."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., description="Hierarchical dot-separated ltree path")
    verbatim_text: str = Field(..., description="Verbatim clause/point text")
    contextualized_text: str = Field(..., description="Synthesized CPHC context text")
    lead_sentence: str = Field("", description="Inherited lead sentence")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dynamic metadata payload")
    effective_date: str = Field(..., description="Effective date YYYY-MM-DD")
    expiration_date: str | None = Field(None, description="Expiration date YYYY-MM-DD")


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
    effective_date: str = Field(..., description="Effective date YYYY-MM-DD")
    expiration_date: str | None = Field(None, description="Expiration date YYYY-MM-DD")
    doc_metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    chunks: list[StagingChunk] = Field(default_factory=list, description="List of staged chunks")
    edges: list[StagingEdge] = Field(default_factory=list, description="List of staged graph edges")


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
                effective_date=c.effective_date.isoformat(),
                expiration_date=c.expiration_date.isoformat() if c.expiration_date else None,
            )
            for c in canonical_chunks
        ]

        session = StagingDocumentSession(
            doc_code=doc_code,
            title=title,
            effective_date=effective_date.isoformat(),
            expiration_date=expiration_date.isoformat() if expiration_date else None,
            doc_metadata=metadata or {},
            chunks=stg_chunks,
            edges=[],
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
        """Saves a staging session to disk atomically."""
        p = self._get_session_path(session.doc_code)
        p.parent.mkdir(parents=True, exist_ok=True)
        content = session.model_dump_json(indent=2)
        p.write_text(content, encoding="utf-8")
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
        self.save_session(session)
        return session

    def delete_session(self, doc_code: str) -> bool:
        """Deletes a staging session file after successful promotion to PostgreSQL."""
        p = self._get_session_path(doc_code)
        if p.exists():
            p.unlink()
            return True
        return False
