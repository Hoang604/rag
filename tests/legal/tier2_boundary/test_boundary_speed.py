"""Tier 2: Boundary & Corner Cases tests for Speed Deltas executing production schemas."""

from __future__ import annotations

import pytest

from rag_eval.legal.schemas import ExtractedEntities, ViolationType


class TestTier2SpeedDeltas:
    """Boundary tests for statutory speeding brackets executing production schemas."""

    @pytest.mark.parametrize(
        ("limit", "recorded", "expected_violation", "expected_delta"),
        [
            # Under 5 km/h tolerance threshold
            (50.0, 50.0, None, 0.0),
            (54.9, 50.0, None, 0.0),  # Under limit
            (50.0, 54.9, None, 4.9),
            # Exact 5 km/h boundary -> Bracket 5 - 10 km/h
            (50.0, 55.0, ViolationType.SPEED_OVER_5_10, 5.0),
            (50.0, 59.99, ViolationType.SPEED_OVER_5_10, 9.99),
            # Exact 10 km/h boundary -> Bracket 10 - 20 km/h
            (50.0, 60.0, ViolationType.SPEED_OVER_10_20, 10.0),
            (50.0, 69.99, ViolationType.SPEED_OVER_10_20, 19.99),
            # Over 20 km/h boundary -> Bracket 20 - 35 km/h
            (50.0, 70.0, ViolationType.SPEED_OVER_20_35, 20.0),
            (50.0, 84.99, ViolationType.SPEED_OVER_20_35, 34.99),
            # Over 35 km/h boundary -> Bracket >= 35 km/h
            (50.0, 85.0, ViolationType.SPEED_OVER_35_PLUS, 35.0),
            (50.0, 120.0, ViolationType.SPEED_OVER_35_PLUS, 70.0),
        ],
    )
    def test_speed_delta_boundary_classification(
        self,
        limit: float,
        recorded: float,
        expected_violation: ViolationType | None,
        expected_delta: float,
    ) -> None:
        entities = ExtractedEntities(
            recorded_speed_kmh=recorded,
            speed_limit_kmh=limit,
        )
        assert round(entities.calculate_speed_delta() or 0.0, 2) == expected_delta
        assert entities.classify_speed_violation() == expected_violation
