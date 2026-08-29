"""Tier 1: Feature Coverage tests for Requirement 4 (R4) - Production MCP 7-Tool Server."""

from __future__ import annotations

import pytest

from rag_eval.legal.mcp.server import LegalMCPServer
from rag_eval.legal.mcp.tools import LegalMCPTools
from tests.legal.mocks.mock_db import MockDatabasePool


@pytest.mark.asyncio
class TestR4MCPServer:
    """Tests JSON-RPC 2.0 interface contracts for all 7 specialized MCP tools directly against LegalMCPServer."""

    async def test_tool_1_corpus_validate_returns_valid_contract(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_corpus_validate", {"document_id": "doc_nd100"}
        )
        assert res["jsonrpc"] == "2.0"
        result = res["result"]
        assert result["status"] == "success"
        assert result["is_valid"] is True
        assert result["total_chunks_scanned"] >= 5

    async def test_tool_2_hybrid_search_executes_dense_and_sparse_fusion(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_hybrid_search",
            {"query": "đèn đỏ ô tô", "vehicle_types": ["CAR_PASSENGER"], "limit": 3},
        )
        assert res["jsonrpc"] == "2.0"
        results = res["result"]["results"]
        assert len(results) > 0
        assert results[0]["min_fine_vnd"] == 800000

    async def test_tool_3_hierarchical_navigate_retrieves_parent_chain(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_hierarchical_navigate",
            {"target_path": "doc_nd100_2019.c2.s1.a5", "direction": "PARENT_CHAIN"},
        )
        assert res["jsonrpc"] == "2.0"
        nodes = res["result"]["nodes"]
        assert len(nodes) > 0

    async def test_tool_4_graph_traverse_follows_normative_edges(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_graph_traverse",
            {
                "start_chunk_id": "chk_nd100_art5_cl3_pta",
                "relation_types": ["REFERENCES_TECHNICAL_STANDARD"],
            },
        )
        assert res["jsonrpc"] == "2.0"
        paths = res["result"]["traversal_paths"]
        assert len(paths) >= 1
        assert paths[0]["target_doc_code"] == "QCVN 41:2019/BGTVT"

    async def test_tool_5_scope_override_detect_evaluates_police_command(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        # Police override scenario
        res = await server.call_tool(
            "mcp_traffic_scope_override_detect",
            {"scenario_type": "POLICE_OVERRIDE_RED_LIGHT"},
        )
        assert res["jsonrpc"] == "2.0"
        result = res["result"]
        assert result["is_override_active"] is True
        assert result["is_overridden"] is True
        assert result["dominant_authority"] == "POLICE_COMMAND"
        assert result["override_type"] == "POLICE_SIGNAL_PRECEDENCE"
        assert result["precedence_level"] == 1
        assert result["statutory_precedence_rank"] == 1
        assert result["is_emergency_exception"] is False
        assert result["is_driver_action_legal"] is True
        assert result["governing_rule"]["precedence_level"] == 1
        assert result["governing_rule"]["doc_code"] == "Luật GTĐB 2008"
        assert result["overridden_rule"]["precedence_level"] == 3
        assert len(result["authority_basis"]) > 0
        assert len(result["override_reasoning"]) > 0

        # Emergency privilege scenario
        res_emerg = await server.call_tool(
            "mcp_traffic_scope_override_detect",
            {"scenario_type": "AMBULANCE_EMERGENCY_MISSION"},
        )
        r_emerg = res_emerg["result"]
        assert r_emerg["is_override_active"] is True
        assert r_emerg["is_emergency_exception"] is True
        assert r_emerg["override_type"] == "EMERGENCY_PRIVILEGE"
        assert r_emerg["governing_rule"]["precedence_level"] == 1
        assert r_emerg["governing_rule"]["doc_code"] == "Luật GTĐB 2008"

    async def test_tool_6_sign_catalog_lookup_exact_and_fuzzy(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        # Exact lookup
        res_exact = await server.call_tool(
            "mcp_traffic_sign_catalog_lookup", {"sign_code": "P.102"}
        )
        assert res_exact["result"]["sign_name"] == "Cấm đi ngược chiều"
        assert res_exact["result"]["total_matches"] >= 1
        assert len(res_exact["result"]["signs"]) >= 1
        assert res_exact["result"]["signs"][0]["sign_code"] == "P.102"
        assert len(res_exact["result"]["signs"][0]["penalty_references"]) > 0

        # Fuzzy lookup (P102 without dot)
        res_fuzzy = await server.call_tool(
            "mcp_traffic_sign_catalog_lookup", {"sign_code": "P102"}
        )
        assert res_fuzzy["result"]["sign_name"] == "Cấm đi ngược chiều"
        assert res_fuzzy["result"]["total_matches"] >= 1
        assert len(res_fuzzy["result"]["signs"]) >= 1

    async def test_tool_7_knowledge_cache_lifecycle(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        # Query miss
        res_miss = await server.call_tool(
            "mcp_traffic_knowledge_cache_query", {"query_hash": "hash_xyz"}
        )
        assert res_miss["result"]["status"] == "miss"
        assert res_miss["result"]["cache_hit"] is False
        assert res_miss["result"]["cached_entry"] is None

        # Write
        res_write = await server.call_tool(
            "mcp_traffic_knowledge_cache_write",
            {"query_hash": "hash_xyz", "plan": {"step": 1}, "answer": "Answer text"},
        )
        assert res_write["result"]["status"] == "written"

        # Query hit
        res_hit = await server.call_tool(
            "mcp_traffic_knowledge_cache_query", {"query_hash": "hash_xyz"}
        )
        assert res_hit["result"]["status"] == "hit"
        assert res_hit["result"]["cache_hit"] is True
        assert res_hit["result"]["cached_entry"] is not None
        assert res_hit["result"]["cached_entry"]["synthesized_answer"] == "Answer text"
        assert res_hit["result"]["cached_entry"]["validation_status"] == "VERIFIED"

    async def test_unknown_method_returns_jsonrpc_32601_error(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool("mcp_non_existent_tool", {})
        assert res["error"]["code"] == -32601
        assert "not found" in res["error"]["message"].lower()

    async def test_invalid_parameters_returns_jsonrpc_32602_error(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_hybrid_search",
            {"query": "đèn đỏ", "fine_min_vnd": -100},
        )
        assert res["error"]["code"] == -32602

    async def test_f26_dynamic_article_depth_navigation_full_article(self) -> None:
        """F-26: Verifies FULL_ARTICLE navigation dynamically extracts article path at any depth."""
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        # Depth 6 node -> resolves article at depth 4
        res_d6 = await server.call_tool(
            "mcp_traffic_hierarchical_navigate",
            {
                "target_path": "doc_nd100_2019.c2.s1.a5.c1.p_a",
                "direction": "FULL_ARTICLE",
            },
        )
        assert res_d6["jsonrpc"] == "2.0"
        nodes_d6 = res_d6["result"]["nodes"]
        assert len(nodes_d6) > 0
        assert any(n["chunk_level"] == "ARTICLE" for n in nodes_d6)

        # Depth 3 node in TT31 -> resolves article at depth 2
        res_d3 = await server.call_tool(
            "mcp_traffic_hierarchical_navigate",
            {
                "target_path": "doc_tt31_2019.a6.c1",
                "direction": "FULL_ARTICLE",
            },
        )
        assert res_d3["jsonrpc"] == "2.0"
        nodes_d3 = res_d3["result"]["nodes"]
        assert len(nodes_d3) > 0

    async def test_f27_expanded_in_memory_sign_catalog_fallback(self) -> None:
        """F-27: Verifies all 13 standard signs exist in static fallback catalog."""
        # Use tools without pool to force static fallback catalog
        tools = LegalMCPTools(pool=None)
        server = LegalMCPServer(tools)

        expected_signs = [
            ("P.102", "Cấm đi ngược chiều"),
            ("P.106A", "Cấm xe ô tô tải"),
            ("P.106B", "Cấm xe ô tô tải"),
            ("P.115", "Hạn chế trọng tải toàn bộ xe"),
            ("P.123A", "Cấm rẽ trái"),
            ("P.124A", "Cấm quay đầu xe"),
            ("P.127", "Tốc độ tối đa cho phép"),
            ("R.420", "Bắt đầu khu đông dân cư"),
            ("R.421", "Hết khu đông dân cư"),
            ("W.201", "Chỗ ngoặt nguy hiểm"),
            ("W.207", "Giao nhau với đường không ưu tiên"),
            ("I.407A", "Đường một chiều"),
            ("DP.135", "Hết tất cả các lệnh cấm"),
        ]

        for code, expected_name_part in expected_signs:
            res = await server.call_tool(
                "mcp_traffic_sign_catalog_lookup",
                {"sign_code": code},
            )
            assert res["jsonrpc"] == "2.0"
            result = res["result"]
            assert result["status"] == "success", f"Sign {code} lookup failed: {result}"
            assert result["total_matches"] >= 1
            assert len(result["signs"]) >= 1
            assert expected_name_part.lower() in result["sign_name"].lower()
            assert len(result["signs"][0]["penalty_references"]) > 0

    async def test_f32_operational_mock_fallback_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """F-32: Verifies mock fallback is guarded and fails fast with -32001 in production mode."""
        from unittest.mock import AsyncMock, patch

        from rag_eval.legal.mcp.server import E_STORAGE_CONNECTION

        # 1. In production mode (no mock fallback, not in pytest env simulated), connection failure raises StorageConnectionError
        monkeypatch.delenv("ALLOW_MOCK_FALLBACK", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")

        tools_prod = LegalMCPTools(pool=None)
        server_prod = LegalMCPServer(tools_prod)

        with patch("rag_eval.legal.mcp.tools.get_db_pool", new_callable=AsyncMock) as mock_get_pool:
            mock_get_pool.side_effect = RuntimeError("PostgreSQL connection refused on port 5432")
            res_fail = await server_prod.call_tool("mcp_traffic_corpus_validate", {"document_id": "doc_nd100"})
            assert "error" in res_fail
            assert res_fail["error"]["code"] == E_STORAGE_CONNECTION
            assert "unavailable" in res_fail["error"]["message"].lower() or "connection" in res_fail["error"]["message"].lower()

        # 2. When ALLOW_MOCK_FALLBACK=true, connection failure gracefully falls back to memory mode
        monkeypatch.setenv("ALLOW_MOCK_FALLBACK", "true")
        tools_fallback = LegalMCPTools(pool=None)
        server_fallback = LegalMCPServer(tools_fallback)

        with patch("rag_eval.legal.mcp.tools.get_db_pool", new_callable=AsyncMock) as mock_get_pool_fallback:
            mock_get_pool_fallback.side_effect = RuntimeError("PostgreSQL connection refused on port 5432")
            res_ok = await server_fallback.call_tool("mcp_traffic_sign_catalog_lookup", {"sign_code": "P.102"})
            assert res_ok["jsonrpc"] == "2.0"
            assert res_ok["result"]["status"] == "success"

    async def test_f33_vector_float_sanitization_rejects_nan_and_inf(self) -> None:
        """F-33: Verifies NaN and Inf vector inputs are rejected with VectorDimensionMismatchError (-32003)."""
        from rag_eval.legal.mcp.server import E_VECTOR_DIMENSION_MISMATCH

        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))

        # 1. NaN in hybrid_search query_vector
        res_nan = await server.call_tool(
            "mcp_traffic_hybrid_search",
            {"query": "vượt đèn đỏ", "query_vector": [float("nan")] * 384},
        )
        assert "error" in res_nan
        assert res_nan["error"]["code"] == E_VECTOR_DIMENSION_MISMATCH
        assert "non-finite" in res_nan["error"]["message"].lower()

        # 2. Inf in hybrid_search query_vector
        res_inf = await server.call_tool(
            "mcp_traffic_hybrid_search",
            {"query": "vượt đèn đỏ", "query_vector": [float("inf")] * 384},
        )
        assert "error" in res_inf
        assert res_inf["error"]["code"] == E_VECTOR_DIMENSION_MISMATCH

        # 3. NaN in knowledge_cache_query query_vector
        res_cache_nan = await server.call_tool(
            "mcp_traffic_knowledge_cache_query",
            {"natural_query": "vượt đèn đỏ", "query_vector": [float("nan")] * 384},
        )
        assert "error" in res_cache_nan
        assert res_cache_nan["error"]["code"] == E_VECTOR_DIMENSION_MISMATCH

        # 4. Inf in knowledge_cache_query query_vector
        res_cache_inf = await server.call_tool(
            "mcp_traffic_knowledge_cache_query",
            {"natural_query": "vượt đèn đỏ", "query_vector": [float("inf")] * 384},
        )
        assert "error" in res_cache_inf
        assert res_cache_inf["error"]["code"] == E_VECTOR_DIMENSION_MISMATCH

