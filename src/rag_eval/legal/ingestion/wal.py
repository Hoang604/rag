"""Write-Ahead Logging (WAL) and Event-Sourcing storage engine for statutory staging sessions.

Provides atomic, append-only transaction logging, immutable genesis baseline snapshots,
and pure deterministic replay for legal document staging.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from rag_eval.legal.ingestion.staging.models import (
    StagingChunk,
    StagingChunkDelta,
    StagingEdge,
    StagingMutationRecord,
    StagingStatus,
)
from rag_eval.legal.ingestion.staging.session import StagingDocumentSession
from rag_eval.legal.schemas import (
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
)

logger = logging.getLogger(__name__)


def compute_payload_checksum(payload: Mapping[str, object]) -> str:
    """Computes deterministic SHA-256 digest over serialized payload dict."""
    serialized = json.dumps(dict(payload), sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


class GenesisSnapshot(BaseModel):
    """Immutable statutory document baseline snapshot captured at LSN 0."""

    model_config = ConfigDict(extra="ignore")

    doc_code: str = Field(..., description="Unique statutory document code")
    title: str = Field(..., description="Document title")
    effective_date: datetime.date = Field(..., description="Effective date")
    expiration_date: datetime.date | None = Field(None, description="Expiration date")
    raw_text: str = Field(..., description="Full raw statutory source text")
    doc_metadata: dict[str, object] = Field(default_factory=dict, description="Document metadata")
    initial_chunks: list[dict[str, object]] = Field(
        default_factory=list, description="Initial parsed AST/CPHC chunks"
    )
    initial_edges: list[dict[str, object]] = Field(
        default_factory=list, description="Initial extracted relational edges"
    )
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="Snapshot creation UTC timestamp",
    )
    genesis_hash: str = Field(default="", description="SHA-256 digest of genesis contents")

    @classmethod
    def create(
        cls,
        doc_code: str,
        title: str,
        effective_date: datetime.date,
        expiration_date: datetime.date | None,
        raw_text: str,
        doc_metadata: dict[str, object],
        initial_chunks: list[dict[str, object]],
        initial_edges: list[dict[str, object]],
    ) -> GenesisSnapshot:
        """Factory computing genesis SHA-256 hash across canonical fields."""
        hasher = hashlib.sha256()
        hasher.update(doc_code.encode("utf-8"))
        hasher.update(raw_text.encode("utf-8"))
        hasher.update(str(len(initial_chunks)).encode("utf-8"))
        hasher.update(str(len(initial_edges)).encode("utf-8"))
        digest = hasher.hexdigest()

        return cls(
            doc_code=doc_code,
            title=title,
            effective_date=effective_date,
            expiration_date=expiration_date,
            raw_text=raw_text,
            doc_metadata=doc_metadata,
            initial_chunks=initial_chunks,
            initial_edges=initial_edges,
            genesis_hash=digest,
        )


class WALRecord(BaseModel):
    """Monotonic append-only log record representing a discrete staging transformation."""

    model_config = ConfigDict(extra="ignore")

    lsn: int = Field(..., ge=0, description="Log Sequence Number, strictly monotonic from 0")
    timestamp: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC),
        description="UTC timestamp of entry",
    )
    actor: str = Field(..., description="'SYSTEM' | 'AGENT' | 'HUMAN:<username>'")
    op_type: str = Field(
        ...,
        description="'GENESIS' | 'CHUNK_PATCHED' | 'EDGES_ATTACHED' | 'EDGE_REMOVED' | 'SUBTREE_REPARENTED' | 'STATUS_TRANSITION' | 'GRAPH_EDGE_PROPOSED' | 'GRAPH_EDGE_APPROVED' | 'PROMOTED_TO_PRODUCTION'",
    )
    description: str = Field(..., description="Human-readable summary of operation")
    payload: dict[str, object] = Field(default_factory=dict, description="Operation payload")
    checksum: str = Field(..., description="SHA-256 digest of serialized payload")


class CheckpointState(BaseModel):
    """Materialized projection snapshot cached for fast O(1) reads with LSN watermark."""

    model_config = ConfigDict(extra="ignore")

    checkpoint_lsn: int = Field(..., ge=0, description="Highest LSN applied to this projection")
    session_data: dict[str, object] = Field(..., description="Serialized StagingDocumentSession data")


class WALSessionStore:
    """Manages disk-based WAL journal, immutable genesis snapshot, and checkpoint state."""

    def __init__(self, session_dir: Path | str) -> None:
        self.session_dir = Path(session_dir)
        self.genesis_file = self.session_dir / "genesis.json"
        self.wal_file = self.session_dir / "wal.jsonl"
        self.state_file = self.session_dir / "state.json"

    def exists(self) -> bool:
        """Returns True if both genesis.json and wal.jsonl exist."""
        return self.genesis_file.exists() and self.wal_file.exists()

    def init_genesis(
        self,
        genesis: GenesisSnapshot,
    ) -> tuple[WALRecord, StagingDocumentSession]:
        """Initializes session directory, writes immutable genesis.json, LSN 0 in wal.jsonl, and initial state.json."""
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write genesis.json
        genesis_json = genesis.model_dump_json(indent=2)
        tmp_genesis = self.session_dir / f"genesis.json.tmp.{os.getpid()}"
        with open(tmp_genesis, "w", encoding="utf-8") as f:
            f.write(genesis_json)
            f.flush()
            os.fsync(f.fileno())
        tmp_genesis.replace(self.genesis_file)

        # 2. Write LSN 0 record to wal.jsonl
        rec_0_payload = {
            "doc_code": genesis.doc_code,
            "chunks_count": len(genesis.initial_chunks),
            "edges_count": len(genesis.initial_edges),
            "genesis_hash": genesis.genesis_hash,
        }
        rec_0 = WALRecord(
            lsn=0,
            timestamp=genesis.created_at,
            actor="SYSTEM",
            op_type="GENESIS",
            description=f"Initialized genesis baseline for '{genesis.doc_code}' with {len(genesis.initial_chunks)} chunks.",
            payload=rec_0_payload,
            checksum=compute_payload_checksum(rec_0_payload),
        )

        tmp_wal = self.session_dir / f"wal.jsonl.tmp.{os.getpid()}"
        with open(tmp_wal, "w", encoding="utf-8") as f:
            f.write(rec_0.model_dump_json() + "\n")
            f.flush()
            os.fsync(f.fileno())
        tmp_wal.replace(self.wal_file)

        # 3. Build initial materialized StagingDocumentSession
        chunks = [StagingChunk.model_validate(c) for c in genesis.initial_chunks]
        edges = [StagingEdge.model_validate(e) for e in genesis.initial_edges]
        mutation_0 = StagingMutationRecord(
            actor=rec_0.actor,
            action_type=rec_0.op_type,
            description=rec_0.description,
            timestamp=rec_0.timestamp,
            diff_payload={"lsn": 0, **rec_0_payload},
        )

        session = StagingDocumentSession(
            doc_code=genesis.doc_code,
            title=genesis.title,
            status=StagingStatus.DRAFT,
            effective_date=genesis.effective_date,
            expiration_date=genesis.expiration_date,
            created_at=genesis.created_at,
            updated_at=genesis.created_at,
            committed_at=None,
            promoted_at=None,
            raw_text=genesis.raw_text,
            doc_metadata=genesis.doc_metadata,
            chunks=chunks,
            edges=edges,
            raw_ast_snapshot=genesis.initial_chunks,
            mutation_history=[mutation_0],
        )

        self.save_checkpoint(session)
        return rec_0, session

    def get_head_lsn(self) -> int:
        """Returns the highest LSN written in wal.jsonl, or -1 if empty."""
        if not self.wal_file.exists():
            return -1

        last_line: str = ""
        with open(self.wal_file, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    last_line = stripped

        if not last_line:
            return -1

        try:
            data = json.loads(last_line)
            return int(data.get("lsn", -1))
        except (json.JSONDecodeError, ValueError, TypeError):
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Corrupted trailing WAL line in {self.wal_file}",
                data={"session_dir": str(self.session_dir)},
            )

    def append_record(
        self,
        actor: str,
        op_type: str,
        description: str,
        payload: Mapping[str, object],
    ) -> tuple[WALRecord, StagingDocumentSession]:
        """Appends a new record to wal.jsonl with monotonic LSN, applies mutation to projection, and writes checkpoint."""
        if not self.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Cannot append to non-existent WAL session at {self.session_dir}",
                data={"session_dir": str(self.session_dir)},
            )

        head_lsn = self.get_head_lsn()
        next_lsn = head_lsn + 1
        checksum = compute_payload_checksum(payload)
        now = datetime.datetime.now(datetime.UTC)

        record = WALRecord(
            lsn=next_lsn,
            timestamp=now,
            actor=actor,
            op_type=op_type,
            description=description,
            payload=dict(payload),
            checksum=checksum,
        )

        session = self.load_materialized_session()
        self.apply_record_to_session(session, record)

        line = record.model_dump_json() + "\n"
        with open(self.wal_file, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        self.save_checkpoint(session)
        return record, session

    def read_wal(self, since_lsn: int = 0) -> list[WALRecord]:
        """Reads and validates sequential WAL records starting from since_lsn."""
        if not self.wal_file.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"wal.jsonl missing in session directory {self.session_dir}",
                data={"session_dir": str(self.session_dir)},
            )

        records: list[WALRecord] = []
        with open(self.wal_file, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    rec = WALRecord.model_validate(data)
                except (json.JSONDecodeError, ValueError, TypeError) as exc:
                    raise LegalDomainError(
                        error_code=E_CORPUS_INTEGRITY_VIOLATION,
                        message=f"Corrupted WAL record at line {line_no} in {self.wal_file}: {exc}",
                        data={"session_dir": str(self.session_dir), "line_no": line_no},
                    ) from exc

                expected_checksum = compute_payload_checksum(rec.payload)
                if rec.checksum != expected_checksum:
                    raise LegalDomainError(
                        error_code=E_CORPUS_INTEGRITY_VIOLATION,
                        message=f"Checksum verification failed for LSN {rec.lsn} in {self.wal_file}",
                        data={"lsn": rec.lsn, "stored": rec.checksum, "computed": expected_checksum},
                    )

                if rec.lsn >= since_lsn:
                    records.append(rec)

        return records

    def load_genesis(self) -> GenesisSnapshot:
        """Loads and verifies immutable genesis baseline snapshot."""
        if not self.genesis_file.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"genesis.json missing in session directory {self.session_dir}",
                data={"session_dir": str(self.session_dir)},
            )

        try:
            content = self.genesis_file.read_text(encoding="utf-8")
            data = json.loads(content)
            return GenesisSnapshot.model_validate(data)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"genesis.json corrupted in {self.session_dir}: {exc}",
                data={"session_dir": str(self.session_dir)},
            ) from exc

    def replay(self, up_to_lsn: int | None = None) -> tuple[StagingDocumentSession, int]:
        """Pure deterministic reducer: replays genesis across wal.jsonl up to specified LSN."""
        genesis = self.load_genesis()
        wal_records = self.read_wal(since_lsn=0)

        chunks = [StagingChunk.model_validate(c) for c in genesis.initial_chunks]
        edges = [StagingEdge.model_validate(e) for e in genesis.initial_edges]

        session = StagingDocumentSession(
            doc_code=genesis.doc_code,
            title=genesis.title,
            status=StagingStatus.DRAFT,
            effective_date=genesis.effective_date,
            expiration_date=genesis.expiration_date,
            created_at=genesis.created_at,
            updated_at=genesis.created_at,
            committed_at=None,
            promoted_at=None,
            raw_text=genesis.raw_text,
            doc_metadata=genesis.doc_metadata,
            chunks=chunks,
            edges=edges,
            raw_ast_snapshot=genesis.initial_chunks,
            mutation_history=[],
        )

        applied_lsn = -1

        for expected_lsn, rec in enumerate(wal_records):
            if rec.lsn != expected_lsn:
                raise LegalDomainError(
                    error_code=E_CORPUS_INTEGRITY_VIOLATION,
                    message=f"Broken LSN monotonicity: expected {expected_lsn}, got {rec.lsn}",
                    data={"expected_lsn": expected_lsn, "actual_lsn": rec.lsn},
                )

            if up_to_lsn is not None and rec.lsn > up_to_lsn:
                break

            self.apply_record_to_session(session, rec)
            applied_lsn = rec.lsn

        return session, applied_lsn

    def apply_record_to_session(self, session: StagingDocumentSession, record: WALRecord) -> None:
        """Pure reducer function applying a single WALRecord to a StagingDocumentSession."""
        session.updated_at = record.timestamp

        if record.op_type == "GENESIS":
            mutation = StagingMutationRecord(
                actor=record.actor,
                action_type="GENESIS",
                description=record.description,
                timestamp=record.timestamp,
                diff_payload={"lsn": record.lsn, **record.payload},
            )
            session.mutation_history = [mutation]
            return

        if record.op_type == "CHUNK_PATCHED":
            raw_deltas = record.payload.get("deltas")
            removed_paths_raw = record.payload.get("removed_paths")
            cascade = bool(record.payload.get("cascade_breadcrumbs", True))

            deltas: list[StagingChunkDelta] = []
            if isinstance(raw_deltas, list):
                deltas = [StagingChunkDelta.model_validate(d) for d in raw_deltas]

            removed_paths: list[str] | None = None
            if isinstance(removed_paths_raw, list):
                removed_paths = [str(p) for p in removed_paths_raw]

            session.apply_chunk_deltas(
                deltas=deltas,
                removed_paths=removed_paths,
                cascade_breadcrumbs=cascade,
                actor=record.actor,
            )
            return

        if record.op_type == "EDGES_ATTACHED":
            raw_edges = record.payload.get("edges")
            edges = [StagingEdge.model_validate(e) for e in raw_edges] if isinstance(raw_edges, list) else []
            session.validate_and_attach_edges(edges=edges, actor=record.actor)
            return

        if record.op_type == "GRAPH_EDGE_PROPOSED":
            raw_edges = record.payload.get("edges")
            if isinstance(raw_edges, list):
                for e_dict in raw_edges:
                    if isinstance(e_dict, dict):
                        clean_src = str(e_dict.get("source_path", ""))
                        clean_tgt = str(e_dict.get("target_path")) if e_dict.get("target_path") else None
                        new_edge = StagingEdge(
                            source_path=clean_src,
                            target_path=clean_tgt,
                            target_external_ref=e_dict.get("target_external_ref"),
                            relation_type=str(e_dict.get("relation_type")),
                            citation_text=e_dict.get("citation_text"),
                            metadata=dict(e_dict.get("metadata") or {}) | {"proposed": True},
                        )
                session.edges = [
                    e
                    for e in session.edges
                    if not (
                        e.source_path == new_edge.source_path
                        and e.target_path == new_edge.target_path
                        and e.relation_type == new_edge.relation_type
                    )
                ] + [new_edge]

            session.mutation_history.append(
                StagingMutationRecord(
                    actor=record.actor,
                    action_type="GRAPH_EDGE_PROPOSED",
                    description=record.description,
                    timestamp=record.timestamp,
                    diff_payload=record.payload,
                )
            )
            return

        if record.op_type == "EDGE_REMOVED":
            src = record.payload.get("source_path")
            tgt = record.payload.get("target_path")
            rel = record.payload.get("relation_type")
            session.edges = [
                e
                for e in session.edges
                if not (e.source_path == src and e.target_path == tgt and e.relation_type == rel)
            ]
            session.mutation_history.append(
                StagingMutationRecord(
                    actor=record.actor,
                    action_type="EDGE_REMOVED",
                    description=record.description,
                    timestamp=record.timestamp,
                    diff_payload=record.payload,
                )
            )
            return

        if record.op_type == "SUBTREE_REPARENTED":
            old_p = str(record.payload.get("old_path_prefix", ""))
            new_p = str(record.payload.get("new_path_prefix", ""))
            session.reparent_subtree(
                old_path_prefix=old_p,
                new_path_prefix=new_p,
                dry_run=False,
                actor=record.actor,
            )
            return

        if record.op_type.startswith("STATUS_TRANSITION_") or record.op_type == "STATUS_TRANSITION":
            new_status_str = record.payload.get("new_status") or record.payload.get("status")
            if new_status_str:
                new_status = StagingStatus(new_status_str)
                session.status = new_status
                if new_status == StagingStatus.AGENT_COMMITTED:
                    session.committed_at = record.timestamp
                elif new_status == StagingStatus.PROMOTED:
                    session.promoted_at = record.timestamp
            if "amendment_baseline_snapshot" in record.payload:
                session.doc_metadata["amendment_baseline_snapshot"] = record.payload[
                    "amendment_baseline_snapshot"
                ]
            session.mutation_history.append(
                StagingMutationRecord(
                    actor=record.actor,
                    action_type=record.op_type,
                    description=record.description,
                    timestamp=record.timestamp,
                    diff_payload=record.payload,
                )
            )
            return

        if record.op_type == "CHUNKS_FINALIZED":
            raw_paths = record.payload.get("paths")
            paths_list = [str(p) for p in raw_paths] if isinstance(raw_paths, (list, tuple)) else []
            session.finalize_chunks(
                paths=paths_list,
                actor=record.actor,
            )
            return

        if record.op_type == "PROMOTED_TO_PRODUCTION":
            session.status = StagingStatus.PROMOTED
            session.promoted_at = record.timestamp
            session.mutation_history.append(
                StagingMutationRecord(
                    actor=record.actor,
                    action_type="PROMOTED_TO_PRODUCTION",
                    description=record.description,
                    timestamp=record.timestamp,
                    diff_payload=record.payload,
                )
            )
            return

        session.mutation_history.append(
            StagingMutationRecord(
                actor=record.actor,
                action_type=record.op_type,
                description=record.description,
                timestamp=record.timestamp,
                diff_payload=record.payload,
            )
        )

    def load_materialized_session(self) -> StagingDocumentSession:
        """Loads state.json if present and synchronized with head LSN; otherwise executes catch-up replay."""
        if not self.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session does not exist at {self.session_dir}",
                data={"session_dir": str(self.session_dir)},
            )

        head_lsn = self.get_head_lsn()

        if not self.state_file.exists():
            session, _ = self.replay()
            self.save_checkpoint(session)
            return session

        try:
            content = self.state_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if "checkpoint_lsn" in data and "session_data" in data:
                chk_lsn = int(data["checkpoint_lsn"])
                if chk_lsn < head_lsn:
                    session, _ = self.replay()
                    self.save_checkpoint(session)
                    return session
                return StagingDocumentSession.model_validate(data["session_data"])
            else:
                session, _ = self.replay()
                self.save_checkpoint(session)
                return session
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning(
                "Materialized checkpoint state corrupted at %s, executing full replay: %s",
                self.state_file,
                exc,
            )
            session, _ = self.replay()
            self.save_checkpoint(session)
            return session

    def save_checkpoint(self, session: StagingDocumentSession) -> Path:
        """Atomically persists session state as state.json checkpoint with checkpoint_lsn watermark."""
        head_lsn = self.get_head_lsn()
        chk = CheckpointState(
            checkpoint_lsn=max(0, head_lsn),
            session_data=session.model_dump(mode="json"),
        )
        content = chk.model_dump_json(indent=2)
        tmp_file = self.session_dir / f"state.json.tmp.{os.getpid()}"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            tmp_file.replace(self.state_file)
        except (OSError, RuntimeError):
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            raise
        return self.state_file
