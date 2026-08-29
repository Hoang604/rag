"""Unit and Integration Tests for Vietnamese Traffic Law Reasoning Engine (R5)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.reasoning.chain_of_custody import (
    ChainOfCustodyVerifier,
)
from rag_eval.legal.reasoning.overrides import (
    EmergencyVehicleTier,
    ScopeOverrideEngine,
    StatutoryPrecedenceRank,
)
from rag_eval.legal.reasoning.pipeline import LegalReasoningPipeline
from rag_eval.legal.reasoning.traverser import (
    DeterministicTriadTraverser,
)
from rag_eval.legal.schemas import (
    ExecutionPlanDAG,
    SignalTier,
    Temporality,
)


class MockTraverserMCPTools(LegalMCPTools):
    """Mock MCP tool provider to verify parallel beam expansion and cycle detection."""

    def __init__(self) -> None:
        super().__init__()
        self.hybrid_search_calls: int = 0
        self.graph_traverse_calls: int = 0

    async def hybrid_search(
        self,
        query: str,
        query_vector: list[float] | None = None,
        vehicle_types: list[str] | None = None,
        actor_category: str | None = None,
        norm_roles: list[str] | None = None,
        fine_min_vnd: int | None = None,
        fine_max_vnd: int | None = None,
        document_codes: list[str] | None = None,
        effective_as_of: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        self.hybrid_search_calls += 1
        return {
            "status": "success",
            "total_hits": 2,
            "results": [
                {
                    "chunk_id": "chk_nd100_a5_c3_pa",
                    "path": "doc_nd100_2019.a5.c3.p_a",
                    "doc_code": "100/2019/ND-CP",
                    "norm_role": "SANCTION_PRINCIPAL",
                    "raw_text": "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với ô tô vượt đèn đỏ",
                    "rrf_score": 0.95,
                },
                {
                    "chunk_id": "chk_nd100_a6_c3_pb",
                    "path": "doc_nd100_2019.a6.c3.p_b",
                    "doc_code": "100/2019/ND-CP",
                    "norm_role": "SANCTION_PRINCIPAL",
                    "raw_text": "Phạt tiền từ 600.000 đồng đến 1.000.000 đồng đối với xe máy vượt đèn đỏ",
                    "rrf_score": 0.85,
                },
            ],
        }

    async def graph_traverse(
        self,
        start_chunk_id: str,
        relation_types: list[str] | None = None,
        direction: str = "BOTH",
        max_depth: int = 2,
    ) -> dict[str, Any]:
        self.graph_traverse_calls += 1
        await asyncio.sleep(0.01)  # Simulate I/O latency

        if start_chunk_id == "chk_nd100_a5_c3_pa":
            return {
                "status": "success",
                "start_chunk_id": start_chunk_id,
                "total_paths": 2,
                "traversal_paths": [
                    {
                        "target_chunk_id": "chk_nd100_a5_c11_pb",
                        "target_path": "doc_nd100_2019.a5.c11.p_b",
                        "target_doc_code": "100/2019/ND-CP",
                        "target_norm_role": "SANCTION_SUPPLEMENTARY",
                        "target_raw_text": "Tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng",
                        "relation_type": "HAS_ADDITIONAL_SANCTION",
                        "confidence_score": 1.0,
                    },
                    {
                        "target_chunk_id": "chk_qcvn41_a4",
                        "target_path": "doc_qcvn41_2019.a4",
                        "target_doc_code": "QCVN 41:2019/BGTVT",
                        "target_norm_role": "HYPOTHESIS_CONDITION",
                        "target_raw_text": "Quy chuẩn hiệu lệnh đèn tín hiệu giao thông",
                        "relation_type": "REFERENCES_TECHNICAL_STANDARD",
                        "confidence_score": 0.95,
                    },
                ],
            }
        elif start_chunk_id == "chk_nd100_a5_c11_pb":
            return {
                "status": "success",
                "start_chunk_id": start_chunk_id,
                "total_paths": 1,
                "traversal_paths": [
                    {
                        "target_chunk_id": "chk_luat_a10",
                        "target_path": "doc_luatgtdb_2008.a10",
                        "target_doc_code": "Luật GTĐB 2008",
                        "target_norm_role": "PRESCRIPTION_DUTY",
                        "target_raw_text": "Người tham gia giao thông phải chấp hành hiệu lệnh và chỉ dẫn của hệ thống báo hiệu đường bộ",
                        "relation_type": "GUIDES",
                        "confidence_score": 0.90,
                    }
                ],
            }
        return {"status": "success", "start_chunk_id": start_chunk_id, "total_paths": 0, "traversal_paths": []}

    async def scope_override_detect(
        self,
        scenario_type: str = "POLICE_OVERRIDE_RED_LIGHT",
        candidate_chunk_id: str | None = None,
        context_conditions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "success",
            "is_override_active": True,
            "dominant_authority": "POLICE_OFFICER",
            "statutory_rank": 1.0,
            "legal_basis": ["QCVN 41:2019/BGTVT Điều 4"],
        }


class TestReasoningEngineModules:
    """Comprehensive test coverage for planner, traverser, overrides, and CoC."""

    # --------------------------------------------------------------------------
    # 1. Deterministic Parallel Traverser
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_traverser_parallel_expansion_and_seed_consumption(self) -> None:
        mock_tools = MockTraverserMCPTools()
        traverser = DeterministicTriadTraverser(tools=mock_tools, beam_width=3, max_depth=3)

        seed_chunks = [
            {
                "chunk_id": "chk_nd100_a5_c3_pa",
                "path": "doc_nd100_2019.a5.c3.p_a",
                "doc_code": "100/2019/ND-CP",
                "norm_role": "SANCTION_PRINCIPAL",
                "raw_text": "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với ô tô vượt đèn đỏ",
                "rrf_score": 0.95,
            }
        ]

        # 1. Traverse using pre-retrieved seed_chunks
        paths = await traverser.traverse(
            query="ô tô vượt đèn đỏ phạt bao nhiêu",
            vehicle_category="CAR_PASSENGER",
            seed_chunks=seed_chunks,
        )

        assert len(paths) >= 1
        top_path = paths[0]
        # Should have expanded from seed to additional sanction and technical standard
        assert len(top_path.nodes) >= 2
        assert mock_tools.hybrid_search_calls == 0  # Did not call redundant hybrid_search!
        assert mock_tools.graph_traverse_calls >= 1

    @pytest.mark.asyncio
    async def test_traverser_cycle_and_self_loop_prevention(self) -> None:
        mock_tools = MockTraverserMCPTools()
        traverser = DeterministicTriadTraverser(tools=mock_tools, beam_width=2, max_depth=4)

        paths = await traverser.traverse(
            query="vượt đèn đỏ",
            seed_chunks=[
                {
                    "chunk_id": "chk_nd100_a5_c3_pa",
                    "path": "doc_nd100_2019.a5.c3.p_a",
                    "doc_code": "100/2019/ND-CP",
                    "norm_role": "SANCTION_PRINCIPAL",
                    "raw_text": "Vượt đèn đỏ",
                    "rrf_score": 0.90,
                }
            ],
        )

        for p in paths:
            node_ids = [n.node_id for n in p.nodes]
            # No duplicates in any path
            assert len(node_ids) == len(set(node_ids))

    # --------------------------------------------------------------------------
    # 2. ScopeOverrideEngine Precedence Lattice
    # --------------------------------------------------------------------------
    def test_precedence_ranks_ordering(self) -> None:
        engine = ScopeOverrideEngine()
        rank_police = engine.get_statutory_rank(SignalTier.POLICE_OFFICER)
        rank_light = engine.get_statutory_rank(SignalTier.TRAFFIC_LIGHT)
        rank_temp_sign = engine.get_statutory_rank(SignalTier.TRAFFIC_SIGN, Temporality.TEMPORARY)
        rank_perm_sign = engine.get_statutory_rank(SignalTier.TRAFFIC_SIGN, Temporality.PERMANENT)
        rank_marking = engine.get_statutory_rank(SignalTier.ROAD_MARKING)

        assert rank_police < rank_light < rank_temp_sign < rank_perm_sign < rank_marking
        assert rank_police == StatutoryPrecedenceRank.TRAFFIC_POLICE.value
        assert rank_temp_sign == StatutoryPrecedenceRank.ROAD_SIGN_TEMPORARY.value

    def test_emergency_vehicle_sub_tier_hierarchy(self) -> None:
        engine = ScopeOverrideEngine()
        # Fire > Police
        res1 = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.FIRE_FIGHTING, EmergencyVehicleTier.MILITARY_POLICE
        )
        assert res1["dominant_vehicle"] == "Vehicle A"
        assert res1["dominant_tier"] == "FIRE_FIGHTING"

        # Military > Ambulance
        res2 = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.MILITARY_POLICE, EmergencyVehicleTier.AMBULANCE
        )
        assert res2["dominant_vehicle"] == "Vehicle A"
        assert res2["dominant_tier"] == "MILITARY_POLICE"

        # Ambulance > Funeral
        res3 = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.AMBULANCE, EmergencyVehicleTier.FUNERAL_CORTEGE
        )
        assert res3["dominant_vehicle"] == "Vehicle A"
        assert res3["dominant_tier"] == "AMBULANCE"

    # --------------------------------------------------------------------------
    # 3. End-to-End Reasoning Pipeline
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_legal_reasoning_pipeline_turn(self) -> None:
        mock_tools = MockTraverserMCPTools()
        pipeline = LegalReasoningPipeline(tools=mock_tools)

        query = "Cảnh sát giao thông ra hiệu đi nhưng đèn đỏ thì tôi đi tiếp có bị phạt không?"
        result = await pipeline.execute_query(query)

        assert result["query"] == query
        assert isinstance(result["plan"], ExecutionPlanDAG)
        assert len(result["retrieved_matches"]) > 0
        assert len(result["traversal_paths"]) > 0
        assert result["override_ruling"] is not None
        assert result["chain_of_custody"] is not None

        coc = result["chain_of_custody"]
        assert len(coc.precedence_resolutions) >= 1
        assert coc.precedence_resolutions[0].dominant_authority == "POLICE_OFFICER"
        assert ChainOfCustodyVerifier.verify_hash_chain(coc, query) is True

    # --------------------------------------------------------------------------
    # 4. F-30, F-41, F-42 Feature Tests
    # --------------------------------------------------------------------------
    def test_traverser_repeals_edge_priority_weight(self) -> None:
        """F-30: Verifies that REPEALS edge type is assigned highest precedence (1.00)."""
        traverser = DeterministicTriadTraverser()
        assert "REPEALS" in traverser.EDGE_PRIORITIES
        assert traverser.EDGE_PRIORITIES["REPEALS"] == 1.00
        assert traverser._get_edge_priority("REPEALS") == 1.00

    def test_traverser_dense_cosine_similarity_scoring(self) -> None:
        """F-41: Verifies dense vector cosine similarity calculation and scoring in traverser."""
        traverser = DeterministicTriadTraverser()

        # Test exact vector similarity
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [1.0, 0.0, 0.0]
        sim_exact = traverser._cosine_similarity(vec_a, vec_b)
        assert sim_exact == pytest.approx(1.0)

        # Test orthogonal vector similarity
        vec_c = [0.0, 1.0, 0.0]
        sim_ortho = traverser._cosine_similarity(vec_a, vec_c)
        assert sim_ortho == pytest.approx(0.0)

        # Test _compute_semantic_similarity with explicit query and target vectors
        sim_score = traverser._compute_semantic_similarity(
            normalized_query="vuot den do",
            node_text="Khong chap hanh hieu lenh den tin hieu",
            vehicle_category="CAR_PASSENGER",
            metadata={"embedding_vector": [1.0, 0.0, 0.0]},
            query_vector=[1.0, 0.0, 0.0],
        )
        assert sim_score > 0.70

    def test_consolidated_diacritic_normalization_in_reasoning(self) -> None:
        """F-42: Verifies that planner and traverser adopt consolidated remove_vietnamese_diacritics."""
        from rag_eval.legal.reasoning.planner import QueryPlanner

        planner = QueryPlanner()
        norm_plan = planner._normalize_text("Xe Ô Tô Tải Chở Hàng")
        assert "xe o to tai cho hang" in norm_plan

        traverser = DeterministicTriadTraverser()
        norm_trav = traverser._normalize_vietnamese("Phạt tiền từ 800.000 đồng")
        assert "phat tien tu 800 000 dong" in norm_trav
