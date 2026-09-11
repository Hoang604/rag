"""Every address named by an evaluation set must still exist in the corpus.

`qa_bench.py` drops a row whose `source_path` is not in the corpus rather than
failing on it. That is reasonable while a set is being built and dangerous
afterwards: re-chunking shifts `.w_<n>` window addresses, and a set that
quietly loses ten rows reports a score on ninety questions while its header
still says a hundred. Nothing in the output says which happened.

So this asserts the thing the benchmark declines to. It is the guard that makes
re-ingesting the corpus a decision rather than a gamble: after any change to
the parser or the chunker, it fails loudly and names every address that moved.

Runs against the **promoted corpus**, not the ephemeral database the migration
tests use. That distinction cost me a full run: `real_pg_pool` creates an empty
throwaway database, so every assertion here failed at once -- which looked like
fifteen broken fixtures and was one wrong fixture choice on my part.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"

PATH_SETS = sorted(FIXTURES.glob("qrels_*.jsonl")) + sorted(
    FIXTURES.glob("smoke_queries*.jsonl")
)

# `DATABASE_URL`, the same variable the application reads. This file first
# invented `LEGAL_DB_DSN`, which meant pointing the suite at another database
# silently kept this one on the default -- a test that claims to check the
# promoted corpus while checking a different one is worse than no test.
CORPUS_DSN = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:15432/rag_legal"
)


@pytest.fixture
async def corpus_pool() -> AsyncIterator[asyncpg.Pool]:
    """The promoted corpus, or a skip.

    Skipped rather than mocked: a made-up corpus cannot answer whether the real
    one still holds these addresses, and a test that passes against a mock here
    would be worse than no test.
    """
    try:
        pool = await asyncpg.create_pool(
            CORPUS_DSN, min_size=1, max_size=2, timeout=3.0
        )
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"không nối được corpus: {exc}")

    if pool is None:
        pytest.skip("không tạo được pool tới corpus")
    try:
        count = await pool.fetchval("SELECT count(*) FROM chunks")
        if not count:
            pytest.skip("corpus rỗng — chưa nạp văn bản")
        yield pool
    finally:
        await pool.close()


def _rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", PATH_SETS, ids=lambda p: p.name)
async def test_every_source_path_still_exists(
    fixture: Path, corpus_pool: asyncpg.Pool
) -> None:
    """A moved address silently shrinks the evaluation set it belongs to."""
    wanted = sorted(
        {
            str(row["source_path"])
            for row in _rows(fixture)
            if row.get("source_path") and row.get("expect", "hit") != "miss"
        }
    )
    if not wanted:
        pytest.skip("bộ đề này định địa chỉ bằng Điều/Khoản, không bằng path")

    present = {
        str(r["path"])
        for r in await corpus_pool.fetch(
            "SELECT path::text AS path FROM chunks WHERE path::text = ANY($1::text[])",
            wanted,
        )
    }

    missing = [p for p in wanted if p not in present]
    assert not missing, (
        f"{len(missing)}/{len(wanted)} địa chỉ trong {fixture.name} không còn "
        f"trong corpus, và qa_bench sẽ bỏ qua chúng mà không báo: {missing[:5]}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", PATH_SETS, ids=lambda p: p.name)
async def test_every_named_article_still_exists(
    fixture: Path, corpus_pool: asyncpg.Pool
) -> None:
    """The other way a set names its answer, checked the same way.

    A row giving `doc_code` and `article` survives re-chunking better than one
    giving a path, but not a renumbering or a document being replaced.
    """
    wanted = {
        (str(row["ground_truth"]["doc_code"]), str(row["ground_truth"]["article"]))
        for row in _rows(fixture)
        if row.get("ground_truth") and row["ground_truth"].get("article")
    }
    if not wanted:
        pytest.skip("bộ đề này không định địa chỉ bằng số Điều")

    rows = await corpus_pool.fetch(
        """
        SELECT DISTINCT d.doc_code,
               substring(c.path::text from '\\.a_([0-9]+[a-z]?)') AS article
        FROM chunks c JOIN documents d ON d.id = c.document_id
        """
    )
    present = {(str(r["doc_code"]), str(r["article"])) for r in rows if r["article"]}

    missing = sorted(w for w in wanted if w not in present)
    assert not missing, (
        f"{len(missing)} Điều được nêu trong {fixture.name} không có trong "
        f"corpus: {missing[:5]}"
    )
