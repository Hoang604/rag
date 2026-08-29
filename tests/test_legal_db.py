"""Unit and mock tests for Vietnamese Traffic Law PostgreSQL database subsystem (M2).

Tests:
1. SQL Schema DDL verification: Extensions, enums, 7 tables, constraints.
2. Index suite verification: HNSW cosine indexes, ltree indexes, JSONB GIN, Trigram GIN, B-Tree.
3. In-database stored procedures & trigger functions in SQL files.
4. Database URL resolver & fallback logic.
5. Async connection pool manager lifecycle (get_db_pool, singleton behavior, close_db_pool).
6. Database healthcheck probes (healthy response vs failure handling).
7. Migration discovery and execution engine (ordering, idempotency, transaction rollback, advisory lock).
"""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from rag_eval.legal.db.connection import (
    DEFAULT_DATABASE_URL,
    check_db_health,
    close_db_pool,
    get_db_pool,
    resolve_database_url,
)
from rag_eval.legal.db.migrations import (
    MIGRATION_ADVISORY_LOCK_ID,
    get_applied_migrations,
    get_migration_sql_files,
    init_migration_table,
    run_migrations,
)


class TestSQLDDLSpecification:
    """Verifies that SQL migration files exist and define the complete required schema."""

    def test_migration_files_exist_and_sorted(self) -> None:
        files = get_migration_sql_files()
        assert len(files) >= 2
        file_names = [f.name for f in files]
        assert "001_initial_schema.sql" in file_names
        assert "002_stored_procs.sql" in file_names
        assert file_names == sorted(file_names)

    def test_001_schema_defines_all_8_extensions(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        content = files["001_initial_schema.sql"].read_text(encoding="utf-8")

        required_extensions = [
            "uuid-ossp",
            "pgcrypto",
            "vector",
            "ltree",
            "pg_trgm",
            "btree_gin",
            "btree_gist",
            "unaccent",
        ]
        for ext in required_extensions:
            assert f'"{ext}"' in content or f"'{ext}'" in content or ext in content, (
                f"Extension {ext} missing"
            )

    def test_001_schema_defines_all_8_enums(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        content = files["001_initial_schema.sql"].read_text(encoding="utf-8")

        required_enums = [
            "legal_document_type",
            "legal_document_status",
            "legal_node_type",
            "legal_norm_role",
            "actor_category",
            "graph_relation_type",
            "sign_category_enum",
            "cache_validation_status",
        ]
        for enum_name in required_enums:
            assert f"TYPE {enum_name}" in content, f"Enum {enum_name} missing"

    def test_001_schema_defines_canonical_8_norm_roles(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        content = files["001_initial_schema.sql"].read_text(encoding="utf-8")

        canonical_roles = [
            "HYPOTHESIS_CONDITION",
            "PRESCRIPTION_DUTY",
            "PRESCRIPTION_PROHIBITION",
            "PRESCRIPTION_PERMISSION",
            "SANCTION_PRINCIPAL",
            "SANCTION_SUPPLEMENTARY",
            "SANCTION_POINT_DEDUCTION",
            "REMEDIAL_MEASURE",
        ]
        for role in canonical_roles:
            assert f"'{role}'" in content, f"NormRole member {role} missing in DDL"

    def test_001_schema_defines_all_7_tables(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        content = files["001_initial_schema.sql"].read_text(encoding="utf-8")

        required_tables = [
            "legal_documents",
            "legal_hierarchy_nodes",
            "legal_chunks",
            "legal_graph_edges",
            "sign_catalog",
            "runtime_knowledge_cache",
            "query_execution_logs",
        ]
        for table_name in required_tables:
            assert (
                f"TABLE IF NOT EXISTS {table_name}" in content
                or f"TABLE {table_name}" in content
            ), f"Table {table_name} missing"

    def test_001_schema_defines_384_and_1536_hnsw_indexes(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        content = files["001_initial_schema.sql"].read_text(encoding="utf-8")

        assert "idx_legal_chunks_dense_embedding_384_hnsw" in content
        assert "dense_embedding_384 vector_cosine_ops" in content
        assert "idx_legal_chunks_dense_embedding_1536_hnsw" in content
        assert "idx_sign_catalog_embedding_384_hnsw" in content
        assert "idx_runtime_cache_query_embedding_384_hnsw" in content

    def test_001_schema_defines_nulls_not_distinct_edge_constraint(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        content = files["001_initial_schema.sql"].read_text(encoding="utf-8")

        assert "CONSTRAINT uq_graph_edge UNIQUE NULLS NOT DISTINCT" in content

    def test_001_schema_defines_ltree_and_gin_indexes(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        content = files["001_initial_schema.sql"].read_text(encoding="utf-8")

        assert "idx_legal_nodes_path_gist" in content
        assert "idx_legal_chunks_path_gist" in content
        assert "idx_legal_chunks_vehicle_types_gin" in content
        assert "jsonb_path_ops" in content
        assert "idx_sign_catalog_code_trgm" in content
        assert "gin_trgm_ops" in content
        assert "idx_runtime_cache_chunk_ids_gin" in content
        assert "idx_runtime_cache_edge_ids_gin" in content
        assert "idx_sign_catalog_chunk_id" in content
        assert "idx_sign_catalog_node_id" in content

    def test_001_schema_defines_vietnamese_fts_triggers(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        content = files["001_initial_schema.sql"].read_text(encoding="utf-8")

        assert "vietnamese_legal" in content
        assert "update_legal_chunks_tsv" in content
        assert "trg_legal_chunks_tsv_update" in content
        assert "idx_legal_chunks_tsv_vi" in content

    def test_002_stored_procs_defines_all_functions(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        content = files["002_stored_procs.sql"].read_text(encoding="utf-8")

        required_procs = [
            "expand_vehicle_category",
            "expand_vehicle_categories",
            "hybrid_legal_search",
            "hybrid_legal_search_384",
            "hybrid_legal_search_1536",
            "traverse_normative_triad",
            "resolve_scope_overrides",
            "query_runtime_knowledge_cache",
            "invalidate_dependent_runtime_cache",
            "invalidate_cache_on_edge_mutation",
        ]
        for proc in required_procs:
            assert f"FUNCTION {proc}" in content, f"Function {proc} missing"

    def test_002_stored_procs_defines_dual_vector_overloads_and_vehicle_expansion(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        content = files["002_stored_procs.sql"].read_text(encoding="utf-8")

        assert "COALESCE(d.rank_dense, 999)::BIGINT AS dense_rank" in content
        assert "COALESCE(s.rank_sparse, 999)::BIGINT AS sparse_rank" in content
        assert "query_vector VECTOR(384)" in content
        assert "query_vector VECTOR(1536)" in content
        assert "target_vehicles TEXT[]" in content
        assert "unaccent(category)" in content
        assert "WHEN 'XE_O_TO_CON' THEN ARRAY['CAR_PASSENGER']" in content
        assert "WHEN 'XE_DAU_KEO' THEN ARRAY['CAR_TRACTOR']" in content


class TestDatabaseConnectionManager:
    """Tests for connection.py lifecycle, DSN resolution, and healthchecks."""

    def test_resolve_database_url_precedence(self) -> None:
        # Explicit argument has highest precedence
        assert (
            resolve_database_url("postgresql://custom:custom@localhost:5432/custom_db")
            == "postgresql://custom:custom@localhost:5432/custom_db"
        )

        # Environment variable precedence over default
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://envuser:envpass@localhost:5432/envdb"},
        ):
            assert (
                resolve_database_url(None)
                == "postgresql://envuser:envpass@localhost:5432/envdb"
            )

        # Default fallback
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_database_url(None) == DEFAULT_DATABASE_URL

    @pytest.mark.asyncio
    async def test_get_db_pool_and_close(self) -> None:
        mock_pool = MagicMock(spec=asyncpg.Pool)
        mock_pool._closed = False

        async def async_close() -> None:
            mock_pool._closed = True

        mock_pool.close = AsyncMock(side_effect=async_close)

        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_pool

            # Reset pool state before test
            await close_db_pool()

            pool1 = await get_db_pool()
            assert pool1 is mock_pool
            mock_create.assert_called_once()

            # Singleton check - should not call create_pool again
            pool2 = await get_db_pool()
            assert pool2 is mock_pool
            assert mock_create.call_count == 1

            # Cleanup
            await close_db_pool()
            assert mock_pool._closed is True


    @pytest.mark.asyncio
    async def test_get_db_pool_connection_failure_raises_runtime_error(self) -> None:
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = OSError("Connection refused")
            await close_db_pool()

            with pytest.raises(RuntimeError, match="Failed to connect to database"):
                await get_db_pool(dsn="postgresql://invalid:5432/db")

    @pytest.mark.asyncio
    async def test_check_db_health_success(self) -> None:
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.fetchval = AsyncMock(return_value=1)

        mock_pool = MagicMock(spec=asyncpg.Pool)
        mock_pool._closed = False

        class MockAcquireContext:
            async def __aenter__(self) -> AsyncMock:
                return mock_conn

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

        mock_pool.acquire.return_value = MockAcquireContext()

        is_healthy = await check_db_health(pool=mock_pool)
        assert is_healthy is True
        mock_conn.fetchval.assert_called_once_with("SELECT 1;")

    @pytest.mark.asyncio
    async def test_check_db_health_failure_returns_false(self) -> None:
        mock_pool = MagicMock(spec=asyncpg.Pool)
        mock_pool.acquire.side_effect = OSError("Connection lost")

        is_healthy = await check_db_health(pool=mock_pool)
        assert is_healthy is False


class TestMigrationRunner:
    """Tests for migrations.py engine execution, idempotency, and advisory lock."""

    @pytest.mark.asyncio
    async def test_run_migrations_applies_unapplied_files(self, tmp_path: Path) -> None:
        m1 = tmp_path / "001_first.sql"
        m1.write_text("CREATE TABLE test1 (id INT);", encoding="utf-8")
        m2 = tmp_path / "002_second.sql"
        m2.write_text("CREATE TABLE test2 (id INT);", encoding="utf-8")

        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.execute = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        class MockTransactionContext:
            async def __aenter__(self) -> None:
                pass

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

        mock_conn.transaction.return_value = MockTransactionContext()

        mock_pool = MagicMock(spec=asyncpg.Pool)

        class MockAcquireContext:
            async def __aenter__(self) -> AsyncMock:
                return mock_conn

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

        mock_pool.acquire.return_value = MockAcquireContext()

        applied = await run_migrations(pool=mock_pool, sql_dir=tmp_path)
        assert applied == ["001_first.sql", "002_second.sql"]
        # Advisory lock acquired and released
        mock_conn.execute.assert_any_call(
            "SELECT pg_advisory_lock($1);", MIGRATION_ADVISORY_LOCK_ID
        )
        mock_conn.execute.assert_any_call(
            "SELECT pg_advisory_unlock($1);", MIGRATION_ADVISORY_LOCK_ID
        )

    @pytest.mark.asyncio
    async def test_run_migrations_idempotent_skips_applied(
        self, tmp_path: Path
    ) -> None:
        m1 = tmp_path / "001_first.sql"
        m1.write_text("CREATE TABLE test1 (id INT);", encoding="utf-8")
        m2 = tmp_path / "002_second.sql"
        m2.write_text("CREATE TABLE test2 (id INT);", encoding="utf-8")

        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.execute = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"version": "001_first.sql"}])

        class MockTransactionContext:
            async def __aenter__(self) -> None:
                pass

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

        mock_conn.transaction.return_value = MockTransactionContext()

        mock_pool = MagicMock(spec=asyncpg.Pool)

        class MockAcquireContext:
            async def __aenter__(self) -> AsyncMock:
                return mock_conn

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

        mock_pool.acquire.return_value = MockAcquireContext()

        applied = await run_migrations(pool=mock_pool, sql_dir=tmp_path)
        assert applied == ["002_second.sql"]

    @pytest.mark.asyncio
    async def test_run_migrations_failure_raises_runtime_error(
        self, tmp_path: Path
    ) -> None:
        m1 = tmp_path / "001_bad.sql"
        m1.write_text("INVALID SQL SYNTAX;", encoding="utf-8")

        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.fetch = AsyncMock(return_value=[])

        async def execute_side_effect(sql: str, *args: Any) -> None:
            if "INVALID SQL" in sql:
                raise asyncpg.PostgresSyntaxError("Syntax error at INVALID")

        mock_conn.execute = AsyncMock(side_effect=execute_side_effect)

        class MockTransactionContext:
            async def __aenter__(self) -> None:
                pass

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

        mock_conn.transaction.return_value = MockTransactionContext()

        mock_pool = MagicMock(spec=asyncpg.Pool)

        class MockAcquireContext:
            async def __aenter__(self) -> AsyncMock:
                return mock_conn

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

        mock_pool.acquire.return_value = MockAcquireContext()

        with pytest.raises(RuntimeError, match="Migration failed at 001_bad.sql"):
            await run_migrations(pool=mock_pool, sql_dir=tmp_path)

        # Advisory lock must still be released in finally block
        mock_conn.execute.assert_any_call(
            "SELECT pg_advisory_unlock($1);", MIGRATION_ADVISORY_LOCK_ID
        )

    @pytest.mark.asyncio
    async def test_init_and_get_applied_migrations(self) -> None:
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.fetch = AsyncMock(return_value=[{"version": "v1"}, {"version": "v2"}])

        await init_migration_table(mock_conn)
        applied = await get_applied_migrations(mock_conn)
        assert applied == {"v1", "v2"}
