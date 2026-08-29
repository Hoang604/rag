"""Tier 3: Cross-Feature Combinations (Pairwise Coverage of Vehicles x Violations x Precedence)."""

from __future__ import annotations

import itertools

import pytest

from rag_eval.legal.reasoning.overrides import ScopeOverrideEngine
from rag_eval.legal.reasoning.planner import QueryPlanner
from rag_eval.legal.schemas import (
    LegalIntent,
    SignalTier,
    Temporality,
    TrafficSignalCommand,
    VehicleCategory,
    ViolationCategory,
)

VEHICLE_QUERY_KEYWORDS: dict[VehicleCategory, str] = {
    VehicleCategory.CAR_PASSENGER: "xe ô tô con",
    VehicleCategory.CAR_TRUCK: "xe tải",
    VehicleCategory.MOTORCYCLE: "xe máy",
    VehicleCategory.MOPED: "xe gắn máy",
    VehicleCategory.BICYCLE_PRIMITIVE: "xe đạp",
    VehicleCategory.PRIORITY_VEHICLE: "xe cứu thương",
}

VIOLATION_QUERY_KEYWORDS: dict[ViolationCategory, tuple[str, LegalIntent]] = {
    ViolationCategory.SIGNAL_COMPLIANCE: ("vượt đèn đỏ", LegalIntent.INTENT_PENALTY_LOOKUP),
    ViolationCategory.SPEED_DISTANCE: ("chạy quá tốc độ 15 km/h", LegalIntent.INTENT_PENALTY_LOOKUP),
    ViolationCategory.ALCOHOL_DRUGS: ("nồng độ cồn 0.55 mg/l", LegalIntent.INTENT_PENALTY_LOOKUP),
    ViolationCategory.LANE_DIRECTION: ("đi ngược chiều", LegalIntent.INTENT_PENALTY_LOOKUP),
}


class TestTier3CombinatorialMatrix:
    """Pairwise combinatorial coverage executing genuine production planning & overrides."""

    @pytest.mark.parametrize(
        ("vehicle_cat", "violation_cat"),
        list(
            itertools.product(
                [
                    VehicleCategory.CAR_PASSENGER,
                    VehicleCategory.CAR_TRUCK,
                    VehicleCategory.MOTORCYCLE,
                    VehicleCategory.MOPED,
                    VehicleCategory.BICYCLE_PRIMITIVE,
                    VehicleCategory.PRIORITY_VEHICLE,
                ],
                [
                    ViolationCategory.SIGNAL_COMPLIANCE,
                    ViolationCategory.SPEED_DISTANCE,
                    ViolationCategory.ALCOHOL_DRUGS,
                    ViolationCategory.LANE_DIRECTION,
                ],
            )
        ),
    )
    def test_vehicle_by_violation_matrix_coverage(
        self, vehicle_cat: VehicleCategory, violation_cat: ViolationCategory
    ) -> None:
        veh_str = VEHICLE_QUERY_KEYWORDS[vehicle_cat]
        viol_str, expected_intent = VIOLATION_QUERY_KEYWORDS[violation_cat]
        query = f"Người điều khiển {veh_str} {viol_str} phạt bao nhiêu tiền?"

        # Executes production QueryPlanner
        planner = QueryPlanner()
        plan = planner.plan(query)

        assert plan.primary_intent == expected_intent
        assert plan.extracted_entities.vehicle_category == vehicle_cat
        assert len(plan.sub_goals) >= 1

    @pytest.mark.parametrize(
        ("highest_tier", "subordinate_tier"),
        [
            (SignalTier.POLICE_OFFICER, SignalTier.TRAFFIC_LIGHT),
            (SignalTier.POLICE_OFFICER, SignalTier.TRAFFIC_SIGN),
            (SignalTier.POLICE_OFFICER, SignalTier.ROAD_MARKING),
            (SignalTier.TRAFFIC_LIGHT, SignalTier.TRAFFIC_SIGN),
            (SignalTier.TRAFFIC_LIGHT, SignalTier.ROAD_MARKING),
            (SignalTier.TRAFFIC_SIGN, SignalTier.ROAD_MARKING),
        ],
    )
    def test_signal_precedence_pairwise_dominance(
        self,
        highest_tier: SignalTier,
        subordinate_tier: SignalTier,
    ) -> None:
        engine = ScopeOverrideEngine()
        signals = [
            TrafficSignalCommand(
                source_type=highest_tier,
                temporality=Temporality.PERMANENT,
                command_directive="PROCEED",
                legal_citation="QCVN 41:2019 Điều 4",
            ),
            TrafficSignalCommand(
                source_type=subordinate_tier,
                temporality=Temporality.PERMANENT,
                command_directive="STOP",
                legal_citation="QCVN 41:2019 Điều 4",
            ),
        ]
        result = engine.resolve_signal_conflict(signals, driver_action="PROCEED")
        assert result.dominant_signal.source_type == highest_tier
        assert highest_tier.value < subordinate_tier.value
