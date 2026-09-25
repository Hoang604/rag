from __future__ import annotations

import datetime
import json
import logging
import uuid
from collections.abc import Sequence
from pathlib import Path

import asyncpg

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
            StagingChunk(
                path=c.path,
                verbatim_text=c.verbatim_text,
                contextualized_text=c.contextualized_text,
                lead_sentence="",
                start_line=c.start_line,
                end_line=c.end_line,
                metadata=c.metadata,
                effective_date=c.effective_date,
                expiration_date=c.expiration_date,
            )
            for c in canonical_chunks
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
            initial_edges=[],
        )

        _, session = wal_store.init_genesis(genesis)
        return session

    def session_exists(self, doc_code: str) -> bool:
        """Returns True if local WAL session directory exists on disk."""
        return self._get_wal_store(doc_code).exists()

    async def load_or_hydrate_session(
        self,
        doc_code: str,
        pool: asyncpg.Pool | None = None,
    ) -> StagingDocumentSession:
        """Loads session from local disk WAL store; if missing and pool provided, hydrates from PostgreSQL."""
        wal_store = self._get_wal_store(doc_code)
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

    def patch_chunks(
        self,
        doc_code: str,
        updated_chunks: Sequence[StagingChunkDelta | StagingChunk | dict[str, object]] | None = None,
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
                            start_line=item.start_line,
                            end_line=item.end_line,
                            metadata=item.metadata,
                            effective_date=item.effective_date,
                            expiration_date=item.expiration_date,
                            review_status=item.review_status,
                            finalization_state=item.finalization_state,
                            dangling_dependencies=item.dangling_dependencies,
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
        edges: Sequence[StagingEdge | dict[str, object]],
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
        session = wal_store.load_materialized_session()
        if session.status not in (StagingStatus.DRAFT, StagingStatus.AMENDMENT):
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể chỉnh sửa phiên staging ở trạng thái '{session.status.value}'. Phiên làm việc phải ở trạng thái DRAFT hoặc AMENDMENT.",
                data={"doc_code": doc_code, "status": session.status.value},
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
        if session.status not in (StagingStatus.DRAFT, StagingStatus.AMENDMENT):
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể chỉnh sửa phiên staging ở trạng thái '{session.status.value}'. Phiên làm việc phải ở trạng thái DRAFT hoặc AMENDMENT.",
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
            if c.path in clean_paths and c.review_status == ChunkReviewStatus.REVIEWED
        )
        return session, finalized_count

    def poll_pending_chunks(
        self,
        doc_code: str,
        limit: int = 10,
        path_prefix: str | None = None,
    ) -> tuple[list[StagingChunk], dict[str, object]]:
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
            1 for c in target_pool if c.review_status != ChunkReviewStatus.PENDING
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

    def reopen_session_for_amendment(
        self,
        doc_code: str,
        actor: str = "AGENT",
        reason: str = "",
    ) -> StagingDocumentSession:
        """Reopens a PROMOTED statutory session into AMENDMENT status."""
        wal_store = self._get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        session = wal_store.load_materialized_session()
        if session.status == StagingStatus.AMENDMENT:
            return session
        if session.status != StagingStatus.PROMOTED:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Chỉ phiên ở trạng thái PROMOTED mới có thể mở lại để sửa đổi bổ sung (AMENDMENT). Hiện tại: '{session.status.value}'.",
                data={"doc_code": doc_code, "status": session.status.value},
            )

        snapshot = [c.model_dump(mode="json") for c in session.chunks]
        session.doc_metadata["amendment_baseline_snapshot"] = snapshot
        payload = {
            "previous_status": session.status.value,
            "new_status": StagingStatus.AMENDMENT.value,
            "reason": reason or "Opened errata / amendment session",
            "amendment_baseline_snapshot": snapshot,
        }
        _, session = wal_store.append_record(
            actor=actor,
            op_type="STATUS_TRANSITION_AMENDMENT",
            description=reason or f"Reopened session for '{doc_code}' into AMENDMENT status.",
            payload=payload,
        )
        return session

    async def hydrate_session_from_db(
        self,
        doc_code: str,
        pool: asyncpg.Pool,
    ) -> StagingDocumentSession:
        """Reconstructs genesis.json, wal.jsonl, and state.json directly from PostgreSQL production tables."""
        from rag_eval.legal.ingestion.staging.models import RelationType
        from rag_eval.legal.schemas import (
            ChunkMetadata,
            DanglingDependencyRecord,
            EdgeMetadata,
            FinalizationState,
        )

        wal_store = self._get_wal_store(doc_code)
        if wal_store.exists():
            return wal_store.load_materialized_session()

        async with pool.acquire() as conn:
            doc_row = await conn.fetchrow(
                "SELECT id, doc_code, title, effective_date, expiration_date, metadata, raw_text FROM documents WHERE doc_code = $1;",
                doc_code,
            )
            if not doc_row:
                raise LegalDomainError(
                    error_code=E_CORPUS_INTEGRITY_VIOLATION,
                    message=f"Không tìm thấy văn bản '{doc_code}' trong cơ sở dữ liệu để hydrate.",
                    data={"doc_code": doc_code},
                )

            doc_id: uuid.UUID = doc_row["id"]
            title: str = str(doc_row["title"])
            effective_date: datetime.date = doc_row["effective_date"]
            expiration_date: datetime.date | None = doc_row["expiration_date"]
            doc_metadata: dict[str, object] = (
                json.loads(doc_row["metadata"])
                if isinstance(doc_row["metadata"], str)
                else dict(doc_row["metadata"] or {})
            )
            raw_text: str = str(doc_row["raw_text"] or "")

            chunk_rows = await conn.fetch(
                """
                SELECT id, path::text AS path, verbatim_text, contextualized_text,
                       start_line, end_line, metadata, effective_date, expiration_date, finalization_state
                FROM chunks
                WHERE document_id = $1
                ORDER BY path ASC;
                """,
                doc_id,
            )

            chunk_ids = [r["id"] for r in chunk_rows]
            dep_rows = await conn.fetch(
                """
                SELECT chunk_id, dependency_text, dependency_type, suggested_target_doc
                FROM chunk_dangling_dependencies
                WHERE chunk_id = ANY($1::uuid[]);
                """,
                chunk_ids,
            )
            deps_by_chunk: dict[uuid.UUID, list[DanglingDependencyRecord]] = {}
            for dr in dep_rows:
                deps_by_chunk.setdefault(dr["chunk_id"], []).append(
                    DanglingDependencyRecord(
                        dependency_text=str(dr["dependency_text"]),
                        dependency_type=str(dr["dependency_type"]),
                        suggested_target_doc=(
                            str(dr["suggested_target_doc"])
                            if dr["suggested_target_doc"]
                            else None
                        ),
                    )
                )

            stg_chunks: list[StagingChunk] = []
            chunk_uuid_to_path: dict[uuid.UUID, str] = {}
            for cr in chunk_rows:
                c_uuid = cr["id"]
                c_path = str(cr["path"])
                chunk_uuid_to_path[c_uuid] = c_path
                meta = (
                    json.loads(cr["metadata"])
                    if isinstance(cr["metadata"], str)
                    else dict(cr["metadata"] or {})
                )
                lead_sentence = str(meta.get("lead_sentence") or "")
                if not lead_sentence and cr["contextualized_text"] != cr["verbatim_text"]:
                    ctx = str(cr["contextualized_text"])
                    verb = str(cr["verbatim_text"])
                    if verb in ctx:
                        pre = ctx.split(verb)[0].strip()
                        lines = [line.strip() for line in pre.splitlines() if line.strip()]
                        if len(lines) >= 2:
                            lead_sentence = lines[-1]

                stg_chunks.append(
                    StagingChunk(
                        path=c_path,
                        verbatim_text=str(cr["verbatim_text"]),
                        contextualized_text=str(cr["contextualized_text"]),
                        lead_sentence=lead_sentence,
                        start_line=int(cr["start_line"]),
                        end_line=int(cr["end_line"]),
                        metadata=ChunkMetadata.model_validate(meta),
                        effective_date=cr["effective_date"],
                        expiration_date=cr["expiration_date"],
                        review_status=ChunkReviewStatus.REVIEWED,
                        finalization_state=FinalizationState(str(cr["finalization_state"])),
                        dangling_dependencies=deps_by_chunk.get(c_uuid, []),
                    )
                )

            if not raw_text:
                doc_metadata["legacy_source_text_absent"] = True
                raw_text = "\n\n".join(c.verbatim_text for c in stg_chunks)

            edge_rows = await conn.fetch(
                """
                SELECT e.source_chunk_id, e.target_chunk_id, e.target_external_ref,
                       e.relation_type, e.citation_text, e.metadata,
                       c2.path::text AS resolved_target_path
                FROM graph_edges e
                LEFT JOIN chunks c2 ON e.target_chunk_id = c2.id
                WHERE e.source_chunk_id = ANY($1::uuid[]);
                """,
                chunk_ids,
            )

            stg_edges: list[StagingEdge] = []
            for er in edge_rows:
                src_path = chunk_uuid_to_path.get(er["source_chunk_id"])
                if not src_path:
                    continue
                tgt_path = (
                    str(er["resolved_target_path"])
                    if er["resolved_target_path"]
                    else None
                )
                e_meta = (
                    json.loads(er["metadata"])
                    if isinstance(er["metadata"], str)
                    else dict(er["metadata"] or {})
                )
                stg_edges.append(
                    StagingEdge(
                        source_path=src_path,
                        target_path=tgt_path,
                        target_external_ref=(
                            str(er["target_external_ref"])
                            if er["target_external_ref"]
                            else None
                        ),
                        relation_type=RelationType(str(er["relation_type"])),
                        citation_text=(
                            str(er["citation_text"])
                            if er["citation_text"]
                            else None
                        ),
                        metadata=EdgeMetadata.model_validate(e_meta),
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
