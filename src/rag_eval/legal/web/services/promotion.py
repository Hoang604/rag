from __future__ import annotations

import logging
import uuid

import asyncpg

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.ingestion.staging.models import StagingStatus
from rag_eval.legal.schemas import (
    E_CORPUS_INTEGRITY_VIOLATION,
    CanonicalFullyQualifiedChunk,
    DocumentRecord,
    GraphEdgeRecord,
    LegalDomainError,
    get_vietnam_now,
)
from rag_eval.legal.web.schemas import PromotionResultResponse
from rag_eval.legal.web.services.validation import PreFlightValidator

logger = logging.getLogger(__name__)


class HumanPromotionEngine:
    """Executes atomic promotion of approved staging sessions into PostgreSQL production tables."""

    def __init__(
        self,
        staging_manager: StagingManager | None = None,
        validator: PreFlightValidator | None = None,
    ) -> None:
        self.staging_manager = staging_manager or StagingManager()
        self.validator = validator or PreFlightValidator()

    async def promote_session(
        self,
        doc_code: str,
        reviewer_notes: str | None = None,
        compute_embeddings: bool = True,
        pool: asyncpg.Pool | None = None,
    ) -> PromotionResultResponse:
        """Validates and atomically promotes a staging session into PostgreSQL."""
        session, _ = self.staging_manager.replay_session(doc_code)

        validation = self.validator.validate(session)
        if not validation.passed:
            violation_msgs = [f"[{i.rule}] {i.message}" for i in validation.issues if i.blocking]
            error_details = "; ".join(violation_msgs)
            raise LegalDomainError(
                error_code=E_CORPUS_INTEGRITY_VIOLATION,
                message=f"Pre-flight validation failed with {len(violation_msgs)} blocking issue(s): {error_details}",
                data={"issues": [i.model_dump() for i in validation.issues]},
            )

        target_pool = pool if pool is not None else await get_db_pool()
        loader = PostgresBulkLoader(pool=target_pool, compute_embeddings=compute_embeddings)

        doc_record = DocumentRecord(
            doc_code=session.doc_code,
            title=session.title,
            effective_date=session.effective_date,
            expiration_date=session.expiration_date,
            metadata=session.doc_metadata,
            raw_text=session.raw_text,
        )

        async with target_pool.acquire() as conn, conn.transaction():
            doc_id = await loader.load_document(doc_record, conn=conn)

            canonical_chunks = [
                CanonicalFullyQualifiedChunk(
                    document_id=doc_id,
                    path=c.path,
                    verbatim_text=c.verbatim_text,
                    contextualized_text=c.contextualized_text,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    metadata=c.metadata,
                    effective_date=c.effective_date,
                    expiration_date=c.expiration_date,
                    finalization_state=c.finalization_state,
                    dangling_dependencies=c.dangling_dependencies,
                )
                for c in session.chunks
            ]
            path_to_uuid = await loader.load_chunks(canonical_chunks, conn=conn)

            unresolved_target_paths: list[str] = [
                e.target_path
                for e in session.edges
                if e.target_path and e.target_path not in path_to_uuid
            ]

            external_path_to_uuid: dict[str, uuid.UUID] = {}
            if unresolved_target_paths:
                external_path_to_uuid = await loader.resolve_chunk_paths(unresolved_target_paths)

            graph_edge_records: list[GraphEdgeRecord] = []
            for edge in session.edges:
                src_uuid = path_to_uuid.get(edge.source_path)
                if src_uuid is None:
                    raise LegalDomainError(
                        error_code=E_CORPUS_INTEGRITY_VIOLATION,
                        message=f"Source chunk '{edge.source_path}' was not assigned a valid UUID during promotion.",
                        data={"source_path": edge.source_path},
                    )

                tgt_uuid = None
                target_ext = edge.target_external_ref

                if edge.target_path:
                    if edge.target_path in path_to_uuid:
                        tgt_uuid = path_to_uuid[edge.target_path]
                    elif edge.target_path in external_path_to_uuid:
                        tgt_uuid = external_path_to_uuid[edge.target_path]
                    elif not target_ext:
                        target_ext = edge.target_path

                graph_edge_records.append(
                    GraphEdgeRecord(
                        source_chunk_id=src_uuid,
                        target_chunk_id=tgt_uuid,
                        target_external_ref=target_ext,
                        relation_type=edge.relation_type,
                        citation_text=edge.citation_text,
                        metadata=edge.metadata,
                    )
                )

            inserted_edges_count = 0
            if graph_edge_records:
                inserted_edges_count = await loader.load_graph_edges(graph_edge_records, conn=conn)

        now = get_vietnam_now()
        self.staging_manager.update_session_status(
            doc_code=session.doc_code,
            status=StagingStatus.PROMOTED,
            actor="HUMAN:reviewer",
            description=f"Promoted to production PostgreSQL (doc_id: {doc_id}). Notes: {reviewer_notes or 'None'}",
        )

        return PromotionResultResponse(
            status="PROMOTED",
            doc_code=session.doc_code,
            document_id=str(doc_id),
            chunks_promoted=len(canonical_chunks),
            edges_promoted=inserted_edges_count,
            promoted_at=now.isoformat(),
            message=(
                f"Văn bản '{session.doc_code}' đã được phê duyệt và commit nguyên tử vào cơ sở dữ liệu "
                f"chính thức ({len(canonical_chunks)} đoạn quy phạm, {inserted_edges_count} cạnh quan hệ đồ thị)."
            ),
        )
