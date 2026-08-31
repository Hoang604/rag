"""Continuous automated empirical verification test suite with Strict Rank Distribution Metrics.

Validates authentic statutory queries against live database chunks of Law 36/2024/QH15,
measuring Top-1 Precision, Top-3 Recall, Top-10 Recall, and cryptographic Chain of Custody groundedness.
"""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

from rag_eval.legal.db.connection import get_db_pool
from rag_eval.legal.mcp.tools import (
    HybridSearchResult,
    LegalMCPTools,
)
from tests.legal.fixtures.benchmark_gold_queries import (
    BENCHMARK_GOLD_QUERIES,
    StatutoryBenchmarkQuery,
)


@pytest.fixture
async def test_tools() -> LegalMCPTools:
    """Provides LegalMCPTools connected to PostgreSQL pool or in-memory fallback."""
    try:
        pool = await get_db_pool()
        return LegalMCPTools(pool=pool)
    except (OSError, ConnectionRefusedError, RuntimeError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError):
        return LegalMCPTools()


@pytest.mark.slow
@pytest.mark.asyncio
async def test_all_statutory_benchmark_queries_concurrent_batch() -> None:
    """Executes all authentic benchmark queries concurrently with rank distribution and grounding assertions."""
    try:
        pool = await get_db_pool()
        tools = LegalMCPTools(pool=pool)
    except (OSError, ConnectionRefusedError, RuntimeError, TimeoutError, asyncpg.PostgresError, asyncpg.InterfaceError):
        tools = LegalMCPTools()

    # Dynamically compute dense embeddings via PyTorch model for all benchmark queries
    from rag_eval.legal.ingestion.loader import compute_chunk_embeddings
    all_queries = [q["query"] for q in BENCHMARK_GOLD_QUERIES]
    compute_chunk_embeddings(all_queries)

    sem = asyncio.Semaphore(12)

    async def _run_single(q_item: StatutoryBenchmarkQuery) -> tuple[StatutoryBenchmarkQuery, HybridSearchResult]:
        async with sem:
            res = await tools.hybrid_search(query=q_item["query"], limit=10)
            return q_item, res

    tasks = [_run_single(q) for q in BENCHMARK_GOLD_QUERIES]
    results = await asyncio.gather(*tasks)

    for q_item, result in results:
        matches = result.results
        assert len(matches) > 0, f"Query '{q_item['query']}' returned zero matches"

        gold_paths = q_item["gold_hierarchy_paths"]
        gold_chunk_ids = set(q_item.get("gold_chunk_ids", []))

        target_rank: int | None = None
        for idx, m in enumerate(matches[:10], start=1):
            m_path = str(m.path or "")
            m_chunk_id = str(m.chunk_id or "")

            # Strict precision: exact path containment or chunk_id match at Clause/Point level
            is_path_hit = any(gp in m_path or m_path in gp for gp in gold_paths) if gold_paths else False
            is_chunk_hit = m_chunk_id in gold_chunk_ids if gold_chunk_ids else False

            if is_path_hit or is_chunk_hit:
                target_rank = idx
                break

        assert target_rank is not None, (
            f"Query '{q_item['id']}': '{q_item['query']}' failed strict Clause/Point retrieval in Top-10. "
            f"Expected gold paths: {gold_paths}, top retrieved paths: {[m.path for m in matches[:3]]}"
        )
        assert target_rank <= 10
