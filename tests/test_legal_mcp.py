"""Comprehensive test suite for Model Context Protocol (MCP) JSON-RPC 2.0 Server & Tools."""

from __future__ import annotations

import pytest

from rag_eval.legal.mcp.server import LegalMCPServer
from rag_eval.legal.mcp.tools import LegalMCPTools
from tests.legal.mocks.mock_db import MockDatabasePool


@pytest.mark.asyncio
class TestLegalMCPServerProtocol:
    """Tests full MCP JSON-RPC 2.0 lifecycle protocol and error mappings."""

    async def test_mcp_initialize_handshake(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        assert res["id"] == 1
        result = res["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "vietnamese-traffic-law-mcp"
        assert "tools" in result["capabilities"]

    async def test_mcp_notifications_initialized_returns_none(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
        )
        assert res is None

    async def test_mcp_ping(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "ping",
                "params": {},
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        assert res["id"] == 42
        assert res["result"] == {}

    async def test_mcp_tools_list_manifests(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "list-1",
                "method": "tools/list",
                "params": {},
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        tools = res["result"]["tools"]
        assert len(tools) == 8  # 7 specialized tools (cache has query & write)
        tool_names = [t["name"] for t in tools]
        assert "mcp_traffic_corpus_validate" in tool_names
        assert "mcp_traffic_hybrid_search" in tool_names
        assert "mcp_traffic_hierarchical_navigate" in tool_names
        assert "mcp_traffic_graph_traverse" in tool_names
        assert "mcp_traffic_scope_override_detect" in tool_names
        assert "mcp_traffic_sign_catalog_lookup" in tool_names
        assert "mcp_traffic_knowledge_cache_query" in tool_names
        assert "mcp_traffic_knowledge_cache_write" in tool_names

        for t in tools:
            assert "inputSchema" in t
            assert t["inputSchema"]["type"] == "object"

    async def test_mcp_tools_call_corpus_validate(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_corpus_validate",
                    "arguments": {"document_id": "100/2019/ND-CP"},
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        assert res["id"] == "call-1"
        assert res["result"]["status"] == "success"
        assert res["result"]["is_valid"] is True
        assert res["result"]["total_chunks_scanned"] >= 5

    async def test_mcp_tools_call_hybrid_search(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-2",
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_hybrid_search",
                    "arguments": {
                        "query": "nồng độ cồn ô tô",
                        "vehicle_types": ["CAR_PASSENGER"],
                        "limit": 3,
                    },
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        results = res["result"]["results"]
        assert len(results) > 0
        assert results[0]["min_fine_vnd"] is not None

    async def test_mcp_tools_call_hierarchical_navigate(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-3",
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_hierarchical_navigate",
                    "arguments": {
                        "target_path": "doc_nd100_2019.c2.s1.a5",
                        "direction": "PARENT_CHAIN",
                    },
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        nodes = res["result"]["nodes"]
        assert len(nodes) > 0

    async def test_mcp_tools_call_graph_traverse(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-4",
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_graph_traverse",
                    "arguments": {
                        "start_chunk_id": "chk_nd100_art5_cl3_pta",
                        "max_depth": 2,
                    },
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        paths = res["result"]["traversal_paths"]
        assert len(paths) >= 1
        assert paths[0]["target_doc_code"] == "QCVN 41:2019/BGTVT"

    async def test_mcp_tools_call_scope_override_detect(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-5",
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_scope_override_detect",
                    "arguments": {
                        "scenario_type": "POLICE_OVERRIDE_RED_LIGHT",
                    },
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = res["result"]
        assert result["is_override_active"] is True
        assert result["dominant_authority"] == "POLICE_COMMAND"

    async def test_mcp_tools_call_sign_catalog_lookup(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-6",
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_sign_catalog_lookup",
                    "arguments": {"sign_code": "P.102"},
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        assert res["result"]["sign_name"] == "Cấm đi ngược chiều"

    async def test_mcp_tools_call_knowledge_cache_lifecycle(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        # Miss
        res_miss = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-7a",
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_knowledge_cache_query",
                    "arguments": {"query_hash": "cache_key_123"},
                },
            }
        )
        assert res_miss is not None
        assert res_miss["result"]["status"] == "miss"

        # Write
        res_write = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-7b",
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_knowledge_cache_write",
                    "arguments": {
                        "query_hash": "cache_key_123",
                        "answer": "Test Synthesized Answer",
                        "citations": ["Điều 5 NĐ 100"],
                    },
                },
            }
        )
        assert res_write is not None
        assert res_write["result"]["status"] == "written"

        # Hit
        res_hit = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "call-7c",
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_knowledge_cache_query",
                    "arguments": {"query_hash": "cache_key_123"},
                },
            }
        )
        assert res_hit is not None
        assert res_hit["result"]["status"] == "hit"
        assert res_hit["result"]["cache_entry"]["answer"] == "Test Synthesized Answer"

    async def test_direct_method_invocation_backward_compatibility(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "direct-1",
                "method": "mcp_traffic_sign_catalog_lookup",
                "params": {"sign_code": "P102"},
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        assert res["result"]["sign_name"] == "Cấm đi ngược chiều"

    async def test_invalid_jsonrpc_returns_32600(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request({"bad_payload": True})
        assert res is not None
        assert res["error"]["code"] == -32600

    async def test_unknown_method_returns_32601(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "err-1",
                "method": "unknown_tool_function",
                "params": {},
            }
        )
        assert res is not None
        assert res["error"]["code"] == -32601

    async def test_invalid_parameters_returns_32602(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "err-2",
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_hybrid_search",
                    "arguments": {
                        "query": "test",
                        "fine_min_vnd": -500,  # Fails ge=0 constraint
                    },
                },
            }
        )
        assert res is not None
        assert res["error"]["code"] == -32602
        assert "validation" in res["error"]["message"].lower() or "arguments" in res["error"]["message"].lower()

    async def test_server_call_tool_convenience_method(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_sign_catalog_lookup", {"sign_code": "P.102"}
        )
        assert res["jsonrpc"] == "2.0"
        assert res["result"]["sign_name"] == "Cấm đi ngược chiều"

    async def test_tools_aliases(self) -> None:
        tools = LegalMCPTools(pool=MockDatabasePool())
        s_res = await tools.search_legal_norms(query="ô tô đèn đỏ", limit=2)
        assert s_res["status"] == "success"

        sig_res = await tools.lookup_sign(sign_code="P.102")
        assert sig_res["status"] == "success"

        prec_res = await tools.resolve_precedence(scenario_type="POLICE_OVERRIDE_RED_LIGHT")
        assert prec_res["is_override_active"] is True

        temp_res = await tools.validate_temporal(document_code="100/2019/ND-CP")
        assert temp_res["status"] == "success"
        assert temp_res["is_active"] is True

    async def test_domain_error_propagation_against_failing_database(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        import asyncpg

        from rag_eval.legal.mcp.server import E_VECTOR_DIMENSION_MISMATCH

        mock_conn = AsyncMock()
        mock_tx = MagicMock()
        mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        mock_conn.fetch.side_effect = asyncpg.PostgresError("ERROR: different vector dimensions 384 and 1536")

        mock_pool = MagicMock(spec=asyncpg.Pool)
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        tools = LegalMCPTools(pool=mock_pool)
        server = LegalMCPServer(tools=tools)

        res = await server.call_tool("mcp_traffic_hybrid_search", {"query": "vượt đèn đỏ"})
        assert "error" in res
        assert res["error"]["code"] == E_VECTOR_DIMENSION_MISMATCH
        assert "vector dimension mismatch" in res["error"]["message"].lower()

