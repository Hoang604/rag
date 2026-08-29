"""Tier 2: Boundary & Corner Cases tests for Alcohol Concentrations executing production schemas."""

from __future__ import annotations

import pytest

from rag_eval.legal.schemas import ExtractedEntities, ViolationType


class TestTier2AlcoholConcentrations:
    """Boundary tests for 3-tier alcohol concentration brackets in blood and breath."""

    @pytest.mark.parametrize(
        ("breath_mg_l", "blood_mg_100ml", "expected_violation"),
        [
            # Zero alcohol -> No violation
            (0.0, None, None),
            (None, 0.0, None),
            # Tier 1: <= 0.25 mg/L or <= 50 mg/100mL
            (0.01, None, ViolationType.ALC_BRACKET_1),
            (0.25, None, ViolationType.ALC_BRACKET_1),
            (None, 50.0, ViolationType.ALC_BRACKET_1),
            # Tier 2: 0.25 < breath <= 0.40 or 50 < blood <= 80
            (0.251, None, ViolationType.ALC_BRACKET_2),
            (0.40, None, ViolationType.ALC_BRACKET_2),
            (None, 80.0, ViolationType.ALC_BRACKET_2),
            # Tier 3: > 0.40 mg/L or > 80 mg/100mL
            (0.401, None, ViolationType.ALC_BRACKET_3),
            (0.85, None, ViolationType.ALC_BRACKET_3),
            (None, 120.0, ViolationType.ALC_BRACKET_3),
        ],
    )
    def test_alcohol_tier_exact_boundaries(
        self,
        breath_mg_l: float | None,
        blood_mg_100ml: float | None,
        expected_violation: ViolationType | None,
    ) -> None:
        entities = ExtractedEntities(
            alcohol_breath_mg_l=breath_mg_l,
            alcohol_blood_mg_100ml=blood_mg_100ml,
        )
        actual_violation = entities.classify_alcohol_violation()
        assert actual_violation == expected_violation
