"""REST API routes for Legal Staging Reviewer."""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request

from rag_eval.legal.db.connection import check_db_health
from rag_eval.legal.ingestion.staging import (
    StagingChunkDelta,
    StagingEdge,
    StagingManager,
    StagingMutationRecord,
)
from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.schemas import LegalDomainError, get_vietnam_now
from rag_eval.legal.web.schemas import (
    BatchPatchRequest,
    BatchPatchResponse,
    CreateEdgeRequest,
    CreateSessionRequest,
    DeleteEdgeRequest,
    DocumentTreeResponse,
    GenericSuccessResponse,
    HealthResponse,
    PreFlightValidationResponse,
    PromoteSessionRequest,
    PromotionResultResponse,
    RawTextResponse,
    ReparentSubtreeRequest,
    ReparentSubtreeResponse,
    SearchHitResponse,
    SearchRequest,
    SearchResponse,
    SessionDiffResponse,
    StagingEdgeResponse,
    StagingSessionDetailResponse,
    StagingSessionSummaryResponse,
    StatusTransitionRequest,
)
from rag_eval.legal.web.service import (
    DiffCalculator,
    HumanPromotionEngine,
    PreFlightValidator,
    TreeHierarchyBuilder,
    natural_legal_path_key,
)

router = APIRouter(tags=["Legal Staging Reviewer"])


def _get_staging_manager(request: Request) -> StagingManager:
    """Helper to retrieve configured StagingManager instance from app state or fallback."""
    if (
        hasattr(request.app.state, "staging_manager")
        and request.app.state.staging_manager
    ):
        return request.app.state.staging_manager  # type: ignore[no-any-return]
    return StagingManager()


def _get_db_pool(request: Request) -> asyncpg.Pool | None:
    """Helper to retrieve active db pool from app state if configured."""
    if hasattr(request.app.state, "pool") and request.app.state.pool:
        return request.app.state.pool  # type: ignore[no-any-return]
    return None


# ------------------------------------------------------------------------------
# Retrieval
# ------------------------------------------------------------------------------


def _get_search_tools(request: Request) -> LegalMCPTools:
    """Builds the retrieval tools once and keeps them on app state.

    The embedding model costs seconds to load; per-request construction would
    put that on every search.
    """
    cached = getattr(request.app.state, "search_tools", None)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    from rag_eval.legal.mcp.tools import SentenceTransformerQueryEmbedder

    tools = LegalMCPTools(
        pool=_get_db_pool(request),
        embedding_engine=SentenceTransformerQueryEmbedder(),
    )
    request.app.state.search_tools = tools
    return tools


@router.post("/search", response_model=SearchResponse)
async def search_corpus(request: Request, payload: SearchRequest) -> SearchResponse:
    """Runs the real hybrid retrieval engine over the promoted corpus.

    This is the same path the MCP tool takes, facets included, so what the
    reviewer sees here is what an agent would get.
    """
    import time

    from rag_eval.legal.ingestion.facets import classify_intent, classify_query
    from rag_eval.legal.ingestion.xref import address_of_path
    from rag_eval.legal.retrieval.lexicon import expand_query

    if _get_db_pool(request) is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    tools = _get_search_tools(request)
    started = time.perf_counter()
    try:
        result = await tools.hybrid_search(
            query=payload.query,
            temporal_violation_date=payload.violation_date,
            limit=payload.limit,
        )
    except LegalDomainError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    elapsed = (time.perf_counter() - started) * 1000.0

    hits: list[SearchHitResponse] = []
    for rank, hit in enumerate(result.hits, start=1):
        address = address_of_path(hit.path)
        parts = [
            label
            for label in (
                f"Điều {address.dieu}" if address.dieu else "",
                f"Khoản {address.khoan}" if address.khoan else "",
                f"Điểm {address.diem}" if address.diem else "",
            )
            if label
        ]
        hits.append(
            SearchHitResponse(
                rank=rank,
                doc_code=hit.doc_code,
                doc_title=hit.doc_title,
                path=hit.path,
                address=" ".join(parts) or hit.path.split(".", 1)[-1],
                verbatim_text=hit.verbatim_text,
                contextualized_text=hit.contextualized_text,
                effective_date=hit.effective_date,
                expiration_date=hit.expiration_date,
                score=hit.score,
                vehicle_classes=list(hit.metadata.get("vehicle_classes") or []),
                provision_role=hit.metadata.get("provision_role"),
                dense_similarity=hit.dense_similarity,
                keyword_matched=hit.keyword_matched,
            )
        )

    return SearchResponse(
        query=payload.query,
        expanded_query=expand_query(payload.query),
        vehicle_class=classify_query(payload.query),
        provision_role=classify_intent(payload.query),
        violation_date=payload.violation_date or str(get_vietnam_now().date()),
        elapsed_ms=round(elapsed, 1),
        confidence=result.confidence,
        hits=hits,
    )


# ------------------------------------------------------------------------------
# 1. Health Probe
# ------------------------------------------------------------------------------
@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Health check endpoint probing database connectivity and service availability."""
    pool = _get_db_pool(request)
    is_healthy = await check_db_health(pool=pool)
    db_status = "CONNECTED" if is_healthy else "UNAVAILABLE"
    return HealthResponse(
        status="OK",
        database=db_status,
        timestamp=get_vietnam_now().isoformat(),
    )


# ------------------------------------------------------------------------------
# 2. Staging Sessions Lifecycle
# ------------------------------------------------------------------------------
@router.get("/staging", response_model=list[StagingSessionSummaryResponse])
async def list_staging_sessions(
    request: Request,
) -> list[StagingSessionSummaryResponse]:
    """Lists summary cards for all discovered staging sessions in the staging directory."""
    mgr = _get_staging_manager(request)
    summaries = mgr.list_sessions()
    return [
        StagingSessionSummaryResponse(
            doc_code=s.doc_code,
            title=s.title,
            status=s.status,
            total_chunks=s.total_chunks,
            total_edges=s.total_edges,
            effective_date=s.effective_date,
            expiration_date=s.expiration_date,
            created_at=s.created_at,
            updated_at=s.updated_at,
            committed_at=s.committed_at,
            promoted_at=s.promoted_at,
        )
        for s in summaries
    ]


@router.post("/staging/raw", response_model=StagingSessionDetailResponse)
async def create_staging_session_from_raw(
    request: Request, payload: CreateSessionRequest
) -> StagingSessionDetailResponse:
    """Creates a fresh staging session by parsing raw statutory text with AST & CPHC engines."""
    mgr = _get_staging_manager(request)
    session = mgr.create_session_from_raw(
        doc_code=payload.doc_code,
        title=payload.title,
        raw_text=payload.raw_text,
        effective_date=payload.effective_date,
        expiration_date=payload.expiration_date,
        metadata=payload.metadata,
    )
    return StagingSessionDetailResponse.model_validate(session.model_dump())


# ------------------------------------------------------------------------------
# 3. Document Tree Hierarchy & In-Place Editing
# ------------------------------------------------------------------------------
@router.get("/staging/{doc_code:path}/tree", response_model=DocumentTreeResponse)
async def get_document_tree_hierarchy(
    request: Request, doc_code: str
) -> DocumentTreeResponse:
    """Returns nested document hierarchy tree formatted for the interactive canvas visualizer."""
    mgr = _get_staging_manager(request)
    session = mgr.load_session(doc_code)
    builder = TreeHierarchyBuilder()
    return builder.build_tree(session)


@router.post("/staging/{doc_code:path}/patch", response_model=BatchPatchResponse)
async def batch_patch_chunks(
    request: Request, doc_code: str, payload: BatchPatchRequest
) -> BatchPatchResponse:
    """Applies surgical in-place chunk updates and removals to the staging session."""
    mgr = _get_staging_manager(request)
    updated_stg_deltas = [
        StagingChunkDelta(
            path=c.path,
            verbatim_text=c.verbatim_text,
            contextualized_text=c.contextualized_text,
            lead_sentence=c.lead_sentence,
            metadata=c.metadata,
            effective_date=c.effective_date,
            expiration_date=c.expiration_date,
        )
        for c in payload.updated_chunks
    ]
    session = mgr.patch_chunks(
        doc_code=doc_code,
        updated_chunks=updated_stg_deltas,
        removed_paths=payload.removed_paths,
    )
    return BatchPatchResponse(
        status="SUCCESS",
        doc_code=doc_code,
        updated_count=len(payload.updated_chunks),
        removed_count=len(payload.removed_paths),
        total_chunks=len(session.chunks),
    )


# ------------------------------------------------------------------------------
# 4. Relational Graph Edges
# ------------------------------------------------------------------------------
@router.get("/staging/{doc_code:path}/edges", response_model=list[StagingEdgeResponse])
async def list_staging_edges(
    request: Request, doc_code: str
) -> list[StagingEdgeResponse]:
    """Lists all relational graph edges attached to the staging session."""
    mgr = _get_staging_manager(request)
    session = mgr.load_session(doc_code)
    return [
        StagingEdgeResponse(
            source_path=e.source_path,
            target_path=e.target_path,
            target_external_ref=e.target_external_ref,
            relation_type=e.relation_type,
            citation_text=e.citation_text,
            metadata=e.metadata,
        )
        for e in session.edges
    ]


@router.post(
    "/staging/{doc_code:path}/edges", response_model=StagingSessionDetailResponse
)
async def add_staging_edges(
    request: Request,
    doc_code: str,
    payload: list[CreateEdgeRequest] | CreateEdgeRequest,
) -> StagingSessionDetailResponse:
    """Adds or updates directed legal relationship edges in the staging session."""
    mgr = _get_staging_manager(request)
    items = [payload] if isinstance(payload, CreateEdgeRequest) else payload
    edges = [
        StagingEdge(
            source_path=item.source_path,
            target_path=item.target_path,
            target_external_ref=item.target_external_ref,
            relation_type=item.relation_type,
            citation_text=item.citation_text,
            metadata=item.metadata,
        )
        for item in items
    ]
    session = mgr.add_edges(doc_code=doc_code, edges=edges)
    return StagingSessionDetailResponse.model_validate(session.model_dump())


@router.delete(
    "/staging/{doc_code:path}/edges", response_model=StagingSessionDetailResponse
)
async def delete_staging_edge(
    request: Request,
    doc_code: str,
    payload: DeleteEdgeRequest | None = None,
    source_path: str | None = Query(None),
    target_path: str | None = Query(None),
    relation_type: str | None = Query(None),
) -> StagingSessionDetailResponse:
    """Removes a relational graph edge matching source, target, and relation type."""
    mgr = _get_staging_manager(request)
    session = mgr.load_session(doc_code)

    src = payload.source_path if payload else source_path
    tgt = payload.target_path if payload else target_path
    rel = payload.relation_type if payload else relation_type

    if not src or not rel:
        raise HTTPException(
            status_code=400,
            detail="Must provide at least source_path and relation_type to delete edge.",
        )

    session.edges = [
        e
        for e in session.edges
        if not (
            e.source_path == src and e.target_path == tgt and e.relation_type == rel
        )
    ]

    now = get_vietnam_now()
    session.updated_at = now
    session.mutation_history.append(
        StagingMutationRecord(
            actor="HUMAN:reviewer",
            action_type="EDGE_REMOVED",
            description=f"Removed edge from '{src}' to '{tgt}' ({rel}).",
            timestamp=now,
            diff_payload={"source_path": src, "target_path": tgt, "relation_type": rel},
        )
    )

    mgr.save_session(session)
    return StagingSessionDetailResponse.model_validate(session.model_dump())


# ------------------------------------------------------------------------------
# 5. Status Transitions, Version Diff & Raw Text
# ------------------------------------------------------------------------------
@router.post(
    "/staging/{doc_code:path}/status", response_model=StagingSessionDetailResponse
)
async def transition_staging_status(
    request: Request, doc_code: str, payload: StatusTransitionRequest
) -> StagingSessionDetailResponse:
    """Transitions staging session lifecycle status (e.g. DRAFT -> APPROVED)."""
    mgr = _get_staging_manager(request)
    session = mgr.update_session_status(
        doc_code=doc_code,
        status=payload.status,
        actor=payload.actor,
        description=payload.description,
    )
    return StagingSessionDetailResponse.model_validate(session.model_dump())


@router.get("/staging/{doc_code:path}/diff", response_model=SessionDiffResponse)
async def get_session_version_diff(
    request: Request, doc_code: str
) -> SessionDiffResponse:
    """Returns 4-stage version mutation differences between initial AST baseline and current state."""
    mgr = _get_staging_manager(request)
    session = mgr.load_session(doc_code)
    calculator = DiffCalculator()
    return calculator.compute_diff(session)


@router.get("/staging/{doc_code:path}/raw", response_model=RawTextResponse)
async def get_raw_statutory_text(request: Request, doc_code: str) -> RawTextResponse:
    """Returns raw source statutory text for dual-view split screen visualizer."""
    mgr = _get_staging_manager(request)
    session = mgr.load_session(doc_code)
    return RawTextResponse(
        doc_code=session.doc_code,
        title=session.title,
        raw_text=session.raw_text or "",
        chunks_count=len(session.chunks),
    )


# ------------------------------------------------------------------------------
# 6. Pre-Flight Validation & Human Promotion Execution
# ------------------------------------------------------------------------------
@router.get(
    "/staging/{doc_code:path}/validate", response_model=PreFlightValidationResponse
)
@router.post(
    "/staging/{doc_code:path}/validate", response_model=PreFlightValidationResponse
)
async def run_preflight_validation(
    request: Request, doc_code: str
) -> PreFlightValidationResponse:
    """Runs automated pre-flight integrity verification checklist before promotion."""
    mgr = _get_staging_manager(request)
    session = mgr.load_session(doc_code)
    validator = PreFlightValidator()
    return validator.validate(session)


@router.post("/staging/{doc_code:path}/promote", response_model=PromotionResultResponse)
async def execute_human_promotion(
    request: Request, doc_code: str, payload: PromoteSessionRequest | None = None
) -> PromotionResultResponse:
    """Triggers atomic Human Promotion of approved staging session into PostgreSQL production tables."""
    mgr = _get_staging_manager(request)
    pool = _get_db_pool(request)
    engine = HumanPromotionEngine(staging_manager=mgr)

    reviewer_notes = payload.reviewer_notes if payload else None
    compute_emb = payload.compute_embeddings if payload else True

    return await engine.promote_session(
        doc_code=doc_code,
        reviewer_notes=reviewer_notes,
        compute_embeddings=compute_emb,
        pool=pool,
    )


# ------------------------------------------------------------------------------
# 7. Session Detail & Session Delete
# ------------------------------------------------------------------------------
@router.get("/staging/{doc_code:path}", response_model=StagingSessionDetailResponse)
async def get_staging_session_detail(
    request: Request, doc_code: str
) -> StagingSessionDetailResponse:
    """Retrieves full detail, chunks, edges, and audit history for a staging document session."""
    mgr = _get_staging_manager(request)
    session = mgr.load_session(doc_code)
    session.chunks.sort(key=lambda c: natural_legal_path_key(c.path))
    return StagingSessionDetailResponse.model_validate(session.model_dump())


@router.post(
    "/staging/{doc_code:path}/reparent", response_model=ReparentSubtreeResponse
)
async def reparent_staging_subtree(
    request: Request, doc_code: str, payload: ReparentSubtreeRequest
) -> ReparentSubtreeResponse:
    """Migrates an entire subtree to a new parent prefix in the staging session."""
    mgr = _get_staging_manager(request)
    session, result = mgr.reparent_node(
        doc_code=doc_code,
        old_path_prefix=payload.old_path_prefix,
        new_path_prefix=payload.new_path_prefix,
        dry_run=payload.dry_run,
        actor=payload.actor,
    )
    return ReparentSubtreeResponse(
        status="SUCCESS",
        doc_code=doc_code,
        dry_run=result.dry_run,
        affected_chunks_count=result.affected_chunks_count,
        affected_edges_count=result.affected_edges_count,
        old_path_prefix=result.old_path_prefix,
        new_path_prefix=result.new_path_prefix,
        total_chunks=len(session.chunks),
    )


@router.delete("/staging/{doc_code:path}", response_model=GenericSuccessResponse)
async def delete_staging_session(
    request: Request, doc_code: str
) -> GenericSuccessResponse:
    """Deletes / discards a staging session file from disk."""
    mgr = _get_staging_manager(request)
    deleted = mgr.delete_session(doc_code)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Staging session for '{doc_code}' not found."
        )
    return GenericSuccessResponse(
        status="SUCCESS",
        message=f"Staging session for '{doc_code}' deleted successfully.",
        doc_code=doc_code,
    )
