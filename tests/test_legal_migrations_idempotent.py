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

import asyncpg
import pytest

from rag_eval.legal.db.migrations import run_migrations

pytestmark = pytest.mark.asyncio

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
    real_pg_pool: asyncpg.Pool,
) -> None:
    before = await _snapshot(real_pg_pool)
    assert before, "ảnh chụp schema rỗng -- truy vấn sai, không phải schema rỗng"

    await run_migrations(pool=real_pg_pool)  # must not raise

    after = await _snapshot(real_pg_pool)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    assert not added and not removed, (
        f"lần chạy thứ hai làm schema lệch: thêm {added}, mất {removed}"
    )


async def test_a_third_run_is_also_clean(real_pg_pool: asyncpg.Pool) -> None:
    """Catches a migration that alternates rather than settles."""
    await run_migrations(pool=real_pg_pool)
    before = await _snapshot(real_pg_pool)
    await run_migrations(pool=real_pg_pool)
    assert await _snapshot(real_pg_pool) == before
