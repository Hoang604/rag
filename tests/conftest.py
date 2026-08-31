"""Pytest configuration and shared fixtures for Agent-First legal system."""

from __future__ import annotations

import datetime
import logging
import os
import uuid
from collections.abc import AsyncGenerator

import asyncpg
import pytest
import pytest_asyncio

from rag_eval.legal.db.connection import close_db_pool, resolve_database_url
from rag_eval.legal.db.migrations import run_migrations
from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    DocumentRecord,
    GraphEdgeRecord,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def sample_document_record() -> DocumentRecord:
    """Provides a sample DocumentRecord for Decree 100/2019/ND-CP."""
    return DocumentRecord(
        id=uuid.uuid4(),
        doc_code="100/2019/NĐ-CP",
        title="Nghị định quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ và đường sắt",
        effective_date=datetime.date(2020, 1, 15),
        expiration_date=None,
        metadata={"doc_type": "NGHI_DINH", "issuing_authority": "Chính phủ"},
    )


@pytest.fixture
def sample_chunk_record(sample_document_record: DocumentRecord) -> CanonicalFullyQualifiedChunk:
    """Provides a sample CanonicalFullyQualifiedChunk for Article 5 Clause 3 Point a."""
    return CanonicalFullyQualifiedChunk(
        id=uuid.uuid4(),
        document_id=sample_document_record.id,
        path="doc_100_2019_nd_cp.c_ii.a_5.c_3.p_a",
        verbatim_text="Điểm a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;",
        contextualized_text="[Nghị định 100/2019/NĐ-CP] > [Chương II] > [Điều 5: Xử phạt người điều khiển xe ô tô] > [Khoản 3: Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:]\nĐiểm a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;",
        embedding=[0.05] * 384,
        effective_date=datetime.date(2020, 1, 15),
        expiration_date=None,
        metadata={
            "fines": {"min_vnd": 800000, "max_vnd": 1000000},
            "vehicles": ["CAR"],
            "norm_roles": ["SANCTION_PRINCIPAL"],
        },
    )


@pytest.fixture
def sample_graph_edge(sample_chunk_record: CanonicalFullyQualifiedChunk) -> GraphEdgeRecord:
    """Provides a sample GraphEdgeRecord."""
    return GraphEdgeRecord(
        id=uuid.uuid4(),
        source_chunk_id=sample_chunk_record.id,
        target_chunk_id=None,
        target_external_ref="Điều 12 Luật Giao thông đường bộ 2008",
        relation_type="REFERENCES",
        citation_text="theo quy định tại Điều 12 Luật Giao thông đường bộ",
        metadata={"confidence": 1.0},
    )


@pytest_asyncio.fixture(scope="session")
async def real_pg_pool() -> AsyncGenerator[asyncpg.Pool]:
    """Provides a real PostgreSQL 16 connection pool when TEST_WITH_REAL_DB=1."""
    if os.getenv("TEST_WITH_REAL_DB", "0") != "1":
        pytest.skip("Set TEST_WITH_REAL_DB=1 to run tests against real containerized PostgreSQL")
        return

    admin_dsn = resolve_database_url(
        os.getenv(
            "TEST_ADMIN_DATABASE_URL",
            "postgresql://postgres:postgres@localhost:54329/postgres",
        )
    )
    test_db_name = "rag_legal_ephemeral_test"
    test_dsn = f"postgresql://postgres:postgres@localhost:54329/{test_db_name}"

    try:
        admin_conn = await asyncpg.connect(admin_dsn, timeout=3.0)
        try:
            await admin_conn.execute(f"DROP DATABASE IF EXISTS {test_db_name} WITH (FORCE);")
            await admin_conn.execute(f"CREATE DATABASE {test_db_name};")
        finally:
            await admin_conn.close()
    except (OSError, TimeoutError, RuntimeError, asyncpg.PostgresError) as exc:
        pytest.skip(f"PostgreSQL container unreachable: {exc}")
        return

    pool = await asyncpg.create_pool(
        dsn=test_dsn,
        min_size=1,
        max_size=5,
        timeout=3.0,
    )
    if pool is None:
        pytest.skip("Could not create test pool")
        return

    try:
        await run_migrations(pool=pool)
        yield pool
    finally:
        await pool.close()
        await close_db_pool()
        try:
            admin_conn = await asyncpg.connect(admin_dsn, timeout=3.0)
            try:
                await admin_conn.execute(f"DROP DATABASE IF EXISTS {test_db_name} WITH (FORCE);")
            finally:
                await admin_conn.close()
        except (OSError, TimeoutError, RuntimeError, asyncpg.PostgresError) as exc:
            logger.debug("Cleanup ephemeral test database error: %s", exc)
