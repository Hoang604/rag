"""Integration test runner orchestrating production MCP and Reasoning stacks with MockDatabasePool."""

from __future__ import annotations

from typing import Any

from rag_eval.legal.mcp.server import LegalMCPServer
from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.reasoning.chain_of_custody import ChainOfCustodyGenerator
from rag_eval.legal.reasoning.overrides import ScopeOverrideEngine
from rag_eval.legal.reasoning.planner import QueryPlanner
from rag_eval.legal.schemas import ChainOfCustodyPlanSummary
from tests.legal.mocks.mock_db import MockDatabasePool


class LegalE2ETestRunner:
    """Orchestrates end-to-end multi-hop legal reasoning queries against the production MCP stack."""

    def __init__(self, db_pool: MockDatabasePool | None = None) -> None:
        self.db = db_pool or MockDatabasePool()
        self.tools = LegalMCPTools(pool=self.db)
        self.mcp = LegalMCPServer(self.tools)
        self.planner = QueryPlanner()
        self.override_engine = ScopeOverrideEngine()
        self.coc_generator = ChainOfCustodyGenerator()

    async def execute_e2e_query(self, query: str) -> dict[str, Any]:
        """Executes a full E2E pipeline turn: Plan -> Search -> Traverse -> Override -> CoC."""
        plan = self.planner.plan(query)

        search_tool_args = plan.sub_goals[0].tool_arguments
        search_res = await self.mcp.call_tool(
            "mcp_traffic_hybrid_search", search_tool_args
        )
        retrieved_matches = search_res.get("result", {}).get("results", [])

        # Traverse supplemental edges if top match exists
        traversal_results: list[dict[str, Any]] = []
        if retrieved_matches:
            top_chunk_id = retrieved_matches[0]["chunk_id"]
            traverse_res = await self.mcp.call_tool(
                "mcp_traffic_graph_traverse",
                {
                    "start_chunk_id": top_chunk_id,
                    "relation_types": [
                        "HAS_ADDITIONAL_SANCTION",
                        "REFERENCES_TECHNICAL_STANDARD",
                    ],
                    "max_depth": 2,
                },
            )
            traversal_results = traverse_res.get("result", {}).get(
                "traversal_paths", []
            )

        # Generate advisory text summary
        advisory_text = (
            retrieved_matches[0].get("contextualized_text", "")
            if retrieved_matches
            else "Không tìm thấy căn cứ pháp lý phù hợp."
        )

        # Synthesize cryptographic CoC
        plan_summary = ChainOfCustodyPlanSummary(
            primary_intent=plan.primary_intent,
            total_subgoals=len(plan.sub_goals),
            execution_path=[g.goal_id for g in plan.sub_goals],
        )
        coc = self.coc_generator.generate(
            query=query,
            retrieved_chunks=retrieved_matches,
            advisory_text=advisory_text,
            plan_summary=plan_summary,
        )

        return {
            "query": query,
            "plan": plan,
            "retrieved_matches": retrieved_matches,
            "traversal_paths": traversal_results,
            "chain_of_custody": coc,
        }
