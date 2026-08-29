"""Tier 2: Boundary & Corner Cases tests for Fine Limits and Penalty Boundaries."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag_eval.legal.schemas import FineBounds


class TestTier2FineBoundaries:
    """Boundary tests for statutory monetary penalties in Vietnamese Traffic Law."""

    def test_fine_bound_zero_fine_for_warning_sanctions(self) -> None:
        bounds = FineBounds(min_fine_vnd=0, max_fine_vnd=0)
        assert bounds.min_fine_vnd == 0
        assert bounds.max_fine_vnd == 0
        assert bounds.average_fine_vnd == 0

    def test_fine_bound_identical_min_and_max(self) -> None:
        bounds = FineBounds(min_fine_vnd=500000, max_fine_vnd=500000)
        assert bounds.average_fine_vnd == 500000

    def test_fine_bound_maximum_statutory_bracket_automobile_alcohol(self) -> None:
        # Decree 100 Article 5 Clause 10 Point a: 30m - 40m VND
        bounds = FineBounds(min_fine_vnd=30000000, max_fine_vnd=40000000)
        assert bounds.min_fine_vnd == 30000000
        assert bounds.max_fine_vnd == 40000000
        assert bounds.average_fine_vnd == 35000000

    def test_fine_bound_negative_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FineBounds(min_fine_vnd=-1)

    def test_fine_bound_inversion_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cannot exceed max_fine_vnd"):
            FineBounds(min_fine_vnd=1000000, max_fine_vnd=999999)

    def test_fine_bound_both_none_is_valid_for_behavioral_norms(self) -> None:
        bounds = FineBounds(min_fine_vnd=None, max_fine_vnd=None)
        assert bounds.min_fine_vnd is None
        assert bounds.max_fine_vnd is None
        assert bounds.average_fine_vnd is None
