"""Unified top-level E2E integration test suite for Vietnamese Traffic Law Agentic RAG."""

from __future__ import annotations

from tests.test_legal_tier1 import (
    TestR1DomainTaxonomies,
    TestR1ExtractionModels,
    TestR1ReasoningModels,
    TestR2DatabaseSubsystem,
    TestR3CPHCIngestion,
    TestR4MCPServer,
    TestR5ReasoningEngine,
    TestR6CLIAndQA,
)
from tests.test_legal_tier2 import (
    TestTier2AlcoholConcentrations,
    TestTier2FineBoundaries,
    TestTier2InputExtremes,
    TestTier2SpeedDeltas,
    TestTier2TemporalBoundaries,
    TestTier2VehicleWeights,
)
from tests.test_legal_tier3 import TestTier3CombinatorialMatrix
from tests.test_legal_tier4 import TestTier4MultiHopScenarios

__all__ = [
    "TestR1DomainTaxonomies",
    "TestR1ExtractionModels",
    "TestR1ReasoningModels",
    "TestR2DatabaseSubsystem",
    "TestR3CPHCIngestion",
    "TestR4MCPServer",
    "TestR5ReasoningEngine",
    "TestR6CLIAndQA",
    "TestTier2AlcoholConcentrations",
    "TestTier2FineBoundaries",
    "TestTier2InputExtremes",
    "TestTier2SpeedDeltas",
    "TestTier2TemporalBoundaries",
    "TestTier2VehicleWeights",
    "TestTier3CombinatorialMatrix",
    "TestTier4MultiHopScenarios",
]
