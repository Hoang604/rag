from __future__ import annotations

from typing import TypedDict

from rag_eval.legal.mcp.server import LegalMCPServer
from rag_eval.legal.mcp.tools import LegalMCPTools, SearchResultItem, TraversalPathItem
from tests.legal.mocks.mock_db import MockDatabasePool


class LegalE2EQueryResult(TypedDict):
    query: str
    retrieved_matches: list[SearchResultItem]
    traversal_paths: list[TraversalPathItem]
    override_ruling: object
    synthesized_answer: str


class LegalE2ETestRunner:
    """Orchestrates end-to-end multi-hop legal queries against the production MCP stack."""

    def __init__(self, db_pool: MockDatabasePool | None = None) -> None:
        self.db = db_pool or MockDatabasePool()
        self.tools = LegalMCPTools(pool=self.db)
        self.mcp = LegalMCPServer(self.tools)

    async def execute_e2e_query(self, query: str) -> LegalE2EQueryResult:
        """Executes a full turn across MCP tools: Search -> Traverse."""
        search_res = await self.mcp.call_tool(
            "mcp_traffic_hybrid_search", {"query": query, "limit": 10}
        )
        search_result_dict = search_res.get("result", {})
        retrieved_matches: list[SearchResultItem] = (
            search_result_dict.get("results", [])
            if isinstance(search_result_dict, dict)
            else []
        )

        # Traverse supplemental edges if top match exists
        traversal_results: list[TraversalPathItem] = []
        if retrieved_matches:
            top_chunk_id = str(retrieved_matches[0].get("chunk_id", ""))
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
            traverse_result_dict = traverse_res.get("result", {})
            traversal_results = (
                traverse_result_dict.get("traversal_paths", [])
                if isinstance(traverse_result_dict, dict)
                else []
            )

        # Dynamically concatenate verbatim statutory matches
        advisory_parts: list[str] = []
        for m in retrieved_matches:
            txt = m.get("contextualized_text") or m.get("raw_text") or m.get("verbatim_text")
            if txt:
                advisory_parts.append(str(txt))

        advisory_text = (
            "\n".join(advisory_parts)
            if advisory_parts
            else "Không tìm thấy căn cứ pháp lý quy định hành vi nêu trên."
        )

        return {
            "query": query,
            "retrieved_matches": retrieved_matches,
            "traversal_paths": traversal_results,
            "override_ruling": None,
            "synthesized_answer": advisory_text,
        }
