from __future__ import annotations

import logging

import asyncpg
from fastapi import APIRouter, HTTPException, Request

from rag_eval.legal.db.connection import check_db_health
from rag_eval.legal.db.repositories import LegalRepository
from rag_eval.legal.errors import LegalDomainError
from rag_eval.legal.eval.retrieval import (
    CaseRun,
    EvalCase,
    EvalRun,
    load_cases,
    run_all,
    run_case,
    save_cases,
)
from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.schemas.api import (
    AnswerRequest,
    AnswerResponse,
    DocumentStatsDTO,
    GroundingResponse,
    HealthResponse,
    ProviderResponse,
    SearchRequest,
)
from rag_eval.legal.schemas.retrieval import SearchHit, SearchResult
from rag_eval.legal.text import get_vietnam_now

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Legal RAG"])


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
    if payload.deep:
        return await _search_with_agent(request, tools, payload)
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

    return result.model_copy(update={"elapsed_ms": round(elapsed, 1)})


@router.get("/documents", response_model=list[DocumentStatsDTO])
async def list_corpus_documents(request: Request) -> list[DocumentStatsDTO]:
    """The ingested corpus, for scoping a query to chosen documents."""
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
        ProviderResponse(name=p.name, label=p.label, installed=p.installed, agent=p.agent)
        for p in available_providers()
    ]


@router.post("/answer", response_model=AnswerResponse)
async def answer_question(request: Request, payload: AnswerRequest) -> AnswerResponse:
    """Retrieves provisions, then has a local agent CLI write the answer."""
    import asyncio
    import tempfile
    import time

    from rag_eval.legal.answer import (
        AGENT_PROVIDERS,
        AnswerError,
        compose,
        rewrite_query,
    )

    if _get_db_pool(request) is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    tools = _get_search_tools(request)
    if payload.mode == "agent":
        if payload.provider not in AGENT_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Chế độ agent chỉ chạy với {', '.join(AGENT_PROVIDERS)}.",
            )
        return await _answer_with_agent(request, tools, payload)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="rag_rewrite_", ignore_cleanup_errors=True) as workdir:
        try:
            search_query = await asyncio.to_thread(rewrite_query, payload.query, payload.provider, workdir)
        except AnswerError as exc:
            logger.warning("Query rewrite failed, searching with the raw question: %s", exc)
            search_query = payload.query
    try:
        result = await tools.hybrid_search(
            query=search_query,
            temporal_violation_date=payload.violation_date,
            limit=payload.limit,
            rerank=payload.rerank,
            doc_codes=payload.doc_codes or None,
        )
    except LegalDomainError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    hits = await _with_licence_points(request, tools, await tools.expand_windows(result.hits))
    result = result.model_copy(update={"hits": hits})
    retrieval_ms = (time.perf_counter() - started) * 1000.0

    with tempfile.TemporaryDirectory(prefix="rag_answer_", ignore_cleanup_errors=True) as workdir:
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
        search_query=search_query,
    )


async def _hits_from_paths(
    request: Request, tools: LegalMCPTools, paths: list[str]
) -> list[SearchHit]:
    pool = _get_db_pool(request)
    assert pool is not None
    hits = await LegalRepository(pool).chunks.get_hits_by_paths(paths)
    return await tools.annotate_amendments(hits)


MAX_LICENCE_POINT_HITS = 3


async def _with_licence_points(
    request: Request, tools: LegalMCPTools, hits: list[SearchHit]
) -> list[SearchHit]:
    pool = _get_db_pool(request)
    if pool is None or not hits:
        return hits
    found = {hit.path for hit in hits}
    sources = await LegalRepository(pool).graph.licence_point_sources([hit.path for hit in hits])
    extra = [path for path in sources if path not in found][:MAX_LICENCE_POINT_HITS]
    if not extra:
        return hits
    return [*hits, *await _hits_from_paths(request, tools, extra)]


async def _search_with_agent(
    request: Request, tools: LegalMCPTools, payload: SearchRequest
) -> SearchResult:
    import asyncio

    from rag_eval.legal.answer import AnswerError, locate_with_agent

    try:
        paths, elapsed_ms = await asyncio.to_thread(locate_with_agent, payload.query)
    except AnswerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    hits = (await _hits_from_paths(request, tools, paths))[: payload.limit]
    ranked = [hit.model_copy(update={"rank": index}) for index, hit in enumerate(hits, start=1)]
    return SearchResult(
        query=payload.query,
        hits=ranked,
        violation_date=payload.violation_date or str(get_vietnam_now().date()),
        dense_is_informative=False,  # the agent chose these paths: there is no dense similarity to grade them by
        elapsed_ms=round(elapsed_ms, 1),
    )


async def _answer_with_agent(
    request: Request, tools: LegalMCPTools, payload: AnswerRequest
) -> AnswerResponse:
    from rag_eval.legal.answer import AnswerError, answer_with_agent

    async def hits_for_paths(paths: list[str]) -> list[SearchHit]:
        return await _hits_from_paths(request, tools, paths)

    try:
        result = await answer_with_agent(payload.provider, payload.query, hits_for_paths)
    except AnswerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AnswerResponse(
        query=payload.query,
        provider=f"{payload.provider} (agent)",
        answer=result.answer,
        abstained=False,
        grounding=GroundingResponse(
            ok=result.grounding.ok,
            unsupported_articles=result.grounding.unsupported_articles,
            unsupported_amounts=result.grounding.unsupported_amounts,
        ),
        confidence="high" if result.hits else "none",
        retrieval_ms=0.0,
        answer_ms=round(result.elapsed_ms, 1),
        hits=result.hits,
    )


def _case_index(cases: list[EvalCase], case_id: str) -> int:
    for index, case in enumerate(cases):
        if case.id == case_id:
            return index
    raise HTTPException(status_code=404, detail=f"No eval case '{case_id}'.")


@router.get("/eval/cases", response_model=list[EvalCase])
async def list_eval_cases() -> list[EvalCase]:
    """The retrieval evaluation set: questions, the agent's search call for each, and the expected provisions."""
    return load_cases()


@router.put("/eval/cases/{case_id}", response_model=EvalCase)
async def update_eval_case(case_id: str, payload: EvalCase) -> EvalCase:
    if payload.id != case_id:
        raise HTTPException(status_code=400, detail="The case id in the body must match the URL.")
    cases = load_cases()
    cases[_case_index(cases, case_id)] = payload
    save_cases(cases)
    return payload


@router.delete("/eval/cases/{case_id}", status_code=204)
async def delete_eval_case(case_id: str) -> None:
    cases = load_cases()
    del cases[_case_index(cases, case_id)]
    save_cases(cases)


@router.post("/eval/cases/{case_id}/run", response_model=CaseRun)
async def run_eval_case(request: Request, case_id: str) -> CaseRun:
    if _get_db_pool(request) is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    cases = load_cases()
    try:
        return await run_case(_get_search_tools(request), cases[_case_index(cases, case_id)])
    except LegalDomainError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc


@router.post("/eval/run", response_model=EvalRun)
async def run_eval(request: Request) -> EvalRun:
    """Replays every case's search call against the live system and scores where each expected provision landed."""
    if _get_db_pool(request) is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    try:
        return await run_all(_get_search_tools(request), load_cases())
    except LegalDomainError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc


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
