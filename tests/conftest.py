"""Shared pytest fixtures for RAG evaluation and Vietnamese Traffic Law database subsystem."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

import asyncpg
import pytest
import pytest_asyncio

from rag_eval.legal.db.connection import close_db_pool, resolve_database_url
from rag_eval.legal.db.migrations import run_migrations
from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    VehicleCategory,
)
from rag_eval.schemas import Document, GroundTruth, PredictionResult, Query, TextSpan
from tests.legal.fixtures.laws_data import (
    ALL_STATUTORY_CHUNKS,
    CIRCULAR_31_ART6,
    DECREE_100_ART5_CL3_PTA,
    DECREE_100_ART5_CL5_PTI,
    DECREE_100_ART5_CL10_PTA,
    DECREE_100_ART6_CL4_PTE,
    DECREE_100_ART6_CL8_PTA,
    DECREE_100_ART24_CL5_PTA,
)
from tests.legal.fixtures.scenarios_data import (
    ALCOHOL_SCENARIOS,
    SPEEDING_SCENARIOS,
    AlcoholScenarioVector,
    SpeedingScenarioVector,
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
    "ALCOHOL_SCENARIOS",
    "ALL_SIGN_CATALOG",
    "ALL_STATUTORY_CHUNKS",
    "CIRCULAR_31_ART6",
    "DECREE_100_ART5_CL3_PTA",
    "DECREE_100_ART5_CL5_PTI",
    "DECREE_100_ART5_CL10_PTA",
    "DECREE_100_ART6_CL4_PTE",
    "DECREE_100_ART6_CL8_PTA",
    "DECREE_100_ART24_CL5_PTA",
    "MARKING_1_1",
    "SIGN_P102",
    "SIGN_P106A",
    "SIGN_P130",
    "SIGN_P131A",
    "SIGN_R412A",
    "SIGN_R420",
    "SIGN_W207A",
    "SPEEDING_SCENARIOS",
    "AlcoholScenarioVector",
    "MockDatabasePool",
    "SignDefinition",
    "SpeedingScenarioVector",
]


@pytest_asyncio.fixture(scope="session")
async def real_pg_pool() -> AsyncGenerator[asyncpg.Pool]:
    """Provides a real PostgreSQL 16 connection pool with migrated DDL and stored procedures.

    Provisions an isolated ephemeral database (rag_legal_ephemeral_test) on PostgreSQL 16 (port 54329),
    applies migrations, yields pool, and tears down with FORCE.
    Skips gracefully if TEST_WITH_REAL_DB != '1' or PostgreSQL container is not reachable.
    """
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

    # 1. Clean-Before-Create on Admin Connection
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

    # 2. Provision Connection Pool on Ephemeral Database & Run Migrations
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
        # 3. Forced Teardown Drop
        try:
            # Safety assertion: Never drop production database
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


# ============================================================================
# Vietnamese Traffic Law Shared Domain Fixtures (F-36)
# ============================================================================


@pytest.fixture
def legal_statutory_chunks() -> list[CanonicalFullyQualifiedChunk]:
    """Provides authoritative collection of statutory chunks from Decree 100, 123, 168, and Circular 31."""
    return list(ALL_STATUTORY_CHUNKS)


@pytest.fixture
def legal_sign_catalog() -> list[SignDefinition]:
    """Provides authoritative QCVN 41:2019 sign definitions."""
    return list(ALL_SIGN_CATALOG)


@pytest.fixture
def legal_speeding_scenarios() -> list[SpeedingScenarioVector]:
    """Provides authoritative speeding scenario vectors across road types and speed brackets."""
    return list(SPEEDING_SCENARIOS)


@pytest.fixture
def legal_alcohol_scenarios() -> list[AlcoholScenarioVector]:
    """Provides authoritative alcohol concentration scenario vectors across brackets 1, 2, and 3."""
    return list(ALCOHOL_SCENARIOS)


@pytest.fixture
def sample_legal_document() -> dict[str, Any]:
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
def sample_vehicle_scopes() -> dict[str, list[VehicleCategory]]:
    """Provides canonical vehicle category scope mapping."""
    return {
        "car": [
            VehicleCategory.CAR_PASSENGER,
            VehicleCategory.CAR_TRUCK,
            VehicleCategory.CAR_BUS,
            VehicleCategory.CAR_TRACTOR,
        ],
        "motorcycle": [
            VehicleCategory.MOTORCYCLE,
            VehicleCategory.MOPED,
            VehicleCategory.E_MOPED,
        ],
        "bicycle": [
            VehicleCategory.E_BICYCLE,
            VehicleCategory.BICYCLE_PRIMITIVE,
        ],
    }


# ============================================================================
# Generic Evaluation Framework Fixtures
# ============================================================================


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
