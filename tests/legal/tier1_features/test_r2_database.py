"""Tier 1: Feature Coverage tests for Requirement 2 (R2) - Database Schema & Stored Procedures."""

from __future__ import annotations

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
            "đèn tín hiệu ô tô", vehicle_category="CAR_PASSENGER", limit=5
        )
        assert len(results) > 0
        top = results[0]
        assert top["doc_code"] == "100/2019/ND-CP"
        assert top["min_fine_vnd"] == 800000
        assert top["max_fine_vnd"] == 1000000
        assert top["rrf_score"] > 0.0

    async def test_hybrid_search_vehicle_filtering_isolates_motorcycle(self) -> None:
        db = MockDatabasePool()
        results = await db.execute_hybrid_search(
            "đèn tín hiệu", vehicle_category="MOTORCYCLE", limit=5
        )
        assert len(results) > 0
        for match in results:
            assert any(
                "MOTORCYCLE" in vt or "MOPED" in vt for vt in match["vehicle_types"]
            )

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
        assert "p102" in edge["target_path"].lower()

    async def test_sign_catalog_retrieval(self) -> None:
        db = MockDatabasePool()
        p102 = await db.get_sign("P.102")
        assert p102 is not None
        assert p102.sign_name == "Cấm đi ngược chiều"
        assert p102.category.value == "PROHIBITORY"

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
        assert hit["intent_classification"]["violation_type"] == "RED_LIGHT"
        assert hit["generated_plan"]["steps"] == ["hybrid_search", "scope_override_detect"]
        assert hit["similarity_score"] == 1.0
        assert hit["is_exact_match"] is True

        # Test backward-compatible hash seam
        hash_hit = await db.query_runtime_cache(write_res["query_hash"])
        assert hash_hit is not None
        assert hash_hit["synthesized_answer"] == hit["synthesized_answer"]
