from __future__ import annotations

import logging
import uuid

import asyncpg

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.db.entities import (
    ChunkContextRefEntity,
    ChunkEntity,
    DocumentEntity,
    GraphEdgeEntity,
)
from rag_eval.legal.errors import (
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
)
from rag_eval.legal.ingestion.staging.manager import StagingManager
from rag_eval.legal.ingestion.staging.service import StagingDomainService
from rag_eval.legal.ingestion.staging.validation import PreFlightValidator
from rag_eval.legal.schemas.domain import (
    FinalizationState,
    StagingStatus,
    StatutoryRelationType,
)
from rag_eval.legal.schemas.staging import (
    PromotionResultResponse,
    StatusTransitionRequest,
)
from rag_eval.legal.text import (
    get_vietnam_now,
)

logger = logging.getLogger(__name__)


class HumanPromotionEngine:
    """Executes atomic promotion of approved staging sessions into PostgreSQL production tables."""

    def __init__(
        self,
        staging_manager: StagingManager | None = None,
        validator: PreFlightValidator | None = None,
        staging_service: StagingDomainService | None = None,
    ) -> None:
        self.staging_manager = staging_manager or StagingManager()
        self.validator = validator or PreFlightValidator()
        self.staging_service = staging_service or StagingDomainService(staging_manager=self.staging_manager)

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
        from rag_eval.legal.db.repositories import LegalRepository

        repo = LegalRepository(target_pool)

        now = get_vietnam_now()
        doc_id = uuid.uuid4()
        doc_meta = dict(session.doc_metadata) if session.doc_metadata else {}
        doc_entity = DocumentEntity(
            id=doc_id,
            doc_code=session.doc_code,
            title=session.title,
            effective_date=session.effective_date,
            expiration_date=session.expiration_date,
            metadata=doc_meta,
            raw_text=session.raw_text,
            created_at=now,
            updated_at=now,
        )

        async with repo.transaction() as conn:
            actual_doc_id = await repo.documents.upsert(doc_entity, conn=conn)

            canonical_chunks = [
                ChunkEntity(
                    id=uuid.uuid4(),
                    document_id=actual_doc_id,
                    path=c.path,
                    verbatim_text=c.verbatim_text,
                    contextualized_text=c.contextualized_text,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    embedding=None,
                    tsv_content=None,
                    metadata=c.metadata.model_dump(),
                    effective_date=c.effective_date,
                    expiration_date=c.expiration_date,
                    finalization_state=FinalizationState(c.finalization_state),
                    created_at=now,
                    updated_at=now,
                )
                for c in session.chunks
            ]
            path_to_uuid = await repo.chunks.upsert_batch(
                canonical_chunks, compute_embeddings=compute_embeddings, conn=conn
            )

            # Purge outgoing edges and refs from these chunks
            chunk_uuids = list(path_to_uuid.values())
            await repo.graph.delete_outgoing_edges_for_chunks(chunk_uuids, conn=conn)
            await repo.context_refs.delete_refs_for_chunks(chunk_uuids, conn=conn)

            # Map external target paths if needed
            unresolved_target_paths: list[str] = [
                e.target_path
                for e in session.edges
                if e.target_path and e.target_path not in path_to_uuid
            ]
            external_path_to_uuid: dict[str, uuid.UUID] = {}
            if unresolved_target_paths:
                external_path_to_uuid = await repo.chunks.resolve_paths_batch(
                    unresolved_target_paths, conn=conn
                )

            chunk_by_path = {c.path: c for c in session.chunks}
            resolved_edges: list[GraphEdgeEntity] = []
            context_refs: list[ChunkContextRefEntity] = []

            # Add dangling dependencies to context_refs
            for c in session.chunks:
                src_id = path_to_uuid[c.path]
                for dep in c.dangling_dependencies:
                    char_start = dep.char_start
                    char_end = dep.char_end
                    if char_start is None and dep.dependency_text and c.verbatim_text:
                        pos = c.verbatim_text.find(dep.dependency_text.strip())
                        if pos != -1:
                            char_start = pos
                            char_end = pos + len(dep.dependency_text.strip())
                    context_refs.append(
                        ChunkContextRefEntity(
                            id=uuid.uuid4(),
                            chunk_id=src_id,
                            char_start=char_start,
                            char_end=char_end,
                            citation_phrase=dep.dependency_text,
                            target_chunk_id=None,
                            edge_id=None,
                            target_path=None,
                            dependency_type="EXTERNAL_CITATION" if dep.dependency_type == "EXTERNAL_CITATION" else "OPEN_ENDED",
                            created_at=now,
                        )
                    )

            for edge in session.edges:
                src_id = path_to_uuid.get(edge.source_path)
                if src_id is None:
                    raise LegalDomainError(
                        error_code=E_CORPUS_INTEGRITY_VIOLATION,
                        message=f"Source chunk '{edge.source_path}' was not assigned a valid UUID during promotion.",
                        data={"source_path": edge.source_path},
                    )

                tgt_id = None
                if edge.target_path in path_to_uuid:
                    tgt_id = path_to_uuid[edge.target_path]
                elif edge.target_path in external_path_to_uuid:
                    tgt_id = external_path_to_uuid[edge.target_path]
                else:
                    raise LegalDomainError(
                        error_code=E_CORPUS_INTEGRITY_VIOLATION,
                        message=f"Target chunk '{edge.target_path}' not found in staged chunks or corpus database.",
                        data={"target_path": edge.target_path},
                    )

                src_chunk = chunk_by_path.get(edge.source_path)
                char_start, char_end = None, None
                if edge.citation_text and src_chunk:
                    pos = src_chunk.verbatim_text.find(edge.citation_text.strip())
                    if pos != -1:
                        char_start = pos
                        char_end = pos + len(edge.citation_text.strip())

                edge_id = uuid.uuid4()
                resolved_edges.append(
                    GraphEdgeEntity(
                        id=edge_id,
                        source_chunk_id=src_id,
                        target_chunk_id=tgt_id,
                        relation_type=StatutoryRelationType(edge.relation_type),
                        citation_text=edge.citation_text,
                        created_at=now,
                    )
                )
                if edge.citation_text:
                    context_refs.append(
                        ChunkContextRefEntity(
                            id=uuid.uuid4(),
                            chunk_id=src_id,
                            char_start=char_start,
                            char_end=char_end,
                            citation_phrase=edge.citation_text,
                            target_chunk_id=tgt_id,
                            edge_id=edge_id,
                            target_path=edge.target_path,
                            dependency_type="INTERNAL_REFERENCE",
                            created_at=now,
                        )
                    )

            inserted_edges_count = 0
            if resolved_edges:
                edge_map = await repo.graph.upsert_edges(resolved_edges, conn=conn)
                inserted_edges_count = len(edge_map)

            if context_refs:
                await repo.context_refs.batch_create_refs(context_refs, conn=conn)

        now = get_vietnam_now()
        await self.staging_service.update_status(
            doc_code=session.doc_code,
            request=StatusTransitionRequest(
                status=StagingStatus.PROMOTED,
                actor="HUMAN:reviewer",
                description=f"Promoted to production PostgreSQL (doc_id: {doc_id}). Notes: {reviewer_notes or 'None'}",
            ),
        )


        return PromotionResultResponse(
            status="SUCCESS",
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
