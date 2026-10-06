from __future__ import annotations

import datetime
import json
import logging
import uuid
from pathlib import Path

import asyncpg

from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.schemas.domain import (
    ChunkReviewStatus,
    RelationEdge,
    StagingStatus,
    StatutoryChunk,
)
from rag_eval.legal.schemas.staging import (
    SessionSummary,
)


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
from rag_eval.legal.errors import (
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
)
from rag_eval.legal.ingestion.staging.session import StagingDocumentSession
from rag_eval.legal.ingestion.wal import GenesisSnapshot, WALRecord, WALSessionStore
from rag_eval.legal.text import (
    sanitize_ltree_label,
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

    def get_wal_store(self, doc_code: str) -> WALSessionStore:
        return WALSessionStore(self._get_session_dir(doc_code))

    def create_session_from_raw(
        self,
        doc_code: str,
        title: str,
        raw_text: str,
        effective_date: datetime.date,
        expiration_date: datetime.date | None = None,
        metadata: dict[str, object] | None = None,
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
            StatutoryChunk(
                path=c.path,
                verbatim_text=c.verbatim_text,
                contextualized_text=c.contextualized_text,
                start_line=c.start_line,
                end_line=c.end_line,
                metadata=c.metadata,
                effective_date=c.effective_date,
                expiration_date=c.expiration_date,
            )
            for c in canonical_chunks
        ]

        wal_store = self.get_wal_store(doc_code)
        genesis = GenesisSnapshot.create(
            doc_code=doc_code,
            title=title,
            effective_date=effective_date,
            expiration_date=expiration_date,
            raw_text=raw_text,
            doc_metadata=metadata or {},
            initial_chunks=[c.model_dump(mode="json") for c in stg_chunks],
            initial_edges=[],
        )

        _, session = wal_store.init_genesis(genesis)
        return session

    def session_exists(self, doc_code: str) -> bool:
        """Returns True if local WAL session directory exists on disk."""
        return self.get_wal_store(doc_code).exists()

    async def load_or_hydrate_session(
        self,
        doc_code: str,
        pool: asyncpg.Pool | None = None,
    ) -> StagingDocumentSession:
        """Loads session from local disk WAL store; if missing and pool provided, hydrates from PostgreSQL."""
        wal_store = self.get_wal_store(doc_code)
        if wal_store.exists():
            return wal_store.load_materialized_session()

        if pool is not None:
            return await self.hydrate_session_from_db(doc_code=doc_code, pool=pool)

        raise LegalDomainError(
            error_code=E_CORPUS_INTEGRITY_VIOLATION,
            message=(
                f"Staging session for document '{doc_code}' does not exist on disk at "
                f"{wal_store.session_dir} and no database pool was provided for hydration."
            ),
            data={"doc_code": doc_code, "staging_path": str(wal_store.session_dir)},
        )

    def load_session(self, doc_code: str) -> StagingDocumentSession:
        """Loads an existing staging session from WAL store. Fails fast if directory does not exist."""
        wal_store = self.get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code, "staging_path": str(wal_store.session_dir)},
            )
        return wal_store.load_materialized_session()

    def save_session(self, session: StagingDocumentSession) -> Path:
        """Persists state.json checkpoint for fast read access."""
        wal_store = self.get_wal_store(session.doc_code)
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



    def list_sessions(self) -> list[SessionSummary]:
        """Discovers and lists summaries of all WAL sessions in the staging directory."""
        summaries: list[SessionSummary] = []
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
                    SessionSummary(
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
        wal_store = self.get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )
        return wal_store.replay(up_to_lsn=up_to_lsn)

    def get_wal_records(self, doc_code: str, since_lsn: int = 0) -> list[WALRecord]:
        """Returns full ordered WAL history for the document."""
        wal_store = self.get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )
        return wal_store.read_wal(since_lsn=since_lsn)



    async def hydrate_session_from_db(
        self,
        doc_code: str,
        pool: asyncpg.Pool,
    ) -> StagingDocumentSession:
        """Reconstructs genesis.json, wal.jsonl, and state.json directly from PostgreSQL production tables."""
        from rag_eval.legal.db.repositories import LegalRepository
        from rag_eval.legal.schemas.domain import (
            ChunkMetadata,
            StatutoryRelationType,
            UnresolvedReference,
        )

        wal_store = self.get_wal_store(doc_code)
        if wal_store.exists():
            return wal_store.load_materialized_session()

        repo = LegalRepository(pool)
        doc = await repo.documents.get_by_code(doc_code)
        if not doc:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không tìm thấy văn bản '{doc_code}' trong cơ sở dữ liệu để hydrate.",
                data={"doc_code": doc_code},
            )

        doc_id: uuid.UUID = doc.id
        title: str = doc.title
        effective_date: datetime.date = doc.effective_date
        expiration_date: datetime.date | None = doc.expiration_date
        doc_metadata: dict[str, object] = dict(doc.metadata)
        raw_text: str = doc.raw_text or ""

        chunks = await repo.chunks.list_by_document(doc_id)
        chunk_ids = [c.id for c in chunks]
        chunk_uuid_to_path: dict[uuid.UUID, str] = {c.id: c.path for c in chunks}
        context_refs = await repo.context_refs.list_by_chunk_ids(chunk_ids)

        deps_by_chunk: dict[uuid.UUID, list[UnresolvedReference]] = {}
        for r in context_refs:
            if r.target_chunk_id is None:
                deps_by_chunk.setdefault(r.chunk_id, []).append(
                    UnresolvedReference(
                        source_path=chunk_uuid_to_path.get(r.chunk_id, ""),
                        dependency_text=r.citation_phrase or "",
                        dependency_type=(
                            "EXTERNAL_CITATION"
                            if r.dependency_type == "EXTERNAL_CITATION"
                            else "OPEN_ENDED"
                        ),
                        char_start=r.char_start,
                        char_end=r.char_end,
                        reason="DOC_NOT_IN_CORPUS",
                    )
                )

        stg_chunks: list[StatutoryChunk] = []
        for c in chunks:
            stg_chunks.append(
                StatutoryChunk(
                    path=c.path,
                    verbatim_text=c.verbatim_text,
                    contextualized_text=c.contextualized_text,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    metadata=ChunkMetadata.model_validate(c.metadata),
                    effective_date=c.effective_date,
                    expiration_date=c.expiration_date,
                    review_status=ChunkReviewStatus.REVIEWED,
                    finalization_state=c.finalization_state,
                    dangling_dependencies=deps_by_chunk.get(c.id, []),
                )
            )

        if not raw_text:
            doc_metadata["legacy_source_text_absent"] = True
            raw_text = "\n\n".join(c.verbatim_text for c in stg_chunks)

        edges_data = await repo.graph.list_edges_with_paths_for_chunks(chunk_ids)
        stg_edges: list[RelationEdge] = []
        for er in edges_data:
            stg_edges.append(
                RelationEdge(
                    source_path=str(er["source_path"]),
                    target_path=str(er["target_path"]),
                    relation_type=StatutoryRelationType(str(er["relation_type"])),
                    citation_text=str(er["citation_text"]) if er.get("citation_text") else None,
                )
            )

        genesis = GenesisSnapshot.create(
            doc_code=doc_code,
            title=title,
            effective_date=effective_date,
            expiration_date=expiration_date,
            raw_text=raw_text,
            doc_metadata=doc_metadata | {"hydrated_from_db": True},
            initial_chunks=[c.model_dump(mode="json") for c in stg_chunks],
            initial_edges=[e.model_dump(mode="json") for e in stg_edges],
        )
        _, session = wal_store.init_genesis(genesis)

        _, session = wal_store.append_record(
            actor="SYSTEM:hydrator",
            op_type="PROMOTED_TO_PRODUCTION",
            description=f"Hydrated baseline from production PostgreSQL for {doc_code}.",
            payload={"doc_id": str(doc_id), "source": "DATABASE_HYDRATION"},
        )
        session.status = StagingStatus.PROMOTED
        return session
