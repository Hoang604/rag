from __future__ import annotations

from typing import TYPE_CHECKING

from rag_eval.legal.errors import (
    E_INVALID_DOCUMENT_HIERARCHY,
    LegalDomainError,
)
from rag_eval.legal.schemas.domain import (
    ChunkDelta,
    ChunkMetadata,
    ChunkReviewStatus,
    FinalizationState,
    RelationEdge,
    StagingStatus,
    StatutoryChunk,
    UnresolvedReference,
)
from rag_eval.legal.schemas.staging import (
    MutationRecord,
    ReparentPathMapping,
    ReparentSubtreeResult,
)
from rag_eval.legal.text import (
    deep_merge_dict,
    natural_legal_path_key,
    validate_ltree_path,
)

if TYPE_CHECKING:
    from rag_eval.legal.ingestion.staging.session import StagingDocumentSession
    from rag_eval.legal.ingestion.wal import WALRecord


class StagingStateReducer:
    """Pure deterministic state fold reducer: S x E -> S'."""

    @classmethod
    def reduce(cls, session: StagingDocumentSession, record: WALRecord) -> None:
        """Folds a single immutable WALRecord onto session state in-place."""
        session.updated_at = record.timestamp

        if record.op_type == "GENESIS":
            mutation = MutationRecord(
                actor=record.actor,
                action_type="GENESIS",
                description=record.description,
                timestamp=record.timestamp,
                diff_payload={"lsn": record.lsn, **record.payload},
            )
            session.mutation_history = [mutation]
            return

        if record.op_type == "CHUNK_PATCHED":
            cls._reduce_chunk_patched(session, record)
            return

        if record.op_type == "EDGES_ATTACHED":
            cls._reduce_edges_attached(session, record)
            return

        if record.op_type == "GRAPH_EDGE_PROPOSED":
            cls._reduce_edge_proposed(session, record)
            return

        if record.op_type in ("EDGE_REMOVED", "EDGES_REMOVED"):
            cls._reduce_edges_removed(session, record)
            return

        if record.op_type == "SUBTREE_REPARENTED":
            cls._reduce_subtree_reparented(session, record)
            return

        if record.op_type == "CHUNKS_FINALIZED":
            cls._reduce_chunks_finalized(session, record)
            return

        if record.op_type in ("CHUNKS_UNFINALIZED", "STATUS_TRANSITION_UNFINALIZED"):
            cls._reduce_chunks_unfinalized(session, record)
            return

        if record.op_type.startswith("STATUS_TRANSITION_") or record.op_type == "STATUS_TRANSITION":
            cls._reduce_status_transition(session, record)
            return

        if record.op_type == "SESSION_REOPENED":
            cls._reduce_session_reopened(session, record)
            return

        if record.op_type == "HYDRATION_FROM_DB":
            cls._reduce_hydration_from_db(session, record)
            return

        if record.op_type == "PROMOTED_TO_PRODUCTION":
            session.status = StagingStatus.PROMOTED
            session.promoted_at = record.timestamp
            session.mutation_history.append(
                MutationRecord(
                    actor=record.actor,
                    action_type="PROMOTED_TO_PRODUCTION",
                    description=record.description,
                    timestamp=record.timestamp,
                    diff_payload=record.payload,
                )
            )
            return

        # Default fallback for arbitrary record types
        session.mutation_history.append(
            MutationRecord(
                actor=record.actor,
                action_type=record.op_type,
                description=record.description,
                timestamp=record.timestamp,
                diff_payload=record.payload,
            )
        )

    @classmethod
    def _reduce_chunk_patched(cls, session: StagingDocumentSession, record: WALRecord) -> None:
        raw_deltas = record.payload.get("deltas")
        removed_paths_raw = record.payload.get("removed_paths")
        cascade_breadcrumbs = bool(record.payload.get("cascade_breadcrumbs", True))

        deltas: list[ChunkDelta] = []
        if isinstance(raw_deltas, list):
            deltas = [
                ChunkDelta.model_validate(d) if isinstance(d, dict) else d
                for d in raw_deltas
            ]

        removed_paths: list[str] = []
        if isinstance(removed_paths_raw, list):
            removed_paths = [str(p) for p in removed_paths_raw]

        # 1. Process removals
        if removed_paths:
            removed_set = set(removed_paths)
            session.chunks = [c for c in session.chunks if c.path not in removed_set]
            session.edges = [
                e
                for e in session.edges
                if e.source_path not in removed_set and e.target_path not in removed_set
            ]

        # 2. Process deltas
        chunk_map = {c.path: c for c in session.chunks}
        updated_count = 0

        for delta in deltas:
            target_path = delta.path.strip()
            if target_path in chunk_map:
                existing = chunk_map[target_path]
                if delta.verbatim_text is not None:
                    existing.verbatim_text = delta.verbatim_text
                if delta.contextualized_text is not None:
                    existing.contextualized_text = delta.contextualized_text
                if delta.start_line is not None:
                    existing.start_line = delta.start_line
                if delta.end_line is not None:
                    existing.end_line = delta.end_line
                if delta.effective_date is not None:
                    existing.effective_date = delta.effective_date
                if delta.expiration_date is not None:
                    existing.expiration_date = delta.expiration_date
                if delta.dangling_dependencies is not None:
                    resolved_deps: list[UnresolvedReference] = []
                    for dep in delta.dangling_dependencies:
                        clean_text = dep.dependency_text.strip()
                        pos = existing.verbatim_text.find(clean_text) if existing.verbatim_text else -1
                        char_start = pos if pos != -1 else None
                        char_end = (pos + len(clean_text)) if pos != -1 else None
                        resolved_deps.append(
                            UnresolvedReference(
                                source_path=existing.path,
                                dependency_text=dep.dependency_text,
                                dependency_type=dep.dependency_type,
                                reason=dep.reason,
                                char_start=char_start,
                                char_end=char_end,
                            )
                        )
                    existing.dangling_dependencies = resolved_deps

                if delta.metadata is not None:
                    delta_meta: dict[str, object] = delta.metadata.model_dump(exclude_unset=True)
                    base_meta: dict[str, object] = existing.metadata.model_dump(exclude_unset=True)
                    merged_meta = deep_merge_dict(base_meta, delta_meta)
                    existing.metadata = ChunkMetadata.model_validate(merged_meta)

                updated_count += 1
            else:
                new_deps: list[UnresolvedReference] = []
                if delta.dangling_dependencies:
                    for dep in delta.dangling_dependencies:
                        clean_text = dep.dependency_text.strip()
                        pos = (delta.verbatim_text or "").find(clean_text)
                        char_start = pos if pos != -1 else None
                        char_end = (pos + len(clean_text)) if pos != -1 else None
                        new_deps.append(
                            UnresolvedReference(
                                source_path=target_path,
                                dependency_text=dep.dependency_text,
                                dependency_type=dep.dependency_type,
                                reason=dep.reason,
                                char_start=char_start,
                                char_end=char_end,
                            )
                        )

                new_chunk = StatutoryChunk(
                    path=target_path,
                    verbatim_text=delta.verbatim_text or "",
                    contextualized_text=delta.contextualized_text or delta.verbatim_text or "",
                    start_line=delta.start_line or 1,
                    end_line=delta.end_line or 1,
                    effective_date=delta.effective_date or session.effective_date,
                    expiration_date=delta.expiration_date or session.expiration_date,
                    review_status=ChunkReviewStatus.PENDING,
                    finalization_state=FinalizationState.UNFINALIZED_OPEN_ENDED,
                    dangling_dependencies=new_deps,
                    metadata=delta.metadata or ChunkMetadata(),
                )
                session.chunks.append(new_chunk)
                chunk_map[target_path] = new_chunk
                updated_count += 1

        # Always sort chunks naturally
        session.chunks.sort(key=lambda c: natural_legal_path_key(c.path))

        session.mutation_history.append(
            MutationRecord(
                actor=record.actor,
                action_type="CHUNK_PATCHED",
                description=record.description,
                timestamp=record.timestamp,
                diff_payload={
                    "updated_count": updated_count,
                    "removed_count": len(removed_paths),
                    "cascade_breadcrumbs": cascade_breadcrumbs,
                    **record.payload,
                },
            )
        )

    @classmethod
    def _reduce_edges_attached(cls, session: StagingDocumentSession, record: WALRecord) -> None:
        raw_edges = record.payload.get("edges")
        new_edges: list[RelationEdge] = []
        if isinstance(raw_edges, list):
            for e in raw_edges:
                new_edges.append(RelationEdge.model_validate(e) if isinstance(e, dict) else e)

        existing_edge_keys = {
            (e.source_path, e.target_path, e.relation_type.value)
            for e in session.edges
        }

        attached: list[RelationEdge] = []
        for edge in new_edges:
            key = (edge.source_path, edge.target_path, edge.relation_type.value)
            if key not in existing_edge_keys:
                existing_edge_keys.add(key)
                session.edges.append(edge)
                attached.append(edge)

        session.mutation_history.append(
            MutationRecord(
                actor=record.actor,
                action_type="EDGES_ATTACHED",
                description=record.description,
                timestamp=record.timestamp,
                diff_payload={
                    "attached_count": len(attached),
                    "edges": [e.model_dump() for e in attached],
                },
            )
        )

    @classmethod
    def _reduce_edge_proposed(cls, session: StagingDocumentSession, record: WALRecord) -> None:
        raw_edges = record.payload.get("edges")
        if isinstance(raw_edges, list):
            for e_dict in raw_edges:
                if isinstance(e_dict, dict):
                    clean_src = str(e_dict.get("source_path", ""))
                    clean_tgt = str(e_dict.get("target_path", ""))
                    if not clean_tgt:
                        continue
                    new_edge = RelationEdge(
                        source_path=clean_src,
                        target_path=clean_tgt,
                        relation_type=str(e_dict.get("relation_type")),
                        citation_text=e_dict.get("citation_text"),
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
            MutationRecord(
                actor=record.actor,
                action_type="GRAPH_EDGE_PROPOSED",
                description=record.description,
                timestamp=record.timestamp,
                diff_payload=record.payload,
            )
        )

    @classmethod
    def _reduce_edges_removed(cls, session: StagingDocumentSession, record: WALRecord) -> None:
        raw_filters = record.payload.get("filters")
        filters: list[dict[str, object]] = []
        if isinstance(raw_filters, list):
            filters = [f for f in raw_filters if isinstance(f, dict)]
        else:
            filters = [dict(record.payload)]

        def _matches_any_filter(e: RelationEdge) -> bool:
            for flt in filters:
                src = flt.get("source_path")
                if e.source_path != src:
                    continue
                clear_all = bool(flt.get("clear_all_targets", False))
                rel = flt.get("relation_type")
                if rel is not None and e.relation_type.value != rel:
                    continue
                tgt = flt.get("target_path")
                if not clear_all and not tgt:
                    continue
                if tgt is not None and e.target_path != tgt:
                    continue
                return True
            return False

        original_count = len(session.edges)
        session.edges = [e for e in session.edges if not _matches_any_filter(e)]
        removed_count = original_count - len(session.edges)

        session.mutation_history.append(
            MutationRecord(
                actor=record.actor,
                action_type=record.op_type,
                description=record.description,
                timestamp=record.timestamp,
                diff_payload=dict(record.payload) | {"removed_count": removed_count},
            )
        )

    @classmethod
    def preview_reparent(
        cls, session: StagingDocumentSession, old_prefix: str, new_prefix: str
    ) -> ReparentSubtreeResult:
        """Pure in-memory simulation of subtree reparenting without mutating session and without WAL."""
        clean_old = validate_ltree_path(old_prefix)
        clean_new = validate_ltree_path(new_prefix)

        matching_chunks = [
            c for c in session.chunks if c.path == clean_old or c.path.startswith(f"{clean_old}.")
        ]
        if not matching_chunks:
            raise LegalDomainError(
                error_code=E_INVALID_DOCUMENT_HIERARCHY,
                message=f"Không tìm thấy node hoặc cây con nào với tiền tố '{clean_old}'.",
                data={"old_prefix": clean_old, "new_prefix": clean_new},
            )

        mappings: list[ReparentPathMapping] = []
        for c in matching_chunks:
            rel = c.path[len(clean_old) :]
            new_path = f"{clean_new}{rel}"
            mappings.append(
                ReparentPathMapping(
                    old_path=c.path,
                    new_path=new_path,
                )
            )

        return ReparentSubtreeResult(
            status="SUCCESS",
            doc_code=session.doc_code,
            dry_run=True,
            affected_chunks_count=len(mappings),
            affected_edges_count=0,
            old_path_prefix=clean_old,
            new_path_prefix=clean_new,
            total_chunks=len(session.chunks),
            sample_mappings=mappings,
        )

    @classmethod
    def _reduce_subtree_reparented(cls, session: StagingDocumentSession, record: WALRecord) -> None:
        old_p = str(record.payload.get("old_path_prefix", ""))
        new_p = str(record.payload.get("new_path_prefix", ""))
        clean_old = validate_ltree_path(old_p)
        clean_new = validate_ltree_path(new_p)

        path_map: dict[str, str] = {}
        for c in session.chunks:
            if c.path == clean_old or c.path.startswith(f"{clean_old}."):
                rel = c.path[len(clean_old) :]
                new_path = f"{clean_new}{rel}"
                path_map[c.path] = new_path
                c.path = new_path

        # Update edge references
        for edge in session.edges:
            if edge.source_path in path_map:
                edge.source_path = path_map[edge.source_path]
            if edge.target_path in path_map:
                edge.target_path = path_map[edge.target_path]

        session.chunks.sort(key=lambda c: natural_legal_path_key(c.path))

        mappings = [
            ReparentPathMapping(old_path=old_k, new_path=new_v)
            for old_k, new_v in path_map.items()
        ]

        session.mutation_history.append(
            MutationRecord(
                actor=record.actor,
                action_type="SUBTREE_REPARENTED",
                description=record.description,
                timestamp=record.timestamp,
                diff_payload={
                    "old_path_prefix": clean_old,
                    "new_path_prefix": clean_new,
                    "affected_chunks_count": len(mappings),
                    "path_mappings": [m.model_dump() for m in mappings],
                },
            )
        )

    @classmethod
    def _reduce_chunks_finalized(cls, session: StagingDocumentSession, record: WALRecord) -> None:
        raw_paths = record.payload.get("paths")
        paths_list = [str(p) for p in raw_paths] if isinstance(raw_paths, (list, tuple)) else []
        target_set = set(paths_list)

        finalized_entries: list[dict[str, object]] = []
        for chunk in session.chunks:
            if chunk.path in target_set:
                chunk.review_status = ChunkReviewStatus.REVIEWED
                if chunk.dangling_dependencies:
                    has_external = any(
                        dep.dependency_type == "EXTERNAL_CITATION"
                        for dep in chunk.dangling_dependencies
                    )
                    chunk.finalization_state = (
                        FinalizationState.UNFINALIZED_PENDING_EXTERNAL
                        if has_external
                        else FinalizationState.UNFINALIZED_OPEN_ENDED
                    )
                else:
                    has_outgoing_edges = any(e.source_path == chunk.path for e in session.edges)
                    chunk.finalization_state = (
                        FinalizationState.FINALIZED_FULLY_LINKED
                        if has_outgoing_edges
                        else FinalizationState.FINALIZED_SELF_CONTAINED
                    )
                finalized_entries.append({
                    "path": chunk.path,
                    "status": "FINALIZED",
                    "finalization_state": chunk.finalization_state.value,
                })

        session.mutation_history.append(
            MutationRecord(
                actor=record.actor,
                action_type="CHUNKS_FINALIZED",
                description=record.description,
                timestamp=record.timestamp,
                diff_payload={
                    "finalized_count": len(finalized_entries),
                    "finalized_chunks": finalized_entries,
                },
            )
        )

    @classmethod
    def _reduce_chunks_unfinalized(cls, session: StagingDocumentSession, record: WALRecord) -> None:
        raw_paths = record.payload.get("paths")
        paths_list = [str(p) for p in raw_paths] if isinstance(raw_paths, (list, tuple)) else []
        target_set = set(paths_list)

        unfinalized_entries: list[dict[str, object]] = []
        for chunk in session.chunks:
            if chunk.path in target_set:
                chunk.review_status = ChunkReviewStatus.PENDING
                chunk.finalization_state = FinalizationState.UNFINALIZED_OPEN_ENDED
                unfinalized_entries.append({
                    "path": chunk.path,
                    "status": "PENDING",
                    "finalization_state": chunk.finalization_state.value,
                })

        session.mutation_history.append(
            MutationRecord(
                actor=record.actor,
                action_type="CHUNKS_UNFINALIZED",
                description=record.description,
                timestamp=record.timestamp,
                diff_payload={
                    "unfinalized_count": len(unfinalized_entries),
                    "unfinalized_chunks": unfinalized_entries,
                },
            )
        )

    @classmethod
    def _reduce_status_transition(cls, session: StagingDocumentSession, record: WALRecord) -> None:
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
            MutationRecord(
                actor=record.actor,
                action_type=record.op_type,
                description=record.description,
                timestamp=record.timestamp,
                diff_payload=record.payload,
            )
        )

    @classmethod
    def _reduce_session_reopened(cls, session: StagingDocumentSession, record: WALRecord) -> None:
        session.status = StagingStatus.DRAFT
        session.committed_at = None
        session.promoted_at = None
        if "amendment_baseline_snapshot" in record.payload:
            session.doc_metadata["amendment_baseline_snapshot"] = record.payload[
                "amendment_baseline_snapshot"
            ]
        session.mutation_history.append(
            MutationRecord(
                actor=record.actor,
                action_type="SESSION_REOPENED",
                description=record.description,
                timestamp=record.timestamp,
                diff_payload=record.payload,
            )
        )

    @classmethod
    def _reduce_hydration_from_db(cls, session: StagingDocumentSession, record: WALRecord) -> None:
        session.doc_metadata["hydrated_from_db"] = True
        session.mutation_history.append(
            MutationRecord(
                actor=record.actor,
                action_type="HYDRATION_FROM_DB",
                description=record.description,
                timestamp=record.timestamp,
                diff_payload=record.payload,
            )
        )
