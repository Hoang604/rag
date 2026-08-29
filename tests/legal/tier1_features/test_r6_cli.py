"""Tier 1: Feature Coverage tests for Requirement 6 (R6) - CLI Commands & QA Integration."""

from __future__ import annotations

import pytest

from tests.legal.runners import LegalE2ETestRunner


@pytest.mark.asyncio
class TestR6CLIAndQA:
    """Tests CLI execution schemas, legal migrations, ingestion, server, and end-to-end querying."""

    async def test_legal_e2e_runner_executes_query_successfully(self) -> None:
        runner = LegalE2ETestRunner()
        result = await runner.execute_e2e_query("Vượt đèn đỏ xe ô tô phạt bao nhiêu?")
        assert result["query"] == "Vượt đèn đỏ xe ô tô phạt bao nhiêu?"
        assert result["plan"].primary_intent.value == "INTENT_PENALTY_LOOKUP"
        assert len(result["retrieved_matches"]) > 0
        assert result["chain_of_custody"].anti_hallucination_audit.is_grounded is True

    async def test_legal_e2e_runner_traversal_paths_populated(self) -> None:
        runner = LegalE2ETestRunner()
        result = await runner.execute_e2e_query("xe máy đi ngược chiều đường một chiều")
        assert len(result["retrieved_matches"]) > 0
        top_match = result["retrieved_matches"][0]
        assert top_match["min_fine_vnd"] == 1000000
        assert top_match["max_fine_vnd"] == 2000000

    async def test_chain_of_custody_audit_pass(self) -> None:
        runner = LegalE2ETestRunner()
        result = await runner.execute_e2e_query("ô tô chạy quá tốc độ 15km/h")
        coc = result["chain_of_custody"]
        assert coc.anti_hallucination_audit.citation_coverage_pct == 100.0
