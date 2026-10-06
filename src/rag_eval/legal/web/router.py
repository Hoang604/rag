from __future__ import annotations

import logging

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request

from rag_eval.legal.db.connection import check_db_health
from rag_eval.legal.db.repositories import LegalRepository
from rag_eval.legal.errors import (
    LegalDomainError,
)
from rag_eval.legal.ingestion.staging.manager import (
    StagingManager,
)
from rag_eval.legal.ingestion.staging.service import (
    StagingDomainService,
)
from rag_eval.legal.ingestion.staging.session import StagingDocumentSession
from rag_eval.legal.ingestion.wal import WALRecord
from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.schemas.api import (
    AnswerRequest,
    AnswerResponse,
    DocumentStatsDTO,
    DocumentTreeResponse,
    GroundingResponse,
    HealthResponse,
    ProviderResponse,
    SearchRequest,
)
from rag_eval.legal.schemas.domain import (
    RelationEdge,
    RelationEdgeFilter,
)
from rag_eval.legal.schemas.retrieval import (
    GraphTraverseRequest,
    GraphTraverseResult,
    GrepRequest,
    GrepResult,
    RawTextResult,
    SearchHit,
    SearchResult,
)
from rag_eval.legal.schemas.staging import (
    BatchPatchRequest,
    BatchPatchResult,
    CreateSessionRequest,
    FinalizeChunksRequest,
    FinalizeChunksResult,
    MutationResult,
    PreFlightValidationResponse,
    PromoteSessionRequest,
    PromotionResultResponse,
    ReparentSubtreeRequest,
    ReparentSubtreeResult,
    ReplayVerificationResponse,
    SessionSummary,
    StatusTransitionRequest,
    UnfinalizeChunksRequest,
    UnfinalizeChunksResult,
)
from rag_eval.legal.text import (
    get_vietnam_now,
    natural_legal_path_key,
    validate_ltree_path,
)
from rag_eval.legal.web.services.promotion import (
    HumanPromotionEngine,
)
from rag_eval.legal.web.services.tree import (
    TreeHierarchyBuilder,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Legal Staging Reviewer"])


def _get_staging_service(request: Request) -> StagingDomainService:
    """Helper to retrieve configured StagingDomainService instance from app state or fallback."""
    srv = getattr(request.app.state, "staging_service", None)
    if isinstance(srv, StagingDomainService):
        return srv
    mgr = getattr(request.app.state, "staging_manager", None)
    mgr_inst = mgr if isinstance(mgr, StagingManager) else StagingManager()
    pool = _get_db_pool(request)
    return StagingDomainService(staging_manager=mgr_inst, pool=pool)


def _get_db_pool(request: Request) -> asyncpg.Pool | None:
    """Helper to retrieve active db pool from app state if configured."""
    pool = getattr(request.app.state, "pool", None)
    if isinstance(pool, asyncpg.Pool):
        return pool
    return None


def _get_search_tools(request: Request) -> LegalMCPTools:
    """Builds the retrieval tools once and keeps them on app state."""
    cached = getattr(request.app.state, "search_tools", None)
    if isinstance(cached, LegalMCPTools):
        return cached

    from rag_eval.legal.mcp.tools import SentenceTransformerQueryEmbedder
    from rag_eval.legal.retrieval.reranker import CrossEncoderReranker

    tools = LegalMCPTools.build(
        pool=_get_db_pool(request),
        embedding_engine=SentenceTransformerQueryEmbedder(),
        reranker=CrossEncoderReranker(max_length=256),
    )
    request.app.state.search_tools = tools
    return tools


@router.post("/search", response_model=SearchResult)
async def search_corpus(request: Request, payload: SearchRequest) -> SearchResult:
    import time

    if _get_db_pool(request) is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    tools = _get_search_tools(request)
    started = time.perf_counter()
    try:
        result = await tools.hybrid_search(
            query=payload.query,
            temporal_violation_date=payload.violation_date,
            limit=payload.limit,
            rerank=payload.rerank,
            doc_codes=payload.doc_codes or None,
        )
    except LegalDomainError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    elapsed = (time.perf_counter() - started) * 1000.0

    return result.model_copy(
        update={
            "query": payload.query,
            "violation_date": payload.violation_date or str(get_vietnam_now().date()),
            "elapsed_ms": round(elapsed, 1),
        }
    )


@router.get("/documents", response_model=list[DocumentStatsDTO])
async def list_corpus_documents(request: Request) -> list[DocumentStatsDTO]:
    """The promoted corpus, for scoping a query to chosen documents."""
    pool = _get_db_pool(request)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    repo = LegalRepository(pool)
    return await repo.documents.list_with_stats()


@router.get("/answer/providers", response_model=list[ProviderResponse])
async def list_answer_providers() -> list[ProviderResponse]:
    """Which agent CLIs this machine has, so the UI offers only real options."""
    from rag_eval.legal.answer import available_providers

    return [
        ProviderResponse(name=p.name, label=p.label, installed=p.installed)
        for p in available_providers()
    ]


@router.post("/answer", response_model=AnswerResponse)
async def answer_question(request: Request, payload: AnswerRequest) -> AnswerResponse:
    """Retrieves provisions, then has a local agent CLI write the answer."""
    import asyncio
    import tempfile
    import time

    from rag_eval.legal.answer import AGENT_PROVIDER, AnswerError, compose

    if _get_db_pool(request) is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    tools = _get_search_tools(request)
    if payload.mode == "agent" and payload.provider == AGENT_PROVIDER:
        return await _answer_with_agent(request, tools, payload)
    started = time.perf_counter()
    try:
        result = await tools.hybrid_search(
            query=payload.query,
            temporal_violation_date=payload.violation_date,
            limit=payload.limit,
            rerank=payload.rerank,
            doc_codes=payload.doc_codes or None,
        )
    except LegalDomainError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    result = result.model_copy(update={"hits": await tools.expand_windows(result.hits)})
    retrieval_ms = (time.perf_counter() - started) * 1000.0

    with tempfile.TemporaryDirectory(prefix="rag_answer_") as workdir:
        try:
            composed = await asyncio.to_thread(
                compose, payload.query, result, payload.provider, workdir
            )
        except AnswerError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AnswerResponse(
        query=payload.query,
        provider=composed.provider,
        answer=composed.answer,
        abstained=composed.abstained,
        grounding=GroundingResponse(
            ok=composed.grounding.ok,
            unsupported_articles=composed.grounding.unsupported_articles,
            unsupported_amounts=composed.grounding.unsupported_amounts,
        ),
        confidence=result.confidence,
        retrieval_ms=round(retrieval_ms, 1),
        answer_ms=round(composed.elapsed_ms, 1),
        hits=result.hits,
    )


async def _answer_with_agent(
    request: Request, tools: LegalMCPTools, payload: AnswerRequest
) -> AnswerResponse:
    """Answers by letting the agent call the MCP tools itself, then shows what it cited."""
    import asyncio
    import re

    from rag_eval.legal.answer import AnswerError, check_grounding, compose_with_agent

    try:
        composed = await asyncio.to_thread(compose_with_agent, payload.query)
    except AnswerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    pool = _get_db_pool(request)
    assert pool is not None
    rows = await pool.fetch(
        """
        SELECT c.id, d.doc_code, d.title, c.path::text AS path, c.verbatim_text,
               c.contextualized_text, c.metadata, c.effective_date, c.expiration_date,
               c.start_line, c.end_line
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE c.path = ANY($1::ltree[])
        """,
        composed.paths,
    )
    by_path = {str(r["path"]): r for r in rows}
    kept = [path for path in dict.fromkeys(composed.paths) if path in by_path]
    hits = [
        SearchHit(
            doc_code=str(by_path[path]["doc_code"]),
            doc_title=str(by_path[path]["title"]),
            path=path,
            start_line=int(by_path[path]["start_line"]),
            end_line=int(by_path[path]["end_line"]),
            verbatim_text=str(by_path[path]["verbatim_text"]),
            contextualized_text=str(by_path[path]["contextualized_text"]),
            effective_date=by_path[path]["effective_date"],
            expiration_date=by_path[path]["expiration_date"]
            if by_path[path]["expiration_date"]
            else None,
            score=1.0,
        )
        for path in kept
    ]
    position = {path: index for index, path in enumerate(kept, start=1)}
    renumber = {
        number: position[path]
        for number, path in enumerate(composed.paths, start=1)
        if path in position
    }
    answer = re.sub(
        r"\[#(\d+)\]",
        lambda m: f"[#{renumber[int(m.group(1))]}]" if int(m.group(1)) in renumber else "",
        composed.answer,
    )
    grounding = check_grounding(answer, hits)
    return AnswerResponse(
        query=payload.query,
        provider="claude (agent)",
        answer=answer,
        abstained=False,
        grounding=GroundingResponse(
            ok=grounding.ok,
            unsupported_articles=grounding.unsupported_articles,
            unsupported_amounts=grounding.unsupported_amounts,
        ),
        confidence="high" if hits else "none",
        retrieval_ms=0.0,
        answer_ms=round(composed.elapsed_ms, 1),
        hits=hits,
    )


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


@router.get("/staging", response_model=list[SessionSummary])
async def list_staging_sessions(
    request: Request,
) -> list[SessionSummary]:
    """Lists summary cards for all discovered staging sessions in the staging directory."""
    service = _get_staging_service(request)
    return await service.list_sessions()


@router.post("/staging/raw", response_model=StagingDocumentSession)
async def create_staging_session_from_raw(
    request: Request, payload: CreateSessionRequest
) -> StagingDocumentSession:
    """Creates a fresh staging session by parsing raw statutory text with AST & CPHC engines."""
    service = _get_staging_service(request)
    return await service.create_session(payload)


@router.get("/staging/{doc_code:path}/tree", response_model=DocumentTreeResponse)
async def get_document_tree_hierarchy(
    request: Request, doc_code: str
) -> DocumentTreeResponse:
    """Returns nested document hierarchy tree formatted for the interactive canvas visualizer."""
    service = _get_staging_service(request)
    session = await service.get_session(doc_code)
    builder = TreeHierarchyBuilder()
    return builder.build_tree(session)


@router.post("/staging/{doc_code:path}/patch", response_model=BatchPatchResult)
async def batch_patch_chunks(
    request: Request, doc_code: str, payload: BatchPatchRequest
) -> BatchPatchResult:
    """Applies surgical in-place chunk updates and removals to the staging session."""
    service = _get_staging_service(request)
    _session, result = await service.patch_chunks(
        doc_code=doc_code,
        request=payload,
        actor="HUMAN:reviewer",
    )
    return result


@router.post(
    "/staging/{doc_code:path}/finalize", response_model=FinalizeChunksResult
)
async def finalize_staging_chunks(
    request: Request, doc_code: str, payload: FinalizeChunksRequest
) -> FinalizeChunksResult:
    """Marks specified chunk paths as finalized in the staging session."""
    service = _get_staging_service(request)
    _session, result = await service.finalize_chunks(
        doc_code=doc_code,
        request=payload,
        actor="HUMAN:reviewer",
    )
    return result


@router.post(
    "/staging/{doc_code:path}/unfinalize", response_model=UnfinalizeChunksResult
)
async def unfinalize_staging_chunks(
    request: Request, doc_code: str, payload: UnfinalizeChunksRequest
) -> UnfinalizeChunksResult:
    """Reverts specified chunk paths back to PENDING status in the staging session."""
    service = _get_staging_service(request)
    _session, result = await service.unfinalize_chunks(
        doc_code=doc_code,
        paths=payload.paths,
        actor="HUMAN:reviewer",
    )
    return result


@router.get("/staging/{doc_code:path}/edges", response_model=list[RelationEdge])
async def list_staging_edges(
    request: Request, doc_code: str
) -> list[RelationEdge]:
    """Lists all relational graph edges attached to the staging session."""
    service = _get_staging_service(request)
    session = await service.get_session(doc_code)
    return session.edges


@router.post(
    "/staging/{doc_code:path}/edges", response_model=StagingDocumentSession
)
async def add_staging_edges(
    request: Request,
    doc_code: str,
    payload: list[RelationEdge] | RelationEdge,
) -> StagingDocumentSession:
    """Adds or updates directed legal relationship edges in the staging session."""
    service = _get_staging_service(request)
    items = [payload] if isinstance(payload, RelationEdge) else payload
    edges = [
        RelationEdge(
            source_path=item.source_path,
            target_path=item.target_path,
            relation_type=item.relation_type,
            citation_text=item.citation_text,
        )
        for item in items
    ]
    session, _count = await service.add_edges(
        doc_code=doc_code,
        edges=edges,
        actor="HUMAN:reviewer",
    )
    return session


@router.delete(
    "/staging/{doc_code:path}/edges", response_model=StagingDocumentSession
)
async def delete_staging_edge(
    request: Request,
    doc_code: str,
    payload: RelationEdgeFilter,
) -> StagingDocumentSession:
    """Removes a relational graph edge matching source, target, and relation type."""
    service = _get_staging_service(request)
    session, _count = await service.remove_edges(
        doc_code=doc_code,
        filters=[payload],
        actor="HUMAN:reviewer",
    )
    return session


@router.post(
    "/staging/{doc_code:path}/status", response_model=StagingDocumentSession
)
async def transition_staging_status(
    request: Request, doc_code: str, payload: StatusTransitionRequest
) -> StagingDocumentSession:
    """Transitions staging session lifecycle status (e.g. DRAFT -> APPROVED)."""
    service = _get_staging_service(request)
    return await service.update_status(doc_code=doc_code, request=payload)


@router.post(
    "/staging/{doc_code:path}/reopen", response_model=StagingDocumentSession
)
async def reopen_staging_session(
    request: Request, doc_code: str, payload: StatusTransitionRequest | None = None
) -> StagingDocumentSession:
    """Reopens a PROMOTED staging session into AMENDMENT status, hydrating from DB if absent."""
    service = _get_staging_service(request)
    actor = payload.actor if payload else "HUMAN:reviewer"
    reason = payload.description if payload else "Reopened for amendment"
    return await service.reopen_session(doc_code=doc_code, actor=actor, reason=reason)





@router.get("/staging/{doc_code:path}/raw", response_model=RawTextResult)
async def get_raw_statutory_text(
    request: Request,
    doc_code: str,
    start_line: int = Query(1, ge=1),
    end_line: int | None = Query(None, ge=1),
) -> RawTextResult:
    """Returns raw source statutory text for dual-view split screen visualizer."""
    service = _get_staging_service(request)
    session = await service.get_session(doc_code)
    return session.get_raw_window(start_line=start_line, end_line=end_line)


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
    service = _get_staging_service(request)
    session = await service.get_session(doc_code)
    return service.validator.validate(session)


@router.post("/staging/{doc_code:path}/promote", response_model=PromotionResultResponse)
async def execute_human_promotion(
    request: Request, doc_code: str, payload: PromoteSessionRequest | None = None
) -> PromotionResultResponse:
    """Triggers atomic Human Promotion of approved staging session into PostgreSQL production tables."""
    service = _get_staging_service(request)
    pool = _get_db_pool(request)
    engine = HumanPromotionEngine(
        staging_manager=service.manager, staging_service=service
    )

    reviewer_notes = payload.reviewer_notes if payload else None
    compute_emb = payload.compute_embeddings if payload else True

    return await engine.promote_session(
        doc_code=doc_code,
        reviewer_notes=reviewer_notes,
        compute_embeddings=compute_emb,
        pool=pool,
    )


@router.post(
    "/staging/{doc_code:path}/reparent", response_model=ReparentSubtreeResult
)
async def reparent_staging_subtree(
    request: Request, doc_code: str, payload: ReparentSubtreeRequest
) -> ReparentSubtreeResult:
    """Migrates an entire subtree to a new parent prefix in the staging session."""
    service = _get_staging_service(request)
    _session, result = await service.reparent_subtree(
        doc_code=doc_code, request=payload
    )
    return result


@router.get("/staging/{doc_code:path}/wal", response_model=list[WALRecord])
async def get_staging_wal_journal(request: Request, doc_code: str) -> list[WALRecord]:
    """Returns complete ordered WAL journal entries for the document session."""
    service = _get_staging_service(request)
    return await service.get_wal_records(doc_code)


@router.post("/staging/{doc_code:path}/replay", response_model=ReplayVerificationResponse)
async def replay_staging_session(
    request: Request, doc_code: str, up_to_lsn: int | None = Query(None)
) -> ReplayVerificationResponse:
    """Deterministically replays the staging session from genesis baseline to specified LSN."""
    service = _get_staging_service(request)
    session, applied_lsn = await service.replay_session(doc_code, up_to_lsn=up_to_lsn)
    return ReplayVerificationResponse(
        status="SUCCESS",
        doc_code=doc_code,
        applied_lsn=applied_lsn,
        is_deterministic=True,
        total_chunks=len(session.chunks),
        total_edges=len(session.edges),
        message=f"Successfully replayed {applied_lsn + 1} WAL records from genesis baseline.",
    )


@router.post("/staging/{doc_code:path}/grep", response_model=GrepResult)
async def grep_staging_session(
    request: Request, doc_code: str, payload: GrepRequest
) -> GrepResult:
    """Searches staging session chunks in-memory using regex or substring matching."""
    service = _get_staging_service(request)
    session = await service.get_session(doc_code)
    hits = session.grep(
        pattern=payload.pattern,
        is_regex=payload.is_regex,
        case_sensitive=payload.case_sensitive,
        search_in=payload.search_in,
        limit=payload.limit,
    )
    return GrepResult(
        doc_code=doc_code,
        pattern=payload.pattern,
        is_regex=payload.is_regex,
        total_matches=len(hits),
        returned=len(hits),
        matches=hits,
    )



@router.post("/staging/{doc_code:path}/graph/traverse", response_model=GraphTraverseResult)
async def traverse_staging_graph(
    request: Request, doc_code: str, payload: GraphTraverseRequest
) -> GraphTraverseResult:
    """Traverses knowledge graph starting from a chunk path via PostgreSQL stored procedure traverse_knowledge_graph."""
    pool = _get_db_pool(request)
    if pool is None:
        return GraphTraverseResult(source_path=payload.source_path, total_paths=0, paths=[])

    try:
        clean_path = validate_ltree_path(payload.source_path)
    except ValueError:
        return GraphTraverseResult(source_path=payload.source_path, total_paths=0, paths=[])

    repo = LegalRepository(pool)
    try:
        steps = await repo.graph.traverse(
            source=clean_path,
            nav_direction=payload.nav_direction,
            depth_limit=payload.depth_limit,
            filter_relations=payload.filter_relations,
        )
        return GraphTraverseResult(
            source_path=payload.source_path,
            total_paths=len(steps),
            paths=steps,
        )
    except LegalDomainError as exc:
        logger.warning("Graph traverse failed for '%s': %s", clean_path, exc)
        return GraphTraverseResult(source_path=payload.source_path, total_paths=0, paths=[])


@router.get("/staging/{doc_code:path}", response_model=StagingDocumentSession)
async def get_staging_session_detail(
    request: Request, doc_code: str
) -> StagingDocumentSession:
    """Retrieves full detail, chunks, edges, and audit history for a staging document session."""
    service = _get_staging_service(request)
    session = await service.get_session(doc_code)
    session.chunks.sort(key=lambda c: natural_legal_path_key(c.path))
    return session


@router.delete("/staging/{doc_code:path}", response_model=MutationResult)
async def delete_staging_session(
    request: Request, doc_code: str
) -> MutationResult:
    """Deletes / discards a staging session file from disk."""
    service = _get_staging_service(request)
    deleted = await service.delete_session(doc_code)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Staging session for '{doc_code}' not found."
        )
    return MutationResult(
        status="SUCCESS",
        message=f"Staging session for '{doc_code}' deleted successfully.",
        doc_code=doc_code,
    )
