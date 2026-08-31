"""Unit tests for database migration discovery and execution."""

from __future__ import annotations

from rag_eval.legal.db.migrations import get_migration_sql_files


def test_get_migration_sql_files() -> None:
    """Verifies discovery and alphabetical ordering of SQL migration scripts."""
    sql_files = get_migration_sql_files()
    assert len(sql_files) >= 2
    filenames = [f.name for f in sql_files]
    assert "001_initial_schema.sql" in filenames
    assert "002_stored_procs.sql" in filenames
    # Asserts deterministic alphabetical sort
    assert filenames == sorted(filenames)
