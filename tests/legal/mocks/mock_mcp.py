"""Mock MCP JSON-RPC 2.0 Client & Server implementing the 7 specialized tools."""

from __future__ import annotations

import datetime
from typing import Any

from tests.legal.mocks.mock_db import MockDatabasePool


class MockMCPServer:
    """Mock MCP JSON-RPC 2.0 Server handling all 7 specialized domain tools."""

    def __init__(self, db_pool: MockDatabasePool | None = None) -> None:
        self.db = db_pool or MockDatabasePool()

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch MCP tool execution with standardized error handling and schemas."""
        handler = getattr(self, f"handle_{tool_name}", None)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Method '{tool_name}' not found",
                },
            }
        try:
            result = await handler(arguments)
            return {"jsonrpc": "2.0", "result": result}
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            OSError,
        ) as err:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000,
                    "message": f"Internal execution error: {err}",
                },
            }

    async def handle_mcp_traffic_corpus_validate(
        self, args: dict[str, Any]
    ) -> dict[str, Any]:
        doc_id = args.get("document_id", "doc_nd100")
        return {
            "status": "success",
            "document_id": doc_id,
            "doc_code": "100/2019/ND-CP",
            "is_valid": True,
            "total_chunks_scanned": len(self.db.chunks),
            "total_edges_scanned": len(self.db.graph_edges),
            "summary": "Corpus validation successful: Zero dangling sub-points, all ltree paths intact.",
            "anomalies": [],
            "validation_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }

    async def handle_mcp_traffic_hybrid_search(
        self, args: dict[str, Any]
    ) -> dict[str, Any]:
        query = args.get("query", "")
        veh = (
            args.get("vehicle_types", [None])[0] if args.get("vehicle_types") else None
        )
        limit = args.get("limit", 10)

        results = await self.db.execute_hybrid_search(
            query, vehicle_category=veh, limit=limit
        )
        return {
            "status": "success",
            "total_hits": len(results),
            "results": results,
        }

    async def handle_mcp_traffic_hierarchical_navigate(
        self, args: dict[str, Any]
    ) -> dict[str, Any]:
        target_path = args.get("target_path", "")
        direction = args.get("direction", "PARENT_CHAIN")

        nodes = []
        for chunk in self.db.chunks.values():
            if chunk.hierarchy_path.startswith(target_path) or target_path.startswith(
                chunk.hierarchy_path
            ):
                nodes.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "parent_id": None,
                        "path": chunk.hierarchy_path,
                        "depth": len(chunk.hierarchy_path.split(".")),
                        "chunk_level": "POINT" if chunk.point_letter else "ARTICLE",
                        "chunk_index": chunk.article_index,
                        "title": chunk.doc_title,
                        "lead_sentence": chunk.lead_sentence,
                        "raw_text": chunk.verbatim_text,
                        "contextualized_text": chunk.contextualized_text,
                        "norm_role": chunk.norm_role.value,
                    }
                )

        return {
            "status": "success",
            "target_path": target_path,
            "direction": direction,
            "total_nodes": len(nodes),
            "nodes": nodes,
        }

    async def handle_mcp_traffic_graph_traverse(
        self, args: dict[str, Any]
    ) -> dict[str, Any]:
        start_chunk_id = args.get("start_chunk_id", "")
        allowed = args.get("relation_types", None)
        max_depth = args.get("max_depth", 2)

        paths = await self.db.execute_graph_traversal(
            start_chunk_id, allowed_edge_types=allowed, max_depth=max_depth
        )
        return {
            "status": "success",
            "start_chunk_id": start_chunk_id,
            "total_paths": len(paths),
            "traversal_paths": paths,
        }

    async def handle_mcp_traffic_scope_override_detect(
        self, args: dict[str, Any]
    ) -> dict[str, Any]:
        scenario = args.get("scenario_type", "POLICE_OVERRIDE_RED_LIGHT")
        if scenario == "POLICE_OVERRIDE_RED_LIGHT":
            return {
                "status": "success",
                "is_override_active": True,
                "dominant_authority": "POLICE_COMMAND",
                "overridden_signals": ["TRAFFIC_LIGHT_RED"],
                "statutory_precedence_rank": 1,
                "is_driver_action_legal": True,
                "legal_basis": [
                    "QCVN 41:2019/BGTVT Điều 4 Khoản 4.1",
                    "Luật Giao thông đường bộ 2008 Điều 11 Khoản 2",
                ],
                "ruling_rationale": "Hiệu lệnh của Cảnh sát giao thông có thứ bậc cao nhất, ghi đè tín hiệu đèn đỏ.",
            }
        elif scenario == "EMERGENCY_AMBULANCE":
            return {
                "status": "success",
                "is_override_active": True,
                "dominant_authority": "EMERGENCY_MISSION",
                "overridden_signals": ["SPEED_LIMIT", "RED_LIGHT", "ONE_WAY"],
                "statutory_precedence_rank": 1,
                "is_driver_action_legal": True,
                "legal_basis": [
                    "Luật Giao thông đường bộ 2008 Điều 22",
                    "Luật Trật tự, an toàn GTĐB 2024 Điều 20",
                ],
                "ruling_rationale": "Xe cứu thương đang làm nhiệm vụ cấp cứu có tín hiệu còi, đèn được miễn trừ các quy tắc giao thông cơ bản.",
            }
        return {
            "status": "success",
            "is_override_active": False,
            "dominant_authority": "GENERAL_RULE",
            "is_driver_action_legal": False,
            "legal_basis": ["Nghị định 100/2019/NĐ-CP"],
            "ruling_rationale": "Không có yếu tố ghi đè hoặc ngoại lệ.",
        }

    async def handle_mcp_traffic_sign_catalog_lookup(
        self, args: dict[str, Any]
    ) -> dict[str, Any]:
        sign_code = args.get("sign_code", "").upper().strip()
        sign = self.db.signs.get(sign_code)
        if not sign:
            # Fuzzy match
            for s in self.db.signs.values():
                if sign_code.replace(".", "") in s.sign_code.replace(".", ""):
                    sign = s
                    break
        if not sign:
            return {"status": "not_found", "sign_code": sign_code}

        return {
            "status": "success",
            "sign_code": sign.sign_code,
            "sign_name": sign.sign_name,
            "category": sign.category.value,
            "shape": sign.shape,
            "primary_color": sign.primary_color,
            "meaning": sign.meaning,
            "placement_rules": sign.placement_rules,
            "penalty_references": sign.penalty_references,
        }

    async def handle_mcp_traffic_knowledge_cache_query(
        self, args: dict[str, Any]
    ) -> dict[str, Any]:
        query_hash = args.get("query_hash", "")
        cached = self.db.runtime_cache.get(query_hash)
        if cached:
            return {"status": "hit", "cache_entry": cached}
        return {"status": "miss"}

    async def handle_mcp_traffic_knowledge_cache_write(
        self, args: dict[str, Any]
    ) -> dict[str, Any]:
        query_hash = args.get("query_hash", "")
        self.db.runtime_cache[query_hash] = args
        return {"status": "written", "query_hash": query_hash}
