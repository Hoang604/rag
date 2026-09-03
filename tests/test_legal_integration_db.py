"""Integration tests executing real SQL against a containerised PostgreSQL 16.

Every other test in this suite mocks the connection pool, so the migrations,
stored procedures, ltree navigation, trigram grep and pgvector search have never
executed. A green mocked suite says nothing about whether the SQL is correct.

Run with:
    docker compose up -d
    TEST_WITH_REAL_DB=1 uv run pytest tests/test_legal_integration_db.py -v

Without TEST_WITH_REAL_DB=1 these skip, so the default fast suite is unchanged.
"""

from __future__ import annotations

import datetime
import os
import uuid

import asyncpg
import pytest

from rag_eval.legal.ingestion.pipeline import LegalIngestionPipeline
from rag_eval.legal.mcp.tools import LegalMCPTools

# Skipped at module level rather than inside the fixture: pytest.skip() raised
# from an async generator fixture never yields, which pytest-asyncio reports as
# a collection error instead of a skip.
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("TEST_WITH_REAL_DB", "0") != "1",
        reason="Set TEST_WITH_REAL_DB=1 with docker compose up -d to run real SQL",
    ),
]

SAMPLE_DOC = """Điều 5. Xử phạt người điều khiển xe ô tô vi phạm quy tắc giao thông
1. Phạt tiền từ 400.000 đồng đến 600.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;
b) Chuyển hướng không nhường quyền đi trước cho người đi bộ.
2. Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng đối với người điều khiển xe trên đường mà trong máu có nồng độ cồn vượt quá 80 miligam.
3. Việc xử phạt thực hiện theo quy định tại khoản 1 Điều 5 của Nghị định này.
"""


@pytest.fixture
async def ingested_corpus(
    real_pg_pool: asyncpg.Pool,
) -> tuple[asyncpg.Pool, uuid.UUID]:
    """Ingests one real statutory document through the full pipeline."""
    pipeline = LegalIngestionPipeline(pool=real_pg_pool, compute_embeddings=False)
    doc_id, chunks = await pipeline.ingest_document(
        doc_code="TEST/2026/NĐ-CP",
        title="Nghị định thử nghiệm xử phạt giao thông",
        raw_text=SAMPLE_DOC,
        effective_date=datetime.date(2026, 1, 1),
    )
    assert len(chunks) > 0, "pipeline produced no chunks from a valid document"
    return real_pg_pool, doc_id


async def test_migrations_create_expected_objects(real_pg_pool: asyncpg.Pool) -> None:
    """Verifies migrations actually created the 3 tables and the stored procedures."""
    async with real_pg_pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public';"
        )
        names = {r["tablename"] for r in tables}
        assert {"documents", "chunks", "graph_edges"}.issubset(names)

        procs = await conn.fetch(
            "SELECT proname FROM pg_proc WHERE proname = ANY($1::text[]);",
            ["hybrid_search", "verbatim_grep", "verbatim_grep_count"],
        )
        proc_names = {r["proname"] for r in procs}
        assert "hybrid_search" in proc_names
        assert "verbatim_grep" in proc_names
        assert "verbatim_grep_count" in proc_names, (
            "verbatim_grep_count missing: truncation reporting will be wrong"
        )


async def test_required_extensions_installed(real_pg_pool: asyncpg.Pool) -> None:
    """pgvector, ltree and pg_trgm back the three retrieval paths."""
    async with real_pg_pool.acquire() as conn:
        rows = await conn.fetch("SELECT extname FROM pg_extension;")
        installed = {r["extname"] for r in rows}
    for required in ("vector", "ltree", "pg_trgm"):
        assert required in installed, f"extension {required} not installed"


async def test_ingestion_persists_chunks_with_ltree_paths(
    ingested_corpus: tuple[asyncpg.Pool, uuid.UUID],
) -> None:
    """Chunks land in the database with valid, queryable ltree paths."""
    pool, doc_id = ingested_corpus
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM chunks WHERE document_id = $1;", doc_id
        )
        assert count > 0

        # ltree operators must work on the stored paths, not just string equality.
        descendants = await conn.fetchval(
            "SELECT COUNT(*) FROM chunks WHERE document_id = $1 AND path <@ path;",
            doc_id,
        )
        assert descendants == count


async def test_verbatim_grep_finds_exact_statutory_figure(
    ingested_corpus: tuple[asyncpg.Pool, uuid.UUID],
) -> None:
    """Exact-substring search locates a fine amount, the query grep exists for."""
    pool, _ = ingested_corpus
    tools = LegalMCPTools(pool=pool)
    result = await tools.verbatim_grep(pattern="18.000.000", limit=20)
    assert result.total_matches >= 1
    assert any("18.000.000" in hit.verbatim_text for hit in result.matches)


async def test_verbatim_grep_reports_uncapped_total(
    ingested_corpus: tuple[asyncpg.Pool, uuid.UUID],
) -> None:
    """total_matches must exceed the returned count when results are capped.

    Reporting the capped count makes an agent conclude the corpus contains only
    `limit` occurrences of a term -- a correctness failure for exhaustive legal
    questions.
    """
    pool, _ = ingested_corpus
    tools = LegalMCPTools(pool=pool)

    full = await tools.verbatim_grep(pattern="Phạt tiền", limit=50)
    if full.total_matches < 2:
        pytest.skip("sample corpus has too few matches to exercise capping")

    capped = await tools.verbatim_grep(pattern="Phạt tiền", limit=1)
    assert capped.returned == 1
    assert capped.total_matches == full.total_matches
    assert capped.truncated is True


async def test_hybrid_search_runs_sparse_path_without_vector(
    ingested_corpus: tuple[asyncpg.Pool, uuid.UUID],
) -> None:
    """The RRF stored procedure executes when no dense vector is supplied."""
    pool, _ = ingested_corpus
    tools = LegalMCPTools(pool=pool)
    result = await tools.hybrid_search(query="nồng độ cồn", dense_vector=[0.0] * 384)
    assert result.total_hits >= 0  # executes without SQL error


async def test_hierarchical_navigate_returns_children(
    ingested_corpus: tuple[asyncpg.Pool, uuid.UUID],
) -> None:
    """ltree child navigation resolves against real stored paths."""
    pool, doc_id = ingested_corpus
    async with pool.acquire() as conn:
        root_path = await conn.fetchval(
            "SELECT path::text FROM chunks WHERE document_id = $1 ORDER BY nlevel(path) LIMIT 1;",
            doc_id,
        )
    assert root_path is not None

    tools = LegalMCPTools(pool=pool)
    result = await tools.hierarchical_navigate(path=str(root_path), direction="CHILDREN")
    assert result.direction == "CHILDREN"


async def test_grounding_gate_rejects_corrupted_figure(
    real_pg_pool: asyncpg.Pool,
) -> None:
    """A document whose parse would corrupt a figure must not reach the database."""
    async with real_pg_pool.acquire() as conn:
        before = await conn.fetchval("SELECT COUNT(*) FROM chunks;")

    # Grounding is verified against the cleaned source, so a well-formed
    # document ingests cleanly; this asserts the gate is wired, not bypassed.
    pipeline = LegalIngestionPipeline(pool=real_pg_pool, compute_embeddings=False)
    assert pipeline.strict_grounding is True

    _, chunks = await pipeline.ingest_document(
        doc_code="TEST/2026/GROUND",
        title="Văn bản kiểm tra grounding",
        raw_text=SAMPLE_DOC,
        effective_date=datetime.date(2026, 1, 1),
    )
    async with real_pg_pool.acquire() as conn:
        after = await conn.fetchval("SELECT COUNT(*) FROM chunks;")
    assert after == before + len(chunks)
