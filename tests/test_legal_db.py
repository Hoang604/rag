"""Unit tests for database migration discovery and execution."""

from __future__ import annotations

from pathlib import Path

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


def test_sql_schema_tsvector_trigger_purified() -> None:
    """Verifies that update_chunks_tsv trigger does not strip slashes or unaccent text."""
    schema_path = Path("src/rag_eval/legal/db/sql/001_initial_schema.sql")
    content = schema_path.read_text(encoding="utf-8")

    # Invariant: Must not contain regexp_replace '[/]' or unaccent in update_chunks_tsv trigger
    assert "regexp_replace(unaccent" not in content
    assert "to_tsvector('vietnamese_legal', COALESCE(NEW.contextualized_text, ''))" in content
    assert "to_tsvector('vietnamese_legal', COALESCE(NEW.verbatim_text, ''))" in content


def test_sql_stored_procs_hybrid_search_purified() -> None:
    """Verifies that hybrid_search stored proc does not strip slashes or unaccent query_text."""
    procs_path = Path("src/rag_eval/legal/db/sql/002_stored_procs.sql")
    content = procs_path.read_text(encoding="utf-8")

    # Invariant: Must not contain regexp_replace '[/]' or unaccent in hybrid_search
    assert "clean_query TEXT := regexp_replace" not in content
    assert "clean_query TEXT := trim(COALESCE(query_text, ''));" in content
