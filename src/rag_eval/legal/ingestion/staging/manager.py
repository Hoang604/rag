"""StagingManager coordinator managing disk storage, WALSessionStore, and session lifecycle."""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.ingestion.staging.models import (
    DEFAULT_STAGING_DIR,
    ChunkReviewStatus,
    StagingChunk,
    StagingChunkDelta,
    StagingEdge,
    StagingSessionSummary,
    StagingStatus,
    StgReparentResult,
)
from rag_eval.legal.ingestion.staging.session import StagingDocumentSession
from rag_eval.legal.ingestion.wal import GenesisSnapshot, WALRecord, WALSessionStore
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
    sanitize_ltree_label,
    validate_ltree_path,
)

logger = logging.getLogger(__name__)


class StagingManager:
    """Manages disk-based staging sessions for two-phase statutory ingestion via WALSessionStore.

    Enforces strict single-path WAL directory architecture (.cache/stg/<sanitized_doc_code>/).
    Zero defensive fallbacks, zero legacy flat file shims, and zero silent defaults.
    """

    def __init__(self, staging_dir: Path | str = DEFAULT_STAGING_DIR) -> None:
        self.staging_dir = Path(staging_dir)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_dir(self, doc_code: str) -> Path:
        sanitized = sanitize_ltree_label(doc_code)
        return self.staging_dir / sanitized

    def _get_wal_store(self, doc_code: str) -> WALSessionStore:
        return WALSessionStore(self._get_session_dir(doc_code))

    def create_session_from_raw(
        self,
        doc_code: str,
        title: str,
        raw_text: str,
        effective_date: datetime.date,
        expiration_date: datetime.date | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StagingDocumentSession:
        """Parses raw text via AST and CPHC, builds GenesisSnapshot, and initializes WAL directory session."""
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

        wal_store = self._get_wal_store(doc_code)
        genesis = GenesisSnapshot.create(
            doc_code=doc_code,
            title=title,
            effective_date=effective_date,
            expiration_date=expiration_date,
            raw_text=raw_text,
            doc_metadata=metadata or {},
            initial_chunks=[c.model_dump(mode="json") for c in stg_chunks],
            initial_edges=[e.model_dump(mode="json") for e in stg_edges],
        )

        _, session = wal_store.init_genesis(genesis)
        return session

    def load_session(self, doc_code: str) -> StagingDocumentSession:
        """Loads an existing staging session from WAL store. Fails fast if directory does not exist."""
        wal_store = self._get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code, "staging_path": str(wal_store.session_dir)},
            )
        return wal_store.load_materialized_session()

    def save_session(self, session: StagingDocumentSession) -> Path:
        """Persists state.json checkpoint for fast read access."""
        wal_store = self._get_wal_store(session.doc_code)
        return wal_store.save_checkpoint(session)

    def load_all_sessions(self) -> list[StagingDocumentSession]:
        """Loads every active WAL staging session on disk."""
        sessions: list[StagingDocumentSession] = []
        if not self.staging_dir.exists():
            return sessions

        for sub_dir in sorted(self.staging_dir.iterdir()):
            if not sub_dir.is_dir() or sub_dir.name.startswith("."):
                continue
            wal_store = WALSessionStore(sub_dir)
            if not wal_store.exists():
                continue
            try:
                sessions.append(wal_store.load_materialized_session())
            except (OSError, ValueError, LegalDomainError):
                logger.warning("Skipping unreadable staging session at %s", sub_dir)

        return sessions

    def resolve_cross_document_edges(self) -> dict[str, int]:
        """Links edges that cite another staged document to its actual chunks."""
        sessions = self.load_all_sessions()
        known_codes: dict[str, str] = {}
        for s in sessions:
            known_codes[normalize_doc_code(s.doc_code)] = s.doc_code
            for alias in s.doc_metadata.get("consolidates") or ():
                known_codes.setdefault(normalize_doc_code(str(alias)), s.doc_code)
        indexes = {
            s.doc_code: build_path_index([c.path for c in s.chunks]) for s in sessions
        }
        titles = {normalize_title(s.title): s.doc_code for s in sessions}

        resolved: dict[str, int] = {}
        for session in sessions:
            count = 0
            resolved_edges: list[dict[str, Any]] = []
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
                resolved_edges.append(edge.model_dump(mode="json"))
                count += 1

            if count:
                wal_store = self._get_wal_store(session.doc_code)
                wal_store.append_record(
                    actor="SYSTEM",
                    op_type="EDGES_ATTACHED",
                    description=f"Resolved {count} cross-document relation edges.",
                    payload={"edges": resolved_edges},
                )
            resolved[session.doc_code] = count
        return resolved

    def patch_chunks(
        self,
        doc_code: str,
        updated_chunks: Sequence[StagingChunkDelta | StagingChunk | dict[str, Any]] | None = None,
        removed_paths: list[str] | None = None,
        cascade_breadcrumbs: bool = True,
        actor: str = "AGENT",
    ) -> StagingDocumentSession:
        """Appends CHUNK_PATCHED record to WAL journal and updates materialized state."""
        wal_store = self._get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        parsed_deltas: list[StagingChunkDelta] = []
        if updated_chunks:
            for item in updated_chunks:
                if isinstance(item, StagingChunkDelta):
                    parsed_deltas.append(item)
                elif isinstance(item, StagingChunk):
                    parsed_deltas.append(
                        StagingChunkDelta(
                            path=item.path,
                            verbatim_text=item.verbatim_text,
                            contextualized_text=item.contextualized_text,
                            lead_sentence=item.lead_sentence,
                            metadata=item.metadata,
                            effective_date=item.effective_date,
                            expiration_date=item.expiration_date,
                            review_status=item.review_status,
                        )
                    )
                elif isinstance(item, dict):
                    parsed_deltas.append(StagingChunkDelta.model_validate(item))

        payload = {
            "deltas": [d.model_dump(mode="json") for d in parsed_deltas],
            "removed_paths": removed_paths or [],
            "cascade_breadcrumbs": cascade_breadcrumbs,
        }
        _, session = wal_store.append_record(
            actor=actor,
            op_type="CHUNK_PATCHED",
            description=f"Patched {len(parsed_deltas)} chunks and removed {len(removed_paths or [])} paths.",
            payload=payload,
        )
        return session

    def add_edges(
        self,
        doc_code: str,
        edges: Sequence[StagingEdge | dict[str, Any]],
        actor: str = "AGENT",
    ) -> StagingDocumentSession:
        """Appends EDGES_ATTACHED record to WAL journal and updates materialized state."""
        wal_store = self._get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        parsed_edges: list[StagingEdge] = []
        for e in edges:
            if isinstance(e, StagingEdge):
                parsed_edges.append(e)
            elif isinstance(e, dict):
                parsed_edges.append(StagingEdge.model_validate(e))

        payload = {
            "edges": [e.model_dump(mode="json") for e in parsed_edges],
        }
        _, session = wal_store.append_record(
            actor=actor,
            op_type="EDGES_ATTACHED",
            description=f"Attached {len(parsed_edges)} relation edges.",
            payload=payload,
        )
        return session

    def remove_edge(
        self,
        doc_code: str,
        source_path: str,
        target_path: str | None = None,
        relation_type: str = "",
        actor: str = "HUMAN:reviewer",
    ) -> StagingDocumentSession:
        """Appends EDGE_REMOVED record to WAL journal and updates materialized state."""
        wal_store = self._get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        payload = {
            "source_path": source_path,
            "target_path": target_path,
            "relation_type": relation_type,
        }
        _, session = wal_store.append_record(
            actor=actor,
            op_type="EDGE_REMOVED",
            description=f"Removed edge from '{source_path}' to '{target_path}' ({relation_type}).",
            payload=payload,
        )
        return session

    def reparent_node(
        self,
        doc_code: str,
        old_path_prefix: str,
        new_path_prefix: str,
        dry_run: bool = False,
        actor: str = "AGENT",
    ) -> tuple[StagingDocumentSession, StgReparentResult]:
        """Validates reparenting; if not dry_run, appends SUBTREE_REPARENTED record to WAL."""
        session = self.load_session(doc_code)
        result = session.reparent_subtree(
            old_path_prefix=old_path_prefix,
            new_path_prefix=new_path_prefix,
            dry_run=dry_run,
            actor=actor,
        )

        if not dry_run:
            wal_store = self._get_wal_store(doc_code)
            payload = {
                "old_path_prefix": old_path_prefix,
                "new_path_prefix": new_path_prefix,
                "affected_chunks": result.affected_chunks_count,
                "affected_edges": result.affected_edges_count,
            }
            _, session = wal_store.append_record(
                actor=actor,
                op_type="SUBTREE_REPARENTED",
                description=f"Migrated subtree '{old_path_prefix}' to '{new_path_prefix}'.",
                payload=payload,
            )

        return session, result

    def list_sessions(self) -> list[StagingSessionSummary]:
        """Discovers and lists summaries of all WAL sessions in the staging directory."""
        summaries: list[StagingSessionSummary] = []
        if not self.staging_dir.exists():
            return summaries

        for sub_dir in sorted(self.staging_dir.iterdir()):
            if not sub_dir.is_dir() or sub_dir.name.startswith("."):
                continue
            wal_store = WALSessionStore(sub_dir)
            if not wal_store.exists():
                continue
            try:
                session = wal_store.load_materialized_session()
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
            except (json.JSONDecodeError, ValueError, KeyError, OSError, LegalDomainError) as exc:
                logger.warning("Skipping unreadable staging session directory %s: %s", sub_dir, exc)

        return summaries

    def update_session_status(
        self,
        doc_code: str,
        status: StagingStatus,
        actor: str,
        description: str,
    ) -> StagingDocumentSession:
        """Appends status transition record to WAL journal and updates materialized state."""
        wal_store = self._get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        payload = {
            "new_status": status.value,
            "description": description,
        }
        _, session = wal_store.append_record(
            actor=actor,
            op_type=f"STATUS_TRANSITION_{status.value}",
            description=description or f"Transitioned status to {status.value}",
            payload=payload,
        )
        return session

    def delete_session(self, doc_code: str) -> bool:
        """Deletes a staging session directory from disk."""
        s_dir = self._get_session_dir(doc_code)
        if s_dir.exists() and s_dir.is_dir():
            for child in s_dir.iterdir():
                child.unlink()
            s_dir.rmdir()
            return True
        return False

    def replay_session(
        self,
        doc_code: str,
        up_to_lsn: int | None = None,
    ) -> tuple[StagingDocumentSession, int]:
        """Deterministically replays session from genesis to up_to_lsn and returns (session, lsn)."""
        wal_store = self._get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )
        return wal_store.replay(up_to_lsn=up_to_lsn)

    def get_wal_records(self, doc_code: str, since_lsn: int = 0) -> list[WALRecord]:
        """Returns full ordered WAL history for the document."""
        wal_store = self._get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )
        return wal_store.read_wal(since_lsn=since_lsn)

    def finalize_chunks(
        self,
        doc_code: str,
        paths: Sequence[str],
        actor: str = "AGENT",
    ) -> tuple[StagingDocumentSession, int]:
        """Atomically locks candidate chunks as FINALIZED via WAL append."""
        wal_store = self._get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )
        session = self.load_session(doc_code)
        if session.status == StagingStatus.PROMOTED:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể chỉnh sửa phiên staging ở trạng thái '{session.status.value}'.",
                data={"doc_code": doc_code, "status": session.status.value},
            )
        clean_paths = [validate_ltree_path(p) for p in paths]
        payload = {"paths": clean_paths}
        _, session = wal_store.append_record(
            actor=actor,
            op_type="CHUNKS_FINALIZED",
            description=f"Finalized {len(clean_paths)} chunks.",
            payload=payload,
        )
        finalized_count = sum(
            1
            for c in session.chunks
            if c.path in clean_paths and c.review_status == ChunkReviewStatus.FINALIZED
        )
        return session, finalized_count

    def poll_pending_chunks(
        self,
        doc_code: str,
        limit: int = 10,
        path_prefix: str | None = None,
    ) -> tuple[list[StagingChunk], dict[str, Any]]:
        """Queries pending chunks and calculates progress statistics."""
        session = self.load_session(doc_code)
        target_pool = session.chunks
        if path_prefix:
            clean_pre = validate_ltree_path(path_prefix)
            target_pool = [
                c
                for c in session.chunks
                if c.path == clean_pre or c.path.startswith(f"{clean_pre}.")
            ]

        total_chunks = len(target_pool)
        finalized_count = sum(
            1 for c in target_pool if c.review_status == ChunkReviewStatus.FINALIZED
        )
        pending_chunks = [
            c for c in target_pool if c.review_status == ChunkReviewStatus.PENDING
        ]

        stats = {
            "total_chunks": total_chunks,
            "finalized_count": finalized_count,
            "pending_count": total_chunks - finalized_count,
            "progress_percent": (
                round((finalized_count / total_chunks * 100.0), 1)
                if total_chunks > 0
                else 0.0
            ),
        }
        return pending_chunks[:limit], stats
