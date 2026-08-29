"""Top-level test entrypoint for Tier 2 Boundary & Corner Cases test suite."""

from __future__ import annotations

from tests.legal.tier2_boundary.test_boundary_alcohol import (
    TestTier2AlcoholConcentrations,
)
from tests.legal.tier2_boundary.test_boundary_fines import TestTier2FineBoundaries
from tests.legal.tier2_boundary.test_boundary_inputs import TestTier2InputExtremes
from tests.legal.tier2_boundary.test_boundary_speed import TestTier2SpeedDeltas
from tests.legal.tier2_boundary.test_boundary_temporal import (
    TestTier2TemporalBoundaries,
)
from tests.legal.tier2_boundary.test_boundary_weights import TestTier2VehicleWeights

__all__ = [
    "TestTier2AlcoholConcentrations",
    "TestTier2FineBoundaries",
    "TestTier2InputExtremes",
    "TestTier2SpeedDeltas",
    "TestTier2TemporalBoundaries",
    "TestTier2VehicleWeights",
]
