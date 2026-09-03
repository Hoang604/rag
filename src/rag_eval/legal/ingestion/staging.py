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
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.ingestion.xref import (
    build_path_index,
    extract_document_citations,
    normalize_doc_code,
    normalize_title,
    resolve_across_documents,
)
from rag_eval.legal.schemas import (
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
    parse_flexible_date,
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
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    doc_metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    chunks: list[StagingChunk] = Field(default_factory=list, description="List of staged chunks")
    edges: list[StagingEdge] = Field(default_factory=list, description="List of staged graph edges")

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

        # Cross-references are extracted here rather than left to the agent.
        # An unrecorded reference is unrecoverable downstream: a clause whose
        # exceptions live in another khoản reads as unconditional, and an
        # amending decree with no edges into what it amends leaves the
        # superseded figure as retrievable as the current one.
        amends = str((metadata or {}).get("amends") or "") or None
        citations = extract_document_citations(
            {c.path: c.verbatim_text for c in stg_chunks},
            default_external_doc=amends,
            chunk_contexts={c.path: c.contextualized_text for c in stg_chunks},
            own_doc_code=doc_code,
        )
        stg_edges = [
            StagingEdge(
                source_path=citation.source_path,
                target_path=citation.target_path,
                target_external_ref=citation.target_external_ref,
                relation_type=citation.relation_type,
                citation_text=citation.citation_text,
                metadata=dict(citation.metadata),
            )
            for citation in citations
        ]
        logger.info(
            "extracted %d cross-reference edges for '%s' (%d resolved in-document)",
            len(stg_edges),
            doc_code,
            sum(1 for e in stg_edges if e.target_path is not None),
        )

        session = StagingDocumentSession(
            doc_code=doc_code,
            title=title,
            effective_date=effective_date,
            expiration_date=expiration_date,
            doc_metadata=metadata or {},
            chunks=stg_chunks,
            edges=stg_edges,
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

    def list_sessions(self) -> list[StagingDocumentSession]:
        """Loads every staging session on disk, skipping temporary files."""
        sessions: list[StagingDocumentSession] = []
        for path in sorted(self.staging_dir.glob("*.json")):
            if ".tmp." in path.name:
                continue
            try:
                sessions.append(
                    StagingDocumentSession.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except (OSError, ValueError):
                logger.warning("Skipping unreadable staging session at %s", path)
        return sessions

    def resolve_cross_document_edges(self) -> dict[str, int]:
        """Links edges that cite another staged document to its actual chunks.

        Extraction runs per document, so a citation out of the document can only
        be recorded as text at that point. This pass runs once every document is
        staged and turns those into real edges.

        It is what makes an amending decree mean anything: 238/2026/NĐ-CP is
        nothing but "sửa đổi, bổ sung điểm b khoản 8 Điều 13" repeated, and
        until each of those lands on 168/2024/NĐ-CP's own điểm b, the two texts
        sit in the index as equals with no record of which supersedes the other.

        Returns per-document counts of newly resolved edges.
        """
        sessions = self.list_sessions()
        known_codes: dict[str, str] = {}
        for s in sessions:
            known_codes[normalize_doc_code(s.doc_code)] = s.doc_code
            # A consolidated text is the base law with its amendments folded
            # in, so a citation naming the base code has to land here: after
            # 36/2024/QH15 was replaced by its consolidation, every reference
            # to it from the decrees would otherwise resolve to nothing.
            for alias in s.doc_metadata.get("consolidates") or ():
                known_codes.setdefault(normalize_doc_code(str(alias)), s.doc_code)
        indexes = {
            s.doc_code: build_path_index([c.path for c in s.chunks]) for s in sessions
        }
        titles = {normalize_title(s.title): s.doc_code for s in sessions}

        resolved: dict[str, int] = {}
        for session in sessions:
            count = 0
            for edge in session.edges:
                if edge.target_path is not None or not edge.target_external_ref:
                    continue
                hit = resolve_across_documents(
                    edge.target_external_ref, known_codes, indexes, titles
                )
                if hit is None:
                    continue
                target_doc, target_path = hit
                edge.target_path = target_path
                edge.metadata = dict(edge.metadata) | {
                    "resolution": "cross_document",
                    "target_doc_code": target_doc,
                }
                count += 1
            if count:
                self.save_session(session)
            resolved[session.doc_code] = count
        return resolved

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
