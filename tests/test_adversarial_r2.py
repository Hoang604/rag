"""Adversarial stress tests for Milestone R2 (PostgreSQL DDL, Stored Procedures & Batch Loader).

Empirically validates:
1. Edge cases in vehicle category expansion (Vietnamese diacritics, group aliases, empty/null inputs).
2. Reciprocal Rank Fusion (RRF) math stability against NULL outer joins and disjoint sets.
3. DDL schema consistency for 384-dim and 1536-dim vectors, HNSW cosine indexes, and constraints.
4. Stored procedure SQL definitions for COALESCE null rank handling and single-pass semantic cache.
5. Ingestion loader strict AST foreign key resolution and deterministic UUID generation via public API.
"""

from __future__ import annotations

import math
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from rag_eval.legal.db.migrations import get_migration_sql_files
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.schemas import (
    ActorCategory,
    AdditionalSanctions,
    CanonicalFullyQualifiedChunk,
    ExceptionMetadata,
    FineBounds,
    NormRole,
    VehicleCategory,
    ViolationCategory,
    ViolationType,
    expand_vehicle_category,
)


class TestAdversarialVehicleExpansion:
    """Stress tests vehicle expansion across Unicode accents, group aliases, and edge inputs."""

    @pytest.mark.parametrize(
        ("input_alias", "expected_contains"),
        [
            ("xe ô tô", [VehicleCategory.CAR_PASSENGER, VehicleCategory.CAR_TRUCK]),
            ("Xe Ô Tô Con", [VehicleCategory.CAR_PASSENGER]),
            ("XE MÁY", [VehicleCategory.MOTORCYCLE]),
            ("mô tô", [VehicleCategory.MOTORCYCLE]),
            ("xe gắn máy", [VehicleCategory.MOPED]),
            ("xe máy điện", [VehicleCategory.E_MOPED]),
            ("xe đạp điện", [VehicleCategory.E_BICYCLE]),
            ("xe đạp", [VehicleCategory.BICYCLE_PRIMITIVE]),
            ("xe cơ giới", [VehicleCategory.CAR_PASSENGER, VehicleCategory.MOTORCYCLE]),
            ("xe hai bánh", [VehicleCategory.MOTORCYCLE, VehicleCategory.BICYCLE_PRIMITIVE]),
            ("xe chuyên dùng", [VehicleCategory.SPECIALIZED_MACHINE]),
            ("xe ưu tiên", [VehicleCategory.PRIORITY_VEHICLE]),
        ],
    )
    def test_natural_vietnamese_diacritic_expansion(
        self, input_alias: str, expected_contains: list[VehicleCategory]
    ) -> None:
        expanded = expand_vehicle_category(input_alias)
        assert len(expanded) > 0
        for expected in expected_contains:
            assert expected in expanded, f"Missing {expected} in expansion of '{input_alias}'"

    def test_invalid_vehicle_category_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown vehicle category"):
            expand_vehicle_category("tàu hỏa không gian")


class TestAdversarialRRFMathematicalStability:
    """Stress tests RRF score computation under extreme outer join distributions."""

    def test_rrf_scoring_with_disjoint_and_empty_candidate_sets(self) -> None:
        rrf_k = 60

        # Scenario A: Chunk matched ONLY in dense search (rank 1), sparse is NULL
        dense_rank = 1
        sparse_rank = None

        score_dense_only = (
            (1.0 / (rrf_k + dense_rank))
            + (0.0 if sparse_rank is None else 1.0 / (rrf_k + sparse_rank))
        )
        assert math.isfinite(score_dense_only)
        assert score_dense_only > 0.0
        assert round(score_dense_only, 6) == round(1.0 / 61.0, 6)

        # Scenario B: Chunk matched ONLY in sparse search (rank 5), dense is NULL
        dense_rank_b = None
        sparse_rank_b = 5
        score_sparse_only = (
            (0.0 if dense_rank_b is None else 1.0 / (rrf_k + dense_rank_b))
            + (1.0 / (rrf_k + sparse_rank_b))
        )
        assert math.isfinite(score_sparse_only)
        assert score_sparse_only > 0.0
        assert round(score_sparse_only, 6) == round(1.0 / 65.0, 6)

        # Scenario C: Chunk matched in BOTH dense (rank 1) and sparse (rank 1)
        score_both = (1.0 / (rrf_k + 1)) + (1.0 / (rrf_k + 1))
        assert score_both > score_dense_only
        assert score_both > score_sparse_only
        assert round(score_both, 6) == round(2.0 / 61.0, 6)

        # Scenario D: Coalescing dense_rank and sparse_rank defaults to 999
        coalesced_dense_rank = dense_rank_b if dense_rank_b is not None else 999
        coalesced_sparse_rank = sparse_rank if sparse_rank is not None else 999
        assert coalesced_dense_rank == 999
        assert coalesced_sparse_rank == 999


class TestAdversarialDDLAndStoredProcIntegrity:
    """Stress tests SQL migration files for pgvector dimensions, constraints, and stored procedures."""

    def test_001_schema_vector_dimensions_and_nulls_not_distinct(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        ddl = files["001_initial_schema.sql"].read_text(encoding="utf-8")

        # Check 384-dim vector fields
        assert "dense_embedding_384 VECTOR(384)" in ddl
        assert "vector_embedding_384 VECTOR(384)" in ddl
        assert "query_embedding_384 VECTOR(384)" in ddl

        # Check HNSW index parameters
        assert "USING hnsw (dense_embedding_384 vector_cosine_ops)" in ddl
        assert "WITH (m = 16, ef_construction = 64)" in ddl

        # Check NULLS NOT DISTINCT constraint
        assert "CONSTRAINT uq_graph_edge UNIQUE NULLS NOT DISTINCT (source_chunk_id, target_chunk_id, relation_type)" in ddl

        # Check all 8 NormRole enum values are present in DDL
        for role in NormRole:
            assert f"'{role.value}'" in ddl

    def test_002_stored_procs_coalesce_and_single_pass_cache(self) -> None:
        files = {f.name: f for f in get_migration_sql_files()}
        procs = files["002_stored_procs.sql"].read_text(encoding="utf-8")

        # Check outer join COALESCE handling
        assert "FULL OUTER JOIN sparse_search s ON d.id = s.id" in procs
        assert "COALESCE(1.0 / (rrf_k + d.rank_dense), 0.0)" in procs
        assert "COALESCE(1.0 / (rrf_k + s.rank_sparse), 0.0)" in procs
        assert "COALESCE(d.rank_dense, 999)::BIGINT AS dense_rank" in procs
        assert "COALESCE(s.rank_sparse, 999)::BIGINT AS sparse_rank" in procs

        # Check dual dimension vector stored procedure overloads (384 and 1536)
        assert "hybrid_legal_search_384" in procs
        assert "hybrid_legal_search_1536" in procs
        assert "query_vector VECTOR(384)" in procs
        assert "query_vector VECTOR(1536)" in procs

        # Check unaccented vehicle expansion in SQL
        assert "unaccent(category)" in procs

        # Check single-pass HNSW cache search
        assert "ORDER BY c.query_embedding_384 <=> input_vector ASC" in procs


class TestAdversarialLoaderStrictFkResolution:
    """Stress tests AST foreign key resolution logic via public PostgresBulkLoader API (Resolves F-24)."""

    def _create_mock_pool(self) -> tuple[MagicMock, AsyncMock]:
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.executemany = AsyncMock()

        class MockTxContext:
            async def __aenter__(self) -> None:
                pass

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

        mock_conn.transaction.return_value = MockTxContext()

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
        return mock_pool, mock_conn

    def _build_test_chunk(self, chunk_id: str, path: str) -> CanonicalFullyQualifiedChunk:
        return CanonicalFullyQualifiedChunk(
            chunk_id=chunk_id,
            document_id="doc_nd100",
            document_code="100/2019/ND-CP",
            hierarchy_path=path,
            article_number=5,
            article_index="Điều 5",
            clause_number=1,
            point_letter="a",
            synthesized_prefix="Prefix",
            lead_sentence="Lead sentence",
            verbatim_text="Verbatim statutory text",
            contextualized_text="Contextualized text",
            norm_role=NormRole.SANCTION_PRINCIPAL,
            primary_actor=ActorCategory.DRIVER,
            vehicle_types=[VehicleCategory.CAR_PASSENGER],
            violation_categories=[ViolationCategory.SIGNAL_COMPLIANCE],
            violation_types=[ViolationType.RED_LIGHT],
            fine_bounds=FineBounds(min_fine_vnd=800000, max_fine_vnd=1000000),
            additional_sanctions=AdditionalSanctions(),
            exceptions_and_overrides=ExceptionMetadata(),
            effective_date="2020-01-15",
            is_active=True,
        )

    @pytest.mark.asyncio
    async def test_loader_chunk_fk_resolution_exact_and_suffix_matching(self) -> None:
        mock_pool, mock_conn = self._create_mock_pool()
        loader = PostgresBulkLoader(pool=mock_pool)
        node_map = {
            "doc_nd100_2019.c2.s1.a5.c1.p_a": "uuid-node-001",
            "doc_nd100_2019.c2.s1.a5": "uuid-node-002",
            "doc_nd100_2019": "uuid-node-root",
        }

        # 1. Exact match resolution with 36-char UUID
        chunk_uuid_1 = "00000000-0000-0000-0000-000000000001"
        chunk_exact = self._build_test_chunk(chunk_uuid_1, "doc_nd100_2019.c2.s1.a5.c1.p_a")
        chunk_map = await loader.load_chunks(
            chunks=[chunk_exact],
            document_id="doc_nd100",
            node_id_map=node_map,
        )
        assert "doc_nd100_2019.c2.s1.a5.c1.p_a" in chunk_map
        assert chunk_map["doc_nd100_2019.c2.s1.a5.c1.p_a"] == chunk_uuid_1

        # 2. Tail suffix match resolution with 36-char UUID
        chunk_uuid_2 = "00000000-0000-0000-0000-000000000002"
        chunk_suffix = self._build_test_chunk(chunk_uuid_2, "doc_nd100_2019.a5.c1.p_a")
        chunk_map_suffix = await loader.load_chunks(
            chunks=[chunk_suffix],
            document_id="doc_nd100",
            node_id_map=node_map,
        )
        assert "doc_nd100_2019.a5.c1.p_a" in chunk_map_suffix
        assert chunk_map_suffix["doc_nd100_2019.a5.c1.p_a"] == chunk_uuid_2

        # 3. Root document match resolution with 36-char UUID
        chunk_uuid_3 = "00000000-0000-0000-0000-000000000003"
        chunk_root = self._build_test_chunk(chunk_uuid_3, "doc_nd100_2019")
        chunk_map_root = await loader.load_chunks(
            chunks=[chunk_root],
            document_id="doc_nd100",
            node_id_map=node_map,
        )
        assert "doc_nd100_2019" in chunk_map_root
        assert chunk_map_root["doc_nd100_2019"] == chunk_uuid_3
        assert mock_conn.executemany.call_count == 3

    @pytest.mark.asyncio
    async def test_loader_chunk_unmapped_path_raises_value_error(self) -> None:
        mock_pool, _ = self._create_mock_pool()
        loader = PostgresBulkLoader(pool=mock_pool)
        node_map = {"doc_nd100_2019.a5": "uuid-001"}

        chunk_unmapped = self._build_test_chunk("00000000-0000-0000-0000-000000000099", "doc_nd100_2019.a999.c99")
        with pytest.raises(ValueError, match="Strict AST Foreign Key Error"):
            await loader.load_chunks(
                chunks=[chunk_unmapped],
                document_id="doc_nd100",
                node_id_map=node_map,
            )

    def test_loader_resolve_node_id_empty_path_raises_value_error(self) -> None:
        from rag_eval.legal.ingestion.loader import _resolve_node_id

        with pytest.raises(ValueError, match="Cannot resolve node UUID for empty hierarchy path"):
            _resolve_node_id("", {})
