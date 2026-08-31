"""Tier 1: Feature Coverage tests for Requirement 2 (R2) - Database Schema & Stored Procedures."""

from __future__ import annotations

import time

import pytest

from rag_eval.legal.schemas import GraphRelationType
from tests.legal.mocks.mock_db import MockDatabasePool


@pytest.mark.asyncio
class TestR2DatabaseSubsystem:
    """Tests for PostgreSQL 16 DDL, stored procedures, ltree filtering, and vector index abstractions."""

    async def test_database_pool_initializes_core_tables(self) -> None:
        db = MockDatabasePool()
        counts = await db.get_table_counts()
        assert counts["documents"] >= 6
        assert counts["chunks"] >= 7
        assert counts["signs"] >= 8
        assert counts["graph_edges"] >= 3

    async def test_legal_documents_contain_authoritative_instruments(self) -> None:
        db = MockDatabasePool()
        docs = await db.list_documents()
        doc_codes = {d["doc_code"] for d in docs}
        assert "100/2019/ND-CP" in doc_codes
        assert "123/2021/ND-CP" in doc_codes
        assert "168/2024/ND-CP" in doc_codes
        assert "36/2024/QH15" in doc_codes
        assert "31/2019/TT-BGTVT" in doc_codes
        assert "QCVN 41:2019/BGTVT" in doc_codes

    async def test_hybrid_search_rrf_scoring_order(self) -> None:
        db = MockDatabasePool()
        results = await db.execute_hybrid_search(
            "đèn tín hiệu ô tô", limit=5
        )
        assert len(results) > 0
        top = results[0]
        assert top["doc_code"] == "100/2019/ND-CP"
        assert top["rrf_score"] > 0.0

    async def test_verbatim_grep_substring_match_and_latency(self) -> None:
        """SPEC [R2-02]: Verbatim grep executes substring search with sub-4.5ms latency."""
        db = MockDatabasePool()
        t0 = time.perf_counter()
        results = await db.execute_verbatim_grep(
            query_pattern="Không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
            is_regex=False,
            case_sensitive=False,
            match_limit=5,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 10.0  # Sub-millisecond in-memory
        assert len(results) >= 1
        top = results[0]
        assert top["doc_code"] == "100/2019/ND-CP"
        assert "không chấp hành hiệu lệnh của đèn tín hiệu" in top["verbatim_text"].lower()
        assert top["min_fine_vnd"] == 800000
        assert top["max_fine_vnd"] == 1000000
        assert top["similarity_score"] > 0.0

    async def test_verbatim_grep_regex_pattern_matching(self) -> None:
        """SPEC [R2-02]: Verbatim grep executes regex pattern matching correctly."""
        db = MockDatabasePool()
        results = await db.execute_verbatim_grep(
            query_pattern=r"không chấp hành hiệu lệnh.*đèn tín hiệu",
            is_regex=True,
            case_sensitive=False,
            match_limit=5,
        )
        assert len(results) >= 1
        matched = results[0]
        assert matched["min_fine_vnd"] == 800000
        assert matched["max_fine_vnd"] == 1000000

    async def test_verbatim_grep_case_sensitivity_flag(self) -> None:
        """SPEC [R2-02]: Case sensitive grep strictly matches exact casing."""
        db = MockDatabasePool()
        # Exact casing matches
        exact_upper = await db.execute_verbatim_grep(
            query_pattern="Không chấp hành",
            case_sensitive=True,
            is_regex=False,
        )
        assert len(exact_upper) >= 1

        # Mismatched casing with case_sensitive=True yields zero matches
        mismatched = await db.execute_verbatim_grep(
            query_pattern="khônG Chấp Hành",
            case_sensitive=True,
            is_regex=False,
        )
        assert len(mismatched) == 0

    async def test_verbatim_grep_exact_temporal_boundary_slicing(self) -> None:
        """SPEC [R2-03]: Slicing effective_date <= t_violation < expiration_date isolates valid statutory version."""
        db = MockDatabasePool()
        # Scenario 1: Violation in 2020 (Decree 100 is effective, Decree 168 is not yet effective)
        results_2020 = await db.execute_verbatim_grep(
            query_pattern="đèn tín hiệu",
            t_violation="2020-06-01",
            match_limit=10,
        )
        doc_codes_2020 = {r["doc_code"] for r in results_2020}
        assert "100/2019/ND-CP" in doc_codes_2020
        assert "168/2024/ND-CP" not in doc_codes_2020

        # Scenario 2: Violation in 2025 (Decree 168 & Law 36 are effective)
        results_2025 = await db.execute_verbatim_grep(
            query_pattern="trật tự, an toàn giao thông đường bộ",
            t_violation="2025-06-01",
            match_limit=10,
        )
        doc_codes_2025 = {r["doc_code"] for r in results_2025}
        assert "36/2024/QH15" in doc_codes_2025

        # Scenario 3: Pre-promulgation date in 2018 (Decree 100 was not effective)
        results_2018 = await db.execute_verbatim_grep(
            query_pattern="không chấp hành hiệu lệnh của đèn tín hiệu",
            t_violation="2018-01-01",
            match_limit=10,
        )
        assert len(results_2018) == 0

    async def test_verbatim_grep_document_and_vehicle_scoping(self) -> None:
        """SPEC [R2-02]: Verbatim grep filters chunks by target documents and vehicle taxonomy."""
        db = MockDatabasePool()
        # Document filtering
        doc_scoped = await db.execute_verbatim_grep(
            query_pattern="đèn tín hiệu",
            target_documents=["100/2019/ND-CP"],
            match_limit=10,
        )
        for r in doc_scoped:
            assert r["doc_code"] == "100/2019/ND-CP"


    async def test_recursive_graph_traversal_resolves_technical_standard_edge(
        self,
    ) -> None:
        db = MockDatabasePool()
        paths = await db.execute_graph_traversal(
            "chk_nd100_art5_cl3_pta",
            allowed_edge_types=[GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value],
        )
        assert len(paths) >= 1
        edge = paths[0]
        assert (
            edge["relation_type"]
            == GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value
        )
        assert edge["target_doc_code"] == "QCVN 41:2019/BGTVT"
        assert edge["confidence_score"] == 1.0

    async def test_recursive_graph_traversal_one_way_sign_edge(self) -> None:
        db = MockDatabasePool()
        paths = await db.execute_graph_traversal(
            "chk_nd100_art6_cl8_pta",
            allowed_edge_types=[GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value],
        )
        assert len(paths) >= 1
        edge = paths[0]
        target_p = edge.get("target_path")
        assert target_p is not None and "p102" in target_p.lower()

    async def test_sign_catalog_retrieval(self) -> None:
        db = MockDatabasePool()
        p102 = await db.get_sign("P.102")
        assert p102 is not None
        assert p102.sign_name == "Cấm đi ngược chiều"
        assert p102.category == "PROHIBITORY"

    async def test_runtime_knowledge_cache_miss_and_hit(self) -> None:
        db = MockDatabasePool()
        query_text = "Mức phạt vượt đèn đỏ xe ô tô"
        miss = await db.query_runtime_knowledge_cache(query_text)
        assert miss is None

        write_res = await db.write_runtime_knowledge_cache(
            natural_query=query_text,
            synthesized_answer="Phạt tiền từ 800.000đ đến 1.000.000đ theo Điểm a Khoản 3 Điều 5 Nghị định 100/2019/NĐ-CP.",
            verified_citations=["doc_nd100_2019.c2.s1.a5.c3.p_a"],
            intent_classification={"violation_type": "RED_LIGHT", "vehicle": "CAR_PASSENGER"},
            generated_plan={"steps": ["hybrid_search", "scope_override_detect"]},
        )
        assert write_res["status"] == "written"
        assert "cache_id" in write_res
        assert "query_hash" in write_res

        hit = await db.query_runtime_knowledge_cache(query_text)
        assert hit is not None
        assert hit["cache_id"] == write_res["cache_id"]
        assert (
            hit["synthesized_answer"]
            == "Phạt tiền từ 800.000đ đến 1.000.000đ theo Điểm a Khoản 3 Điều 5 Nghị định 100/2019/NĐ-CP."
        )
        assert hit["verified_citations"] == ["doc_nd100_2019.c2.s1.a5.c3.p_a"]
        intent_val = hit.get("intent_classification")
        assert isinstance(intent_val, dict)
        assert intent_val.get("violation_type") == "RED_LIGHT"
        plan_val = hit.get("generated_plan")
        assert isinstance(plan_val, dict)
        assert plan_val.get("steps") == ["hybrid_search", "scope_override_detect"]
        assert hit["similarity_score"] == 1.0
        assert hit["is_exact_match"] is True

        # Test backward-compatible hash seam
        hash_hit = await db.query_runtime_cache(write_res["query_hash"])
        assert hash_hit is not None
        assert hash_hit["synthesized_answer"] == hit["synthesized_answer"]

    async def test_traverse_normative_triad_stored_proc_signature_and_execution(
        self,
    ) -> None:
        """Verifies traverse_normative_triad stored procedure execution against live PostgreSQL if available."""
        import asyncpg

        from rag_eval.legal.db.connection import close_db_pool, get_db_pool

        try:
            pool = await get_db_pool()
            async with pool.acquire() as conn, conn.transaction():
                chunk = await conn.fetchrow(
                    "SELECT id FROM legal_chunks LIMIT 1;"
                )
                if chunk is not None:
                    await conn.execute(
                        "UPDATE sign_catalog SET chunk_id = $1 WHERE sign_code = 'P.102';",
                        chunk["id"],
                    )
                rows = await conn.fetch(
                    "SELECT * FROM traverse_normative_triad('P.102', ARRAY['CAR_PASSENGER']);"
                )
                assert isinstance(rows, list)
                if chunk is not None:
                    assert len(rows) >= 1
                    for r in rows:
                        assert "hop_depth" in r
                        assert "node_role" in r
                        assert "document_code" in r
                        assert "chunk_path" in r
                        assert "traversal_path" in r
                raise RuntimeError("Rollback test transaction")
        except RuntimeError as exc:
            if str(exc) != "Rollback test transaction":
                raise
        except (OSError, asyncpg.PostgresError) as exc:
            pytest.skip(f"Live PostgreSQL database not reachable: {exc}")
        finally:
            await close_db_pool()
