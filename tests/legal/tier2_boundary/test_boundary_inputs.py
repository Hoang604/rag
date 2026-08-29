"""Tier 2: Boundary & Corner Cases tests for Query Extremes and Input Normalization."""

from __future__ import annotations

from rag_eval.legal.reasoning.planner import QueryPlanner
from rag_eval.legal.schemas import LegalIntent, VehicleCategory


class TestTier2InputExtremes:
    """Boundary tests for empty inputs, whitespace, long tokens, and unaccented Vietnamese."""

    def test_empty_string_query_handling(self) -> None:
        planner = QueryPlanner()
        plan = planner.plan("")
        assert plan.query_id is not None
        assert len(plan.sub_goals) >= 1
        assert plan.primary_intent == LegalIntent.INTENT_PENALTY_LOOKUP

    def test_whitespace_only_query_handling(self) -> None:
        planner = QueryPlanner()
        plan = planner.plan("   \n\t   ")
        assert plan.query_id is not None
        assert len(plan.sub_goals) >= 1

    def test_extreme_long_query_token_handling(self) -> None:
        planner = QueryPlanner()
        long_query = "Tôi điều khiển xe ô tô chạy quá tốc độ " + "rất nhanh " * 200
        plan = planner.plan(long_query)
        assert plan.query_id is not None
        assert plan.extracted_entities.vehicle_category == VehicleCategory.CAR_PASSENGER

    def test_unaccented_vietnamese_query_normalization(self) -> None:
        planner = QueryPlanner()
        plan = planner.plan("xe o to chay vuot den do phat bao nhieu")
        assert plan.extracted_entities.vehicle_category == VehicleCategory.CAR_PASSENGER
        assert plan.primary_intent == LegalIntent.INTENT_PENALTY_LOOKUP
