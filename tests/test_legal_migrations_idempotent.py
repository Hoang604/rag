"""Runs the migrations a second time and checks nothing moved.

`conftest` migrates a freshly created database, so the only path ever
exercised is the empty one. That is not the path a developer takes: they run
`legal-migrate` against a database that already has the schema and the corpus
in it. Eighteen files now carry `CREATE OR REPLACE`, an `ALTER TABLE`, and one
`UPDATE chunks` that rewrites the search index -- each of which is a chance for
the second run to fail, or to quietly change something.

Idempotency was checked by hand when those files were written. This makes it a
property the suite defends instead of a claim in a commit message.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import asyncpg
import pytest
import pytest_asyncio

from rag_eval.legal.db.migrations import run_migrations

pytestmark = pytest.mark.asyncio

_ADMIN_DSN = "postgresql://postgres:postgres@localhost:54329/postgres"
# The suite runs under xdist, so each worker needs a database of its own
# or the two tests race to CREATE the same name.
_DB = "rag_migr_idem_" + os.getenv("PYTEST_XDIST_WORKER", "main")


@pytest_asyncio.fixture
async def migrated_pool() -> AsyncGenerator[asyncpg.Pool]:
    """A database of its own, migrated once.

    `conftest.migrated_pool` cannot be used: it is session-scoped while the
    project runs asyncio fixtures at function scope, so requesting it raises
    ScopeMismatch. Nothing else in the suite requests it either, which is why
    that has gone unnoticed.
    """
    if os.getenv("TEST_WITH_REAL_DB", "0") != "1":
        pytest.skip("đặt TEST_WITH_REAL_DB=1 để chạy với PostgreSQL thật")

    dsn = f"postgresql://postgres:postgres@localhost:54329/{_DB}"
    try:
        admin = await asyncpg.connect(_ADMIN_DSN, timeout=3.0)
    except (OSError, TimeoutError, asyncpg.PostgresError) as exc:
        pytest.skip(f"không kết nối được PostgreSQL: {exc}")
    try:
        await admin.execute(f"DROP DATABASE IF EXISTS {_DB} WITH (FORCE);")
        await admin.execute(f"CREATE DATABASE {_DB};")
    finally:
        await admin.close()

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2, timeout=5.0)
    assert pool is not None
    try:
        await run_migrations(pool=pool)
        yield pool
    finally:
        await pool.close()
        admin = await asyncpg.connect(_ADMIN_DSN, timeout=5.0)
        try:
            await admin.execute(f"DROP DATABASE IF EXISTS {_DB} WITH (FORCE);")
        finally:
            await admin.close()


# Objects a migration could add, drop or redefine behind our back.
_SNAPSHOT = """
SELECT 'column' AS kind, table_name || '.' || column_name || ':' || data_type AS id
  FROM information_schema.columns WHERE table_schema = 'public'
UNION ALL
SELECT 'index', indexname || ':' || indexdef
  FROM pg_indexes WHERE schemaname = 'public'
UNION ALL
SELECT 'routine', p.proname || ':' || pg_get_function_identity_arguments(p.oid)
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public'
UNION ALL
SELECT 'constraint', conrelid::regclass::text || ':' || conname
  FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace
 WHERE n.nspname = 'public'
ORDER BY 1, 2
"""


async def _snapshot(pool: asyncpg.Pool) -> list[tuple[str, str]]:
    async with pool.acquire() as conn:
        return [(r["kind"], r["id"]) for r in await conn.fetch(_SNAPSHOT)]


async def test_running_the_migrations_twice_changes_nothing(
    migrated_pool: asyncpg.Pool,
) -> None:
    before = await _snapshot(migrated_pool)
    assert before, "ảnh chụp schema rỗng -- truy vấn sai, không phải schema rỗng"

    await run_migrations(pool=migrated_pool)  # must not raise

    after = await _snapshot(migrated_pool)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    assert not added and not removed, (
        f"lần chạy thứ hai làm schema lệch: thêm {added}, mất {removed}"
    )


async def test_a_third_run_is_also_clean(migrated_pool: asyncpg.Pool) -> None:
    """Catches a migration that alternates rather than settles."""
    await run_migrations(pool=migrated_pool)
    before = await _snapshot(migrated_pool)
    await run_migrations(pool=migrated_pool)
    assert await _snapshot(migrated_pool) == before
