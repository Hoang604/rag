"""Top-level test entrypoint for Tier 1 Feature Coverage test suite."""

from __future__ import annotations

from tests.legal.tier1_features.test_r1_schemas import (
    TestR1DomainTaxonomies,
    TestR1ExtractionModels,
    TestR1ReasoningModels,
)
from tests.legal.tier1_features.test_r2_database import TestR2DatabaseSubsystem
from tests.legal.tier1_features.test_r3_ingestion import TestR3CPHCIngestion
from tests.legal.tier1_features.test_r4_mcp_tools import TestR4MCPServer
from tests.legal.tier1_features.test_r5_reasoning import TestR5ReasoningEngine
from tests.legal.tier1_features.test_r6_cli import TestR6CLIAndQA

__all__ = [
    "TestR1DomainTaxonomies",
    "TestR1ExtractionModels",
    "TestR1ReasoningModels",
    "TestR2DatabaseSubsystem",
    "TestR3CPHCIngestion",
    "TestR4MCPServer",
    "TestR5ReasoningEngine",
    "TestR6CLIAndQA",
]
