from __future__ import annotations

import logging
from collections.abc import Sequence

import asyncpg
from pydantic import BaseModel

from rag_eval.legal.errors import (
    E_AST_GROUNDING_VALIDATION,
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
)
from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.ingestion.staging.reducer import StagingStateReducer
from rag_eval.legal.ingestion.staging.session import StagingDocumentSession
from rag_eval.legal.ingestion.staging.validation import PreFlightValidator
from rag_eval.legal.ingestion.wal import WALRecord
from rag_eval.legal.schemas.domain import (
    ChunkReviewStatus,
    RelationEdge,
    RelationEdgeFilter,
    StagingStatus,
    StatutoryChunk,
)
from rag_eval.legal.schemas.retrieval import RawTextResult
from rag_eval.legal.schemas.staging import (
    BatchPatchRequest,
    BatchPatchResult,
    ChunkFinalizeStatus,
    ChunkProgressStats,
    CreateSessionRequest,
    FinalizeChunksRequest,
    FinalizeChunksResult,
    PendingChunkGroup,
    PendingChunkLeaf,
    PreFlightValidationResponse,
    ReparentPathMapping,
    ReparentSubtreeRequest,
    ReparentSubtreeResult,
    SessionSummary,
    StatusTransitionRequest,
    UnfinalizeChunksResult,
)
from rag_eval.legal.text import (
    extract_parent_context,
    natural_legal_path_key,
    validate_ltree_path,
)

logger = logging.getLogger(__name__)


class StagingDomainService:
    """Core domain facade for statutory staging operations and lifecycle mutations."""

    def __init__(
        self,
        staging_manager: StagingManager | None = None,
        validator: PreFlightValidator | None = None,
        pool: asyncpg.Pool | None = None,
    ) -> None:
        self._manager = staging_manager or StagingManager()
        self._validator = validator or PreFlightValidator()
        self._pool = pool

    @property
    def manager(self) -> StagingManager:
        return self._manager

    @property
    def validator(self) -> PreFlightValidator:
        return self._validator

    @property
    def pool(self) -> asyncpg.Pool | None:
        return self._pool

    def set_pool(self, pool: asyncpg.Pool | None) -> None:
        """Updates internal database pool."""
        self._pool = pool

    async def get_session(self, doc_code: str) -> StagingDocumentSession:
        """Loads session from local disk WAL store; if missing and pool provided, hydrates from PostgreSQL."""
        return await self._manager.load_or_hydrate_session(
            doc_code=doc_code, pool=self._pool
        )

    async def create_session(
        self, request: CreateSessionRequest
    ) -> StagingDocumentSession:
        """Creates a fresh staging session by parsing raw text via AST & CPHC engines."""
        meta = (
            request.metadata.model_dump()
            if isinstance(request.metadata, BaseModel)
            else (dict(request.metadata) if request.metadata else None)
        )
        return self._manager.create_session_from_raw(
            doc_code=request.doc_code,
            title=request.title,
            raw_text=request.raw_text,
            effective_date=request.effective_date,
            expiration_date=request.expiration_date,
            metadata=meta,
        )

    async def list_sessions(
        self, status: StagingStatus | None = None
    ) -> list[SessionSummary]:
        """Discovers and lists summaries of all WAL sessions in the staging directory."""
        summaries = self._manager.list_sessions()
        if status:
            summaries = [s for s in summaries if s.status == status]
        return summaries

    async def delete_session(self, doc_code: str) -> bool:
        """Deletes a staging session directory from disk."""
        return self._manager.delete_session(doc_code)

    async def get_chunk(self, doc_code: str, path: str) -> StatutoryChunk:
        """Looks up chunk and records inspection checkpoint for duty-of-inspection enforcement."""
        session = await self.get_session(doc_code)
        clean_path = validate_ltree_path(path)
        chunk = session.get_chunk(clean_path)
        if chunk is None:
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=f"Đoạn quy phạm '{clean_path}' không tồn tại trong phiên làm việc cho văn bản '{doc_code}'.",
                data={"doc_code": doc_code, "path": clean_path},
            )
        wal_store = self._manager.get_wal_store(doc_code)
        wal_store.save_checkpoint(session)
        return chunk

    async def get_raw_window(
        self, doc_code: str, start_line: int = 1, end_line: int | None = None
    ) -> RawTextResult:
        """Reads raw text window and records overlapping chunks in inspected_paths."""
        session = await self.get_session(doc_code)
        res = session.get_raw_window(start_line=start_line, end_line=end_line)
        wal_store = self._manager.get_wal_store(doc_code)
        wal_store.save_checkpoint(session)
        return res

    async def poll_pending_chunks(
        self,
        doc_code: str,
        limit: int = 10,
        path_prefix: str | None = None,
    ) -> tuple[list[PendingChunkGroup], ChunkProgressStats, bool, int]:
        """Queries pending chunks as a FIFO work queue, groups them under shared parent context,
        records inspection checkpoints, and clamps batch size strictly to at most 10 provisions."""
        session = await self.get_session(doc_code)
        doc_total = len(session.chunks)
        doc_finalized = sum(
            1 for c in session.chunks if c.review_status != ChunkReviewStatus.PENDING
        )

        target_pool = session.chunks
        if path_prefix and path_prefix.strip():
            clean_pre = validate_ltree_path(path_prefix)
            target_pool = [
                c for c in session.chunks
                if c.path == clean_pre or c.path.startswith(f"{clean_pre}.")
            ]

        pending_chunks = [
            c for c in target_pool if c.review_status == ChunkReviewStatus.PENDING
        ]
        pending_chunks.sort(key=lambda c: natural_legal_path_key(c.path))

        pending_total = len(pending_chunks)
        clamped_limit = min(max(1, limit), 10)
        windowed = pending_chunks[:clamped_limit]
        has_more = len(windowed) < pending_total

        if windowed:
            for c in windowed:
                session.inspected_paths.add(c.path)
            wal_store = self._manager.get_wal_store(doc_code)
            wal_store.save_checkpoint(session)

        groups_map: dict[str, tuple[str, list[PendingChunkLeaf]]] = {}
        for c in windowed:
            parent_path = c.path.rsplit(".", 1)[0] if "." in c.path else c.path
            if parent_path not in groups_map:
                fallback_title = c.metadata.article_title or c.metadata.chapter_title
                p_ctx = extract_parent_context(
                    contextualized_text=c.contextualized_text,
                    verbatim_text=c.verbatim_text,
                    parent_path=parent_path,
                    fallback_title=fallback_title,
                )
                groups_map[parent_path] = (p_ctx, [])

            leaf = PendingChunkLeaf(
                path=c.path,
                verbatim_text=c.verbatim_text,
                start_line=c.start_line,
                end_line=c.end_line,
                dangling_dependencies=c.dangling_dependencies,
            )
            groups_map[parent_path][1].append(leaf)

        groups = [
            PendingChunkGroup(
                parent_path=p_path,
                parent_context=p_ctx,
                chunks=leaves,
            )
            for p_path, (p_ctx, leaves) in groups_map.items()
        ]

        progress_percent = (
            round((doc_finalized / doc_total * 100.0), 1)
            if doc_total > 0
            else 0.0
        )
        stats = ChunkProgressStats(
            total_chunks=doc_total,
            finalized_count=doc_finalized,
            pending_count=pending_total,
            progress_percent=progress_percent,
        )
        return groups, stats, has_more, len(windowed)

    async def patch_chunks(
        self,
        doc_code: str,
        request: BatchPatchRequest,
        actor: str = "AGENT",
        cascade_breadcrumbs: bool = True,
    ) -> tuple[StagingDocumentSession, BatchPatchResult]:
        """Appends CHUNK_PATCHED record to WAL journal and updates materialized state."""
        wal_store = self._manager.get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        session = await self.get_session(doc_code)
        if session.status not in (StagingStatus.DRAFT, StagingStatus.AMENDMENT):
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể chỉnh sửa phiên staging ở trạng thái '{session.status.value}'. Phiên làm việc phải ở trạng thái DRAFT hoặc AMENDMENT.",
                data={"doc_code": doc_code, "status": session.status.value},
            )

        chunk_map = {c.path: c for c in session.chunks}
        for delta in request.updated_chunks:
            chunk = chunk_map.get(delta.path)
            target_text = delta.verbatim_text or (chunk.verbatim_text if chunk else "")
            if delta.dangling_dependencies is not None:
                for dep in delta.dangling_dependencies:
                    clean_dep_text = dep.dependency_text.strip()
                    pos = target_text.find(clean_dep_text) if target_text else -1
                    if pos == -1 and dep.dependency_type == "EXTERNAL_CITATION":
                        raise LegalDomainError(
                            error_code=E_AST_GROUNDING_VALIDATION,
                            message=f"Viện dẫn ngoại vi '{dep.dependency_text}' không tồn tại trong nội dung gốc của đoạn quy phạm '{delta.path}'.",
                            data={"path": delta.path, "dependency_text": dep.dependency_text},
                        )

        payload = {
            "deltas": [d.model_dump(mode="json") for d in request.updated_chunks],
            "removed_paths": list(request.removed_paths),
            "cascade_breadcrumbs": cascade_breadcrumbs,
        }
        _, session = wal_store.append_record(
            actor=actor,
            op_type="CHUNK_PATCHED",
            description=f"Patched {len(request.updated_chunks)} chunks and removed {len(request.removed_paths)} paths.",
            payload=payload,
        )

        diff_payload = (
            session.mutation_history[-1].diff_payload
            if session.mutation_history and session.mutation_history[-1].diff_payload
            else {}
        )
        raw_fields = diff_payload.get("fields_modified")
        fields_mod = (
            [str(f) for f in raw_fields] if isinstance(raw_fields, list) else []
        )
        raw_updated = diff_payload.get("updated_count")
        updated_cnt = (
            int(str(raw_updated))
            if raw_updated is not None
            else len(request.updated_chunks)
        )
        raw_removed = diff_payload.get("removed_count")
        removed_cnt = (
            int(str(raw_removed))
            if raw_removed is not None
            else len(request.removed_paths)
        )
        raw_cascaded = diff_payload.get("cascaded_count")
        cascaded_cnt = int(str(raw_cascaded)) if raw_cascaded is not None else 0

        result = BatchPatchResult(
            status="SUCCESS",
            doc_code=session.doc_code,
            updated_count=updated_cnt,
            removed_count=removed_cnt,
            cascaded_count=cascaded_cnt,
            total_chunks=len(session.chunks),
            fields_modified=fields_mod,
        )
        return session, result

    async def add_edges(
        self,
        doc_code: str,
        edges: Sequence[RelationEdge],
        actor: str = "AGENT",
    ) -> tuple[StagingDocumentSession, int]:
        """Appends EDGES_ATTACHED record to WAL journal and updates materialized state."""
        wal_store = self._manager.get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        session = await self.get_session(doc_code)
        if session.status not in (StagingStatus.DRAFT, StagingStatus.AMENDMENT):
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể chỉnh sửa phiên staging ở trạng thái '{session.status.value}'. Phiên làm việc phải ở trạng thái DRAFT hoặc AMENDMENT.",
                data={"doc_code": doc_code, "status": session.status.value},
            )

        chunk_paths = {c.path for c in session.chunks}
        for edge in edges:
            if edge.target_path and edge.source_path == edge.target_path:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=(
                        f"Self-referencing edge loop detected on path '{edge.source_path}'. "
                        "Source and target paths must not be identical."
                    ),
                    data={
                        "doc_code": doc_code,
                        "source_path": edge.source_path,
                        "target_path": edge.target_path,
                    },
                )
            if edge.source_path not in chunk_paths:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=(
                        f"Invalid edge source path '{edge.source_path}': "
                        f"chunk path does not exist in document '{doc_code}'."
                    ),
                    data={"doc_code": doc_code, "source_path": edge.source_path},
                )

        payload = {
            "edges": [e.model_dump(mode="json") for e in edges],
        }
        _, session = wal_store.append_record(
            actor=actor,
            op_type="EDGES_ATTACHED",
            description=f"Attached {len(edges)} relation edges.",
            payload=payload,
        )
        return session, len(edges)

    async def remove_edges(
        self,
        doc_code: str,
        filters: Sequence[RelationEdgeFilter],
        actor: str = "AGENT",
    ) -> tuple[StagingDocumentSession, int]:
        """Appends EDGES_REMOVED record to WAL journal and updates materialized state."""
        wal_store = self._manager.get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        session = await self.get_session(doc_code)
        if session.status not in (StagingStatus.DRAFT, StagingStatus.AMENDMENT):
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể chỉnh sửa phiên staging ở trạng thái '{session.status.value}'. Phiên làm việc phải ở trạng thái DRAFT hoặc AMENDMENT.",
                data={"doc_code": doc_code, "status": session.status.value},
            )

        if not filters:
            return session, 0

        initial_count = len(session.edges)
        payload = {
            "filters": [f.model_dump(mode="json") for f in filters],
        }
        _, session = wal_store.append_record(
            actor=actor,
            op_type="EDGES_REMOVED",
            description=f"Removed edges matching {len(filters)} filter(s).",
            payload=payload,
        )
        removed_count = initial_count - len(session.edges)
        return session, removed_count

    async def reparent_subtree(
        self,
        doc_code: str,
        request: ReparentSubtreeRequest,
    ) -> tuple[StagingDocumentSession, ReparentSubtreeResult]:
        """Validates reparenting; if request.dry_run is True, simulates via pure state reducer without WAL.
        Otherwise appends SUBTREE_REPARENTED record to WAL journal.
        """
        session = await self.get_session(doc_code)

        if request.dry_run:
            result = StagingStateReducer.preview_reparent(
                session=session,
                old_prefix=request.old_path_prefix,
                new_prefix=request.new_path_prefix,
            )
            return session, result

        if session.status not in (StagingStatus.DRAFT, StagingStatus.AMENDMENT):
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể chỉnh sửa phiên staging ở trạng thái '{session.status.value}'. Phiên làm việc phải ở trạng thái DRAFT hoặc AMENDMENT.",
                data={"doc_code": doc_code, "status": session.status.value},
            )

        wal_store = self._manager.get_wal_store(doc_code)
        payload = {
            "old_path_prefix": request.old_path_prefix,
            "new_path_prefix": request.new_path_prefix,
        }
        _, session = wal_store.append_record(
            actor=request.actor,
            op_type="SUBTREE_REPARENTED",
            description=f"Migrated subtree '{request.old_path_prefix}' to '{request.new_path_prefix}'.",
            payload=payload,
        )

        diff = (
            session.mutation_history[-1].diff_payload
            if session.mutation_history and session.mutation_history[-1].diff_payload
            else {}
        )
        raw_mappings = diff.get("path_mappings") or diff.get("mappings")
        mappings: list[ReparentPathMapping] = []
        if isinstance(raw_mappings, list):
            mappings = [ReparentPathMapping.model_validate(m) for m in raw_mappings]

        result = ReparentSubtreeResult(
            status="SUCCESS",
            doc_code=session.doc_code,
            dry_run=False,
            affected_chunks_count=int(str(diff.get("affected_chunks_count", diff.get("affected_chunks", 0)))),
            affected_edges_count=int(str(diff.get("affected_edges_count", diff.get("affected_edges", 0)))),
            old_path_prefix=request.old_path_prefix,
            new_path_prefix=request.new_path_prefix,
            total_chunks=len(session.chunks),
            sample_mappings=mappings,
        )
        return session, result

    async def finalize_chunks(
        self,
        doc_code: str,
        request: FinalizeChunksRequest,
        actor: str = "AGENT",
    ) -> tuple[StagingDocumentSession, FinalizeChunksResult]:
        """Atomically locks candidate chunks as FINALIZED via WAL append."""
        wal_store = self._manager.get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        session = await self.get_session(doc_code)
        if session.status not in (StagingStatus.DRAFT, StagingStatus.AMENDMENT):
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Không thể chỉnh sửa phiên staging ở trạng thái '{session.status.value}'. Phiên làm việc phải ở trạng thái DRAFT hoặc AMENDMENT.",
                data={"doc_code": doc_code, "status": session.status.value},
            )

        clean_paths = [validate_ltree_path(p) for p in request.paths]
        if actor == "AGENT":
            uninspected = [p for p in clean_paths if p not in session.inspected_paths]
            if uninspected:
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=f"Chunk '{uninspected[0]}' chưa từng được đọc qua stg_poll_pending, stg_get_chunk hoặc stg_get_raw trong phiên làm việc.",
                    data={
                        "violation_code": "UNINSPECTED_CHUNK",
                        "path": uninspected[0],
                        "remediation_hint": "Nghĩa vụ thẩm định: Hãy gọi stg_poll_pending, stg_get_chunk hoặc stg_get_raw để kiểm tra toàn văn nội dung trước khi chốt nghiệm thu.",
                    },
                )

        payload = {"paths": clean_paths}
        _, session = wal_store.append_record(
            actor=actor,
            op_type="CHUNKS_FINALIZED",
            description=f"Finalized {len(clean_paths)} chunks.",
            payload=payload,
        )

        finalize_statuses: list[ChunkFinalizeStatus] = [
            ChunkFinalizeStatus(
                path=c.path,
                review_status=c.review_status,
                finalization_state=c.finalization_state,
            )
            for c in session.chunks
            if c.path in clean_paths and c.review_status == ChunkReviewStatus.REVIEWED
        ]
        pending_remaining = sum(
            1 for c in session.chunks if c.review_status != ChunkReviewStatus.REVIEWED
        )
        result = FinalizeChunksResult(
            status="SUCCESS",
            doc_code=session.doc_code,
            finalized_count=len(finalize_statuses),
            pending_remaining=pending_remaining,
            paths=clean_paths,
            results=finalize_statuses,
        )
        return session, result

    async def unfinalize_chunks(
        self,
        doc_code: str,
        paths: list[str],
        actor: str = "AGENT",
    ) -> tuple[StagingDocumentSession, UnfinalizeChunksResult]:
        """Atomically reverts reviewed chunks back to PENDING status via WAL append."""
        wal_store = self._manager.get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        session = await self.get_session(doc_code)
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
            op_type="CHUNKS_UNFINALIZED",
            description=f"Unfinalized {len(clean_paths)} chunks back to PENDING.",
            payload=payload,
        )

        unfinalized_count = sum(
            1 for c in session.chunks
            if c.path in clean_paths and c.review_status == ChunkReviewStatus.PENDING
        )
        pending_count = sum(
            1 for c in session.chunks if c.review_status == ChunkReviewStatus.PENDING
        )
        result = UnfinalizeChunksResult(
            status="SUCCESS",
            doc_code=session.doc_code,
            unfinalized_count=unfinalized_count,
            pending_count=pending_count,
            paths=clean_paths,
        )
        return session, result

    async def commit_session(
        self, doc_code: str, actor: str = "AGENT"
    ) -> StagingDocumentSession:
        """Enforces 100% PreFlightValidator pass (including zero pending chunks),
        then appends STATUS_TRANSITION_AGENT_COMMITTED record to WAL journal.
        """
        session = await self.get_session(doc_code)

        validation_result = self._validator.validate(session)
        if not validation_result.passed:
            blocking = [
                f"[{issue.rule}] {issue.path or 'DOCUMENT'}: {issue.message}"
                for issue in validation_result.issues
                if issue.blocking
            ]
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=(
                    f"Không thể commit văn bản '{doc_code}': vi phạm {len(blocking)} quy tắc kiểm định an toàn.\n"
                    + "\n".join(blocking[:5])
                ),
                data={
                    "doc_code": doc_code,
                    "blocking_count": len(blocking),
                    "blocking_issues": blocking,
                },
            )

        unreviewed = [
            c.path
            for c in session.chunks
            if c.review_status == ChunkReviewStatus.PENDING
        ]
        if unreviewed:
            raise LegalDomainError(
                error_code=E_AST_GROUNDING_VALIDATION,
                message=(
                    f"Không thể commit văn bản '{doc_code}': còn {len(unreviewed)}/{len(session.chunks)} "
                    "đoạn quy phạm ở trạng thái PENDING. Thẩm định viên/Agent bắt buộc phải rà soát "
                    "100% các đoạn quy phạm trước khi phiên làm việc được phép cam kết."
                ),
                data={
                    "doc_code": doc_code,
                    "unreviewed_count": len(unreviewed),
                    "total_chunks": len(session.chunks),
                    "unreviewed_sample": unreviewed[:5],
                },
            )

        wal_store = self._manager.get_wal_store(doc_code)
        payload = {
            "new_status": StagingStatus.AGENT_COMMITTED.value,
            "description": f"Agent completed staging session review and committed for {doc_code}.",
        }
        _, session = wal_store.append_record(
            actor=actor,
            op_type="STATUS_TRANSITION_AGENT_COMMITTED",
            description=f"Agent completed staging session review and committed for {doc_code}.",
            payload=payload,
        )
        return session

    async def update_status(
        self,
        doc_code: str,
        request: StatusTransitionRequest,
    ) -> StagingDocumentSession:
        """Appends status transition record to WAL journal and updates materialized state."""
        wal_store = self._manager.get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        session = await self.get_session(doc_code)
        if request.status in (StagingStatus.AGENT_COMMITTED, StagingStatus.PROMOTED):
            validation_result = self._validator.validate(session)
            if not validation_result.passed:
                blocking = [
                    f"[{issue.rule}] {issue.path or 'DOCUMENT'}: {issue.message}"
                    for issue in validation_result.issues
                    if issue.blocking
                ]
                raise LegalDomainError(
                    error_code=E_AST_GROUNDING_VALIDATION,
                    message=(
                        f"Không thể chuyển trạng thái '{doc_code}' sang {request.status.value}: "
                        f"vi phạm {len(blocking)} quy tắc kiểm định an toàn.\n"
                        + "\n".join(blocking[:5])
                    ),
                    data={
                        "doc_code": doc_code,
                        "blocking_count": len(blocking),
                        "blocking_issues": blocking,
                    },
                )

        payload = {
            "new_status": request.status.value,
            "description": request.description,
        }
        _, session = wal_store.append_record(
            actor=request.actor,
            op_type=f"STATUS_TRANSITION_{request.status.value}",
            description=request.description or f"Transitioned status to {request.status.value}",
            payload=payload,
        )
        return session

    async def reopen_session(
        self,
        doc_code: str,
        actor: str = "AGENT",
        reason: str = "",
    ) -> StagingDocumentSession:
        """Reopens a PROMOTED statutory session into AMENDMENT status."""
        wal_store = self._manager.get_wal_store(doc_code)
        if not wal_store.exists():
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Staging session for document '{doc_code}' does not exist at {wal_store.session_dir}",
                data={"doc_code": doc_code},
            )

        session = await self.get_session(doc_code)
        if session.status == StagingStatus.AMENDMENT:
            return session
        if session.status != StagingStatus.PROMOTED:
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=(
                    f"Chỉ phiên ở trạng thái PROMOTED mới có thể mở lại để sửa đổi bổ sung (AMENDMENT). "
                    f"Hiện tại: '{session.status.value}'."
                ),
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

    async def replay_session(
        self,
        doc_code: str,
        up_to_lsn: int | None = None,
    ) -> tuple[StagingDocumentSession, int]:
        """Deterministically replays session from genesis to up_to_lsn and returns (session, lsn)."""
        return self._manager.replay_session(doc_code, up_to_lsn=up_to_lsn)

    async def get_wal_records(
        self, doc_code: str, since_lsn: int = 0
    ) -> list[WALRecord]:
        """Returns full ordered WAL history for the document."""
        return self._manager.get_wal_records(doc_code, since_lsn=since_lsn)

    async def validate_session(self, doc_code: str) -> PreFlightValidationResponse:
        """Executes full automated pre-flight integrity check on the staging session."""
        session = await self.get_session(doc_code)
        return self._validator.validate(session)

