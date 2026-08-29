"""Empirical Adversarial Stress Test Suite for Requirement 5 (R5).

Challenger R5-2: Stress-testing ScopeOverrideEngine, DeterministicTriadTraverser, and AST Citation Grounding.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.reasoning.chain_of_custody import (
    ASTCitationValidator,
)
from rag_eval.legal.reasoning.overrides import (
    EmergencyVehicleTier,
    ScopeOverrideEngine,
    StatutoryPrecedenceRank,
)
from rag_eval.legal.reasoning.traverser import (
    DeterministicTriadTraverser,
)
from rag_eval.legal.schemas import (
    SignalTier,
    Temporality,
    TrafficSignalCommand,
)


class AdversarialCyclicMCPTools(LegalMCPTools):
    """Adversarial mock MCP tools with dense cyclic graphs, self-loops, and back-edges."""

    def __init__(self, latency: float = 0.02) -> None:
        super().__init__()
        self.latency = latency
        self.traverse_call_count = 0

    async def graph_traverse(
        self,
        start_chunk_id: str,
        relation_types: list[str] | None = None,
        direction: str = "BOTH",
        max_depth: int = 2,
    ) -> dict[str, Any]:
        self.traverse_call_count += 1
        if self.latency > 0:
            await asyncio.sleep(self.latency)

        # Dense cyclic adjacency topology:
        # N1 -> [N1 (self-loop), N2, N3]
        # N2 -> [N1 (back-edge), N3, N4]
        # N3 -> [N1, N2, N4]
        # N4 -> [N1, N2, N3, N5]
        # N5 -> [N1, N5 (self-loop)]
        adjacency: dict[str, list[str]] = {
            "N1": ["N1", "N2", "N3"],
            "N2": ["N1", "N3", "N4"],
            "N3": ["N1", "N2", "N4"],
            "N4": ["N1", "N2", "N3", "N5"],
            "N5": ["N1", "N5"],
        }
        neighbors = adjacency.get(start_chunk_id, ["N1"])
        paths: list[dict[str, Any]] = []
        for n in neighbors:
            role = (
                "SANCTION_SUPPLEMENTARY"
                if n == "N2"
                else ("HYPOTHESIS_CONDITION" if n == "N3" else "PRESCRIPTION_DUTY")
            )
            rel = "HAS_ADDITIONAL_SANCTION" if n == "N2" else "REFERENCES_TECHNICAL_STANDARD"
            paths.append(
                {
                    "target_chunk_id": n,
                    "target_path": f"doc_test.{n.lower()}",
                    "target_doc_code": "100/2019/ND-CP",
                    "target_norm_role": role,
                    "target_raw_text": f"Statutory normative content for node {n}",
                    "relation_type": rel,
                    "confidence_score": 0.95,
                }
            )
        return {
            "status": "success",
            "start_chunk_id": start_chunk_id,
            "traversal_paths": paths,
        }


class TestAdversarialScopeOverrides:
    """Adversarial stress-testing of ScopeOverrideEngine precedence hierarchy."""

    def test_police_hand_signal_dominates_all_emergency_vehicles(self) -> None:
        engine = ScopeOverrideEngine()
        rank_police = engine.get_statutory_rank(SignalTier.POLICE_OFFICER)
        rank_fire = EmergencyVehicleTier.FIRE_FIGHTING.value
        rank_mil = EmergencyVehicleTier.MILITARY_POLICE.value
        rank_amb = EmergencyVehicleTier.AMBULANCE.value
        rank_dike = EmergencyVehicleTier.DIKE_DISASTER_RELIEF.value
        rank_funeral = EmergencyVehicleTier.FUNERAL_CORTEGE.value
        rank_generic = StatutoryPrecedenceRank.EMERGENCY_VEHICLE_GENERIC.value

        assert rank_police == 1.0
        assert rank_fire == 1.1
        assert rank_mil == 1.2
        assert rank_amb == 1.3
        assert rank_dike == 1.4
        assert rank_funeral == 1.5
        assert rank_generic == 1.5

        # Strict inequality
        assert rank_police < rank_fire < rank_mil < rank_amb < rank_dike < rank_funeral
        assert rank_police < rank_generic

        # Signal Conflict with Police Officer
        signals = [
            TrafficSignalCommand(
                source_type=SignalTier.POLICE_OFFICER,
                temporality=Temporality.PERMANENT,
                command_directive="STOP",
                legal_citation="QCVN 41:2019 Điều 4.1",
            ),
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_LIGHT,
                temporality=Temporality.PERMANENT,
                command_directive="PROCEED",
                legal_citation="QCVN 41:2019 Điều 4.2",
            ),
        ]
        res = engine.resolve_signal_conflict(signals, driver_action="STOP")
        assert res.dominant_signal.source_type == SignalTier.POLICE_OFFICER
        assert res.is_driver_action_legal is True

    def test_emergency_vehicle_conflict_fire_truck_dominates_ambulance(self) -> None:
        engine = ScopeOverrideEngine()

        # Fire Fighting (1.1) vs Ambulance (1.3)
        res_a_b = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.FIRE_FIGHTING, EmergencyVehicleTier.AMBULANCE
        )
        assert res_a_b["dominant_vehicle"] == "Vehicle A"
        assert res_a_b["dominant_tier"] == "FIRE_FIGHTING"
        assert res_a_b["dominant_rank"] == 1.1
        assert res_a_b["subordinate_tier"] == "AMBULANCE"
        assert res_a_b["subordinate_rank"] == 1.3

        # Commutative order test: Ambulance (1.3) vs Fire Fighting (1.1)
        res_b_a = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.AMBULANCE, EmergencyVehicleTier.FIRE_FIGHTING
        )
        assert res_b_a["dominant_vehicle"] == "Vehicle B"
        assert res_b_a["dominant_tier"] == "FIRE_FIGHTING"
        assert res_b_a["dominant_rank"] == 1.1

    def test_temporary_sign_dominates_permanent_sign(self) -> None:
        engine = ScopeOverrideEngine()
        signals = [
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_SIGN,
                temporality=Temporality.TEMPORARY,
                command_directive="SPEED_LIMIT",
                speed_cap_kmh=30.0,
                legal_citation="QCVN 41:2019 Điều 4.3 (Biển tạm 30 km/h)",
            ),
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_SIGN,
                temporality=Temporality.PERMANENT,
                command_directive="SPEED_LIMIT",
                speed_cap_kmh=60.0,
                legal_citation="QCVN 41:2019 Điều 4.4 (Biển cố định 60 km/h)",
            ),
            TrafficSignalCommand(
                source_type=SignalTier.ROAD_MARKING,
                temporality=Temporality.PERMANENT,
                command_directive="PROCEED",
                legal_citation="QCVN 41:2019 Điều 4.4",
            ),
        ]

        # Driving at 45 km/h: Below permanent 60 km/h, but exceeds temporary 30 km/h -> ILLEGAL
        res_illegal = engine.resolve_signal_conflict(signals, driver_speed_kmh=45.0)
        assert res_illegal.dominant_signal.temporality == Temporality.TEMPORARY
        assert res_illegal.dominant_signal.speed_cap_kmh == 30.0
        assert res_illegal.is_driver_action_legal is False

        # Driving at 25 km/h: Below temporary 30 km/h -> LEGAL
        res_legal = engine.resolve_signal_conflict(signals, driver_speed_kmh=25.0)
        assert res_legal.dominant_signal.temporality == Temporality.TEMPORARY
        assert res_legal.is_driver_action_legal is True

    def test_complete_six_tier_inequality_ordering(self) -> None:
        engine = ScopeOverrideEngine()
        r1 = engine.get_statutory_rank(SignalTier.POLICE_OFFICER)
        r_fire = EmergencyVehicleTier.FIRE_FIGHTING.value
        r_amb = EmergencyVehicleTier.AMBULANCE.value
        r_gen = StatutoryPrecedenceRank.EMERGENCY_VEHICLE_GENERIC.value
        r2 = engine.get_statutory_rank(SignalTier.TRAFFIC_LIGHT)
        r3_temp = engine.get_statutory_rank(SignalTier.TRAFFIC_SIGN, Temporality.TEMPORARY)
        r3_perm = engine.get_statutory_rank(SignalTier.TRAFFIC_SIGN, Temporality.PERMANENT)
        r4 = engine.get_statutory_rank(SignalTier.ROAD_MARKING)
        r5 = StatutoryPrecedenceRank.GENERAL_RULE.value

        assert r1 < r_fire < r_amb < r_gen < r2 < r3_temp < r3_perm < r4 < r5


class TestAdversarialTraverser:
    """Adversarial stress-testing of DeterministicTriadTraverser."""

    @pytest.mark.asyncio
    async def test_traverser_dense_cyclic_graph_cycle_prevention(self) -> None:
        tools = AdversarialCyclicMCPTools(latency=0.0)
        traverser = DeterministicTriadTraverser(tools=tools, beam_width=3, max_depth=6)

        seed_chunks = [
            {
                "chunk_id": "N1",
                "path": "doc_test.n1",
                "doc_code": "100/2019/ND-CP",
                "norm_role": "SANCTION_PRINCIPAL",
                "raw_text": "Root seed node N1",
                "rrf_score": 0.99,
            }
        ]

        paths = await traverser.traverse(
            query="test cyclic resilience",
            seed_chunks=seed_chunks,
        )

        assert len(paths) > 0
        for p in paths:
            node_ids = [n.node_id for n in p.nodes]
            hierarchy_paths = [n.hierarchy_path for n in p.nodes]
            # No repeated node_id in any single path
            assert len(node_ids) == len(set(node_ids)), f"Cycle detected in node sequence: {node_ids}"
            # No repeated hierarchy_path in any single path
            assert len(hierarchy_paths) == len(set(hierarchy_paths)), f"Duplicate path: {hierarchy_paths}"
            # Path length strictly bounded by max_depth + 1
            assert len(p.nodes) <= traverser.max_depth + 1

    @pytest.mark.asyncio
    async def test_traverser_parallel_expansion_concurrency(self) -> None:
        latency = 0.04
        tools = AdversarialCyclicMCPTools(latency=latency)
        traverser = DeterministicTriadTraverser(tools=tools, beam_width=3, max_depth=3)

        seed_chunks = [
            {
                "chunk_id": "N1",
                "path": "doc_test.n1",
                "doc_code": "100/2019/ND-CP",
                "norm_role": "SANCTION_PRINCIPAL",
                "raw_text": "Root seed node N1",
                "rrf_score": 0.99,
            }
        ]

        t0 = time.perf_counter()
        paths = await traverser.traverse(
            query="test parallel performance",
            seed_chunks=seed_chunks,
        )
        elapsed = time.perf_counter() - t0

        assert len(paths) > 0
        # If sequential: depth 1 had 1 call (0.04s), depth 2 had 3 calls (3 * 0.04s = 0.12s), depth 3 had 3 calls (0.12s) -> Total ~ 0.28s
        # With asyncio.gather: depth 1 (0.04s) + depth 2 (0.04s) + depth 3 (0.04s) -> Total ~ 0.12s - 0.16s
        assert elapsed < 0.25, f"Parallel fan-out too slow ({elapsed:.4f}s), sequential bottleneck detected!"


class TestAdversarialASTCitationGrounding:
    """Adversarial stress-testing of ASTCitationValidator and ChainOfCustody."""

    def test_validator_rejects_subtle_fabricated_articles(self) -> None:
        validator = ASTCitationValidator()
        retrieved_chunks: list[dict[str, Any]] = [
            {
                "chunk_id": "chk_nd100_a5_c3_pa",
                "doc_code": "100/2019/ND-CP",
                "hierarchy_path": "doc_nd100_2019.a5.c3.p_a",
                "raw_text": "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện hành vi vi phạm: Không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
            }
        ]

        # Case 1: Fabricated Article 6 instead of Article 5
        advisory_fake_art = "Căn cứ theo Điều 6 Khoản 3 Điểm a Nghị định 100/2019/NĐ-CP phạt tiền 800.000đ."
        audit_1 = validator.validate(advisory_fake_art, retrieved_chunks)
        assert audit_1.is_grounded is False
        assert len(audit_1.unmatched_citations) >= 1
        assert audit_1.hallucination_score > 0.0

        # Case 2: Fabricated Clause 9 instead of Clause 3
        advisory_fake_clause = "Căn cứ theo Điều 5 Khoản 9 Điểm a Nghị định 100/2019/NĐ-CP."
        audit_2 = validator.validate(advisory_fake_clause, retrieved_chunks)
        assert audit_2.is_grounded is False
        assert len(audit_2.unmatched_citations) >= 1

        # Case 3: Grounded citation passes with 100% score
        advisory_valid = "Căn cứ theo Điều 5 Khoản 3 Điểm a Nghị định 100/2019/NĐ-CP phạt tiền từ 800.000 đồng đến 1.000.000 đồng."
        audit_valid = validator.validate(advisory_valid, retrieved_chunks)
        assert audit_valid.is_grounded is True
        assert audit_valid.citation_coverage_pct == 100.0
        assert audit_valid.hallucination_score == 0.0
