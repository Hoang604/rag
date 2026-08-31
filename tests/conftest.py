from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

from rag_eval.legal.db.connection import close_db_pool, resolve_database_url
from rag_eval.legal.db.migrations import run_migrations
from rag_eval.legal.schemas import CanonicalFullyQualifiedChunk
from rag_eval.schemas import Document, GroundTruth, PredictionResult, Query, TextSpan
from tests.legal.fixtures.laws_data import (
    ALL_STATUTORY_CHUNKS,
    DECREE_100_ART5_CL3_PTA,
    DECREE_100_ART5_CL5_PTI,
    DECREE_100_ART5_CL8_PTA,
    DECREE_100_ART6_CL8_PTA,
    DECREE_123_ART2_CL3_PTA,
    DECREE_168_ART8_CL2,
    LAW_36_ART10_CL3,
)
from tests.legal.fixtures.signs_data import (
    ALL_SIGN_CATALOG,
    MARKING_1_1,
    SIGN_P102,
    SIGN_P106A,
    SIGN_P130,
    SIGN_P131A,
    SIGN_R412A,
    SIGN_R420,
    SIGN_W207A,
    SignDefinition,
)
from tests.legal.mocks.mock_db import MockDatabasePool

__all__ = [
    "ALL_SIGN_CATALOG",
    "ALL_STATUTORY_CHUNKS",
    "DECREE_100_ART5_CL3_PTA",
    "DECREE_100_ART5_CL5_PTI",
    "DECREE_100_ART5_CL8_PTA",
    "DECREE_100_ART6_CL8_PTA",
    "DECREE_123_ART2_CL3_PTA",
    "DECREE_168_ART8_CL2",
    "LAW_36_ART10_CL3",
    "MARKING_1_1",
    "SIGN_P102",
    "SIGN_P106A",
    "SIGN_P130",
    "SIGN_P131A",
    "SIGN_R412A",
    "SIGN_R420",
    "SIGN_W207A",
    "MockDatabasePool",
    "SignDefinition",
]


@pytest_asyncio.fixture(scope="session")
async def real_pg_pool() -> AsyncGenerator[asyncpg.Pool]:
    """Provides a real PostgreSQL 16 connection pool with migrated DDL and stored procedures."""
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
    except (
        OSError,
        TimeoutError,
        RuntimeError,
        asyncpg.PostgresError,
        asyncpg.InterfaceError,
        asyncpg.CannotConnectNowError,
    ) as exc:
        pytest.skip(f"PostgreSQL 16 container not reachable at {admin_dsn}: {exc}")
        return

    pool = await asyncpg.create_pool(
        dsn=test_dsn,
        min_size=1,
        max_size=5,
        timeout=3.0,
        command_timeout=10.0,
    )
    if pool is None:
        pytest.skip("PostgreSQL 16 connection pool could not be initialized")
        return

    try:
        await run_migrations(pool=pool)
        yield pool
    finally:
        await pool.close()
        await close_db_pool()
        try:
            assert "ephemeral" in test_db_name and test_db_name != "rag_legal"
            admin_conn = await asyncpg.connect(admin_dsn, timeout=3.0)
            try:
                await admin_conn.execute(f"DROP DATABASE IF EXISTS {test_db_name} WITH (FORCE);")
            finally:
                await admin_conn.close()
        except (OSError, TimeoutError, RuntimeError, asyncpg.PostgresError):
            pass


@pytest.fixture
def mock_db_pool() -> MockDatabasePool:
    """Provides an in-memory MockDatabasePool for lightweight unit test runs."""
    return MockDatabasePool()


def _generate_deterministic_pseudo_embedding(text: str, dim: int = 384) -> list[float]:
    """Generates a unit-normalized deterministic pseudo-embedding with cosine angle variance."""
    import hashlib
    import math

    tokens = text.lower().split()
    vec = [0.0] * dim
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for i in range(dim):
            weight = ((h >> (i % 64)) & 0xFF) / 255.0 - 0.5
            vec[i] += weight

    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        return [x / norm for x in vec]
    return [1.0 / math.sqrt(dim)] * dim


@pytest.fixture(autouse=True)
def _fast_unit_chunk_embeddings(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Provides fast synthetic vector embeddings for unit tests to eliminate transformer model load latency while preserving cosine angle variance."""
    if (
        "slow" in request.keywords
        or "test_100_live_queries" in request.node.nodeid
        or "test_challenger" in request.node.nodeid
    ):
        return
    monkeypatch.setattr(
        "rag_eval.legal.ingestion.loader.compute_chunk_embeddings",
        lambda texts, **kwargs: [_generate_deterministic_pseudo_embedding(t) for t in texts],
    )


@pytest_asyncio.fixture
async def legal_db_pool() -> AsyncGenerator[asyncpg.Pool | MockDatabasePool]:
    """Hybrid fixture: yields real ephemeral pool if TEST_WITH_REAL_DB=1, otherwise yields MockDatabasePool."""
    if os.getenv("TEST_WITH_REAL_DB", "0") == "1":
        test_dsn = "postgresql://postgres:postgres@localhost:54329/rag_legal_ephemeral_test"
        try:
            pool = await asyncpg.create_pool(
                dsn=test_dsn,
                min_size=1,
                max_size=5,
                timeout=2.0,
                command_timeout=5.0,
            )
            if pool is not None:
                yield pool
                await pool.close()
                return
        except (
            OSError,
            TimeoutError,
            RuntimeError,
            asyncpg.PostgresError,
            asyncpg.InterfaceError,
            asyncpg.CannotConnectNowError,
        ):
            pass

    yield MockDatabasePool()


@pytest.fixture
def legal_statutory_chunks() -> list[CanonicalFullyQualifiedChunk]:
    """Provides authoritative collection of statutory chunks from Decree 100, 123, 168, and Circular 31."""
    return list(ALL_STATUTORY_CHUNKS)


@pytest.fixture
def legal_sign_catalog() -> list[SignDefinition]:
    """Provides authoritative QCVN 41:2019 sign definitions."""
    return list(ALL_SIGN_CATALOG)


@pytest.fixture
def sample_legal_document() -> dict[str, object]:
    """Provides sample legal document metadata for Decree 100/2019/ND-CP."""
    return {
        "id": "doc_nd100",
        "doc_code": "100/2019/ND-CP",
        "title": "Nghị định 100/2019/NĐ-CP xử phạt vi phạm hành chính giao thông đường bộ và đường sắt",
        "doc_type": "NGHI_DINH",
        "effective_date": "2020-01-15",
        "status": "EFFECTIVE",
    }


@pytest.fixture
def sample_vehicle_scopes() -> dict[str, list[str]]:
    """Provides canonical vehicle category scope mapping."""
    return {
        "car": [
            "CAR_PASSENGER",
            "CAR_TRUCK",
            "CAR_BUS",
            "CAR_TRACTOR",
        ],
        "motorcycle": [
            "MOTORCYCLE",
            "MOPED",
            "E_MOPED",
        ],
        "bicycle": [
            "E_BICYCLE",
            "BICYCLE_PRIMITIVE",
        ],
    }


@pytest.fixture
def sample_documents() -> list[Document]:
    """Provide a list of sample domain documents."""
    return [
        Document(
            id="doc_law_001",
            text="Termination for convenience requires thirty days advance written notice.",
            title="Master Services Agreement",
            metadata={"category": "legal_contract"},
        ),
        Document(
            id="doc_bio_002",
            text="CRISPR Cas9 endonuclease enables targeted RNA-guided genome editing.",
            title="Genome Engineering Review",
            metadata={"category": "scientific_abstract"},
        ),
        Document(
            id="doc_fin_003",
            text="Quarterly dividend yields increased by fifteen percent across retail banking.",
            title="Q3 Financial Report",
            metadata={"category": "financial_report"},
        ),
    ]


@pytest.fixture
def sample_queries() -> list[Query]:
    """Provide a list of sample test queries."""
    return [
        Query(
            id="q_law",
            text="What is the notice period for contract termination?",
            metadata={"category": "legal_query"},
        ),
        Query(
            id="q_bio",
            text="How does CRISPR Cas9 perform genome editing?",
            metadata={"category": "bio_query"},
        ),
    ]


@pytest.fixture
def sample_ground_truths() -> list[GroundTruth]:
    """Provide reference ground truths matching the sample queries."""
    return [
        GroundTruth(
            query_id="q_law",
            relevant_doc_ids=["doc_law_001"],
            answers=["thirty days advance written notice"],
            spans=[
                TextSpan(
                    start_char=35,
                    end_char=71,
                    text="thirty days advance written notice",
                    section_name="Master Services Agreement",
                )
            ],
        ),
        GroundTruth(
            query_id="q_bio",
            relevant_doc_ids=["doc_bio_002"],
            answers=["targeted RNA-guided genome editing"],
            spans=[
                TextSpan(
                    start_char=35,
                    end_char=69,
                    text="targeted RNA-guided genome editing",
                    section_name="Genome Engineering Review",
                )
            ],
        ),
    ]


@pytest.fixture
def sample_predictions() -> list[PredictionResult]:
    """Provide sample predictions matching the queries and ground truths."""
    return [
        PredictionResult(
            query_id="q_law",
            retrieved_doc_ids=["doc_law_001", "doc_bio_002"],
            generated_answer="thirty days advance written notice.",
            latency_ms=12.5,
        ),
        PredictionResult(
            query_id="q_bio",
            retrieved_doc_ids=["doc_bio_002"],
            generated_answer="CRISPR Cas9 enables RNA-guided genome editing.",
            latency_ms=8.3,
        ),
    ]


@pytest.fixture(scope="session")
def parsed_law_36_pdf_text() -> str:
    """Session-memoized PDF text extraction for Law 36/2024/QH15 with fast text caching."""
    txt_path = Path("data/36-2024-qh15_tiep.txt")
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8")

    from rag_eval.legal.ingestion.converter import convert_pdf_to_text

    pdf_path = Path("data/36-2024-qh15_tiep.pdf")
    if not pdf_path.exists():
        return ""
    return convert_pdf_to_text(pdf_path)
