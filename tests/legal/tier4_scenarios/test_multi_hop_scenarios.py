"""Tier 4: Real-World Multi-Hop Application Scenarios.

Covers the 6 statutory multi-hop reasoning scenarios:
1. Speeding in non-divided urban corridor (Circular 31 -> Law -> Decree 100/123 -> Decree 168 point deduction).
2. Red light violation vs CSGT manual override (Statutory signal precedence hierarchy).
3. Emergency vehicle (Ambulance on duty) priority privilege & exemption evaluation.
4. Alcohol concentration tier evaluation & mandatory supplementary impoundment/suspension.
5. Commercial truck overloading & bridge weight restriction.
6. Motorbike driving against traffic on one-way street (Sign P.102).
"""

from __future__ import annotations

import pytest

from rag_eval.legal.reasoning.overrides import EmergencyVehicleTier, ScopeOverrideEngine
from rag_eval.legal.schemas import (
    SignalTier,
    Temporality,
    TrafficSignalCommand,
    VehicleCategory,
)
from tests.legal.runners import LegalE2ETestRunner


@pytest.mark.asyncio
class TestTier4MultiHopScenarios:
    """Exhaustive end-to-end integration tests for 6 authoritative real-world scenarios."""

    async def test_scenario_1_speeding_in_non_divided_urban_corridor(self) -> None:
        """Scenario 1: Car at 68 km/h in urban 2-way road without median (Limit 50 -> delta 18 km/h)."""
        runner = LegalE2ETestRunner()
        query = "Xe ô tô con chạy 68 km/h trên đường đôi không có dải phân cách khu đông dân cư phạt bao nhiêu?"
        result = await runner.execute_e2e_query(query)

        assert len(result["retrieved_matches"]) > 0
        top_match = result["retrieved_matches"][0]
        assert top_match["min_fine_vnd"] == 4000000
        assert top_match["max_fine_vnd"] == 6000000
        assert top_match["additional_sanctions"]["license_suspension_months_min"] == 1
        assert top_match["additional_sanctions"]["license_suspension_months_max"] == 3
        assert top_match["additional_sanctions"]["demerit_points"] == 2
        assert result["chain_of_custody"].anti_hallucination_audit.is_grounded is True

    async def test_scenario_2_red_light_violation_vs_csgt_override(self) -> None:
        """Scenario 2: Red traffic light vs CSGT manual forward command."""
        engine = ScopeOverrideEngine()
        signals = [
            TrafficSignalCommand(
                source_type=SignalTier.POLICE_OFFICER,
                temporality=Temporality.PERMANENT,
                command_directive="PROCEED",
                legal_citation="QCVN 41:2019/BGTVT Điều 4 Khoản 4.1",
            ),
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_LIGHT,
                temporality=Temporality.PERMANENT,
                command_directive="STOP",
                legal_citation="QCVN 41:2019/BGTVT Điều 4 Khoản 4.2",
            ),
        ]
        result = engine.resolve_signal_conflict(signals, driver_action="PROCEED")
        assert result.dominant_signal.source_type == SignalTier.POLICE_OFFICER
        assert result.is_driver_action_legal is True

    async def test_scenario_3_ambulance_on_duty_emergency_privilege(self) -> None:
        """Scenario 3: Ambulance on emergency duty proceeding through red light at 85 km/h."""
        engine = ScopeOverrideEngine()
        res = engine.evaluate_emergency_privilege(
            vehicle_type=VehicleCategory.PRIORITY_VEHICLE,
            is_on_duty=True,
            has_siren_beacon=True,
            emergency_tier=EmergencyVehicleTier.AMBULANCE,
        )
        assert res["is_exempt"] is True
        assert "Điều 22 Luật GTĐB 2008" in res["legal_basis"][0]

    async def test_scenario_4_alcohol_concentration_tier_evaluation(self) -> None:
        """Scenario 4: Automobile driver at 0.55 mg/L breath alcohol."""
        runner = LegalE2ETestRunner()
        query = "Lái xe ô tô có nồng độ cồn 0.55 mg/l khí thở phạt bao nhiêu?"
        result = await runner.execute_e2e_query(query)

        assert len(result["retrieved_matches"]) > 0
        top_match = result["retrieved_matches"][0]
        assert top_match["min_fine_vnd"] == 30000000
        assert top_match["max_fine_vnd"] == 40000000
        assert top_match["additional_sanctions"]["license_suspension_months_min"] == 22
        assert top_match["additional_sanctions"]["license_suspension_months_max"] == 24
        assert top_match["additional_sanctions"]["vehicle_impoundment_days"] == 7
        assert top_match["additional_sanctions"]["demerit_points"] == 12

    async def test_scenario_5_commercial_truck_overloading(self) -> None:
        """Scenario 5: Commercial truck carrying payload 35% over certified capacity (Bracket 20-50%)."""
        runner = LegalE2ETestRunner()
        query = "Xe ô tô tải chở hàng vượt tải trọng 35% bị phạt thế nào?"
        result = await runner.execute_e2e_query(query)

        assert len(result["retrieved_matches"]) > 0
        top_match = result["retrieved_matches"][0]
        assert top_match["min_fine_vnd"] == 6000000
        assert top_match["max_fine_vnd"] == 8000000
        assert top_match["additional_sanctions"]["license_suspension_months_min"] == 1
        assert top_match["additional_sanctions"]["license_suspension_months_max"] == 3
        assert top_match["additional_sanctions"]["demerit_points"] == 3

    async def test_scenario_6_motorbike_against_traffic_on_one_way_street(self) -> None:
        """Scenario 6: Motorcycle driving opposite direction on one-way road (Sign P.102)."""
        runner = LegalE2ETestRunner()
        query = "Xe máy đi ngược chiều trên đường có biển P.102 cấm đi ngược chiều phạt bao nhiêu?"
        result = await runner.execute_e2e_query(query)

        assert len(result["retrieved_matches"]) > 0
        top_match = result["retrieved_matches"][0]
        assert top_match["min_fine_vnd"] == 1000000
        assert top_match["max_fine_vnd"] == 2000000
        assert top_match["additional_sanctions"]["license_suspension_months_min"] == 2
        assert top_match["additional_sanctions"]["license_suspension_months_max"] == 4
        assert top_match["additional_sanctions"]["demerit_points"] == 3
        assert result["chain_of_custody"].anti_hallucination_audit.is_grounded is True
