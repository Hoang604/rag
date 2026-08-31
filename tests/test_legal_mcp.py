"""Comprehensive test suite for Model Context Protocol (MCP) JSON-RPC 2.0 Server & Tools."""

from __future__ import annotations

from typing import cast

import pytest

from rag_eval.legal.mcp.server import LegalMCPServer
from rag_eval.legal.mcp.tools import LegalMCPTools
from tests.legal.mocks.mock_db import MockDatabasePool


def _res(r: dict[str, object] | None) -> dict[str, object]:
    assert r is not None
    val = r.get("result")
    assert isinstance(val, dict)
    return val


def _err(r: dict[str, object] | None) -> dict[str, object]:
    assert r is not None
    val = r.get("error")
    assert isinstance(val, dict)
    return val


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
        result = _res(res)
        assert result["protocolVersion"] == "2024-11-05"
        server_info = cast(dict[str, object], result["serverInfo"])
        assert server_info["name"] == "vietnamese-traffic-law-mcp"
        capabilities = cast(dict[str, object], result["capabilities"])
        assert "tools" in capabilities

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
        result_dict = _res(res)
        tools = cast(list[dict[str, object]], result_dict["tools"])
        assert len(tools) == 9
        tool_names = [str(t["name"]) for t in tools]
        assert "mcp_traffic_corpus_validate" in tool_names
        assert "mcp_traffic_hybrid_search" in tool_names
        assert "mcp_traffic_verbatim_grep" in tool_names
        assert "mcp_traffic_hierarchical_navigate" in tool_names
        assert "mcp_traffic_graph_traverse" in tool_names
        assert "mcp_traffic_graph_edge_write" in tool_names
        assert "mcp_traffic_sign_catalog_lookup" in tool_names
        assert "mcp_traffic_knowledge_cache_query" in tool_names
        assert "mcp_traffic_knowledge_cache_write" in tool_names

        for t in tools:
            assert "inputSchema" in t
            schema = t.get("inputSchema")
            assert isinstance(schema, dict) and schema.get("type") == "object"

    async def test_mcp_tools_call_corpus_validate(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 100,
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_corpus_validate",
                    "arguments": {"document_id": "doc_nd100"},
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"
        assert result["is_valid"] is True
        assert int(str(result["total_chunks_scanned"])) >= 5

    async def test_mcp_tools_call_hybrid_search(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 101,
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_hybrid_search",
                    "arguments": {
                        "query": "vượt đèn đỏ",
                        "limit": 5,
                        "effective_at": "2025-01-01",
                    },
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"
        results = cast(list[dict[str, object]], result["results"])
        assert len(results) > 0
        assert str(results[0]["doc_code"]) in ("100/2019/ND-CP", "36/2024/QH15")

    async def test_mcp_tools_call_verbatim_grep(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 102,
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_verbatim_grep",
                    "arguments": {
                        "pattern": "đèn tín hiệu",
                        "is_regex": False,
                        "limit": 5,
                    },
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"
        assert int(str(result["total_hits"])) >= 1

    async def test_mcp_tools_call_hierarchical_navigate(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 103,
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_hierarchical_navigate",
                    "arguments": {
                        "target_path": "doc_nd100_2019.c2.s1.a5",
                        "direction": "children",
                    },
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"
        nodes = cast(list[dict[str, object]], result["nodes"])
        assert len(nodes) > 0

    async def test_mcp_tools_call_graph_traverse(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 104,
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_graph_traverse",
                    "arguments": {
                        "start_chunk_id": "chk_nd100_art5_cl3_pta",
                        "relation_types": ["REFERENCES_TECHNICAL_STANDARD"],
                    },
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"
        paths = cast(list[dict[str, object]], result["traversal_paths"])
        assert len(paths) >= 1

    async def test_mcp_tools_call_graph_edge_write(self) -> None:
        pool = MockDatabasePool()
        server = LegalMCPServer(LegalMCPTools(pool=pool))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 105,
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_graph_edge_write",
                    "arguments": {
                        "source_chunk_id": "chk_nd100_art5_cl3_pta",
                        "target_path": "doc_qcvn41_2019.art10",
                        "relation_type": "REFERENCES_TECHNICAL_STANDARD",
                        "confidence_score": 0.95,
                    },
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"
        assert result["relation_type"] == "REFERENCES_TECHNICAL_STANDARD"

    async def test_mcp_tools_call_sign_catalog_lookup(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 106,
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_sign_catalog_lookup",
                    "arguments": {
                        "sign_code": "P.102",
                    },
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"
        assert result["sign_name"] == "Cấm đi ngược chiều"
        signs = cast(list[dict[str, object]], result["signs"])
        assert len(signs) >= 1

    async def test_mcp_tools_call_knowledge_cache_lifecycle(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))

        # 1. Query non-existent hash (miss)
        res_miss = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 107,
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_knowledge_cache_query",
                    "arguments": {
                        "query": "câu hỏi chưa từng có trong cache",
                    },
                },
            }
        )
        assert res_miss is not None
        r_miss = _res(res_miss)
        assert r_miss["status"] == "miss"
        assert r_miss["cache_hit"] is False

        # 2. Write answer into cache
        res_write = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 108,
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_knowledge_cache_write",
                    "arguments": {
                        "query": "câu hỏi chưa từng có trong cache",
                        "synthesized_answer": "Câu trả lời mẫu đã được kiểm chứng.",
                        "retrieved_chunk_ids": ["chk_nd100_art5_cl3_pta"],
                    },
                },
            }
        )
        assert res_write is not None
        r_write = _res(res_write)
        assert r_write["status"] == "written"
        assert "cache_id" in r_write

        # 3. Query same question (hit)
        res_hit = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 109,
                "method": "tools/call",
                "params": {
                    "name": "mcp_traffic_knowledge_cache_query",
                    "arguments": {
                        "query": "câu hỏi chưa từng có trong cache",
                    },
                },
            }
        )
        assert res_hit is not None
        r_hit = _res(res_hit)
        assert r_hit["status"] == "hit"
        assert r_hit["cache_hit"] is True
        cached_entry = cast(dict[str, object], r_hit["cached_entry"])
        assert cached_entry["synthesized_answer"] == "Câu trả lời mẫu đã được kiểm chứng."

    async def test_direct_mcp_traffic_hybrid_search_method(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 201,
                "method": "mcp_traffic_hybrid_search",
                "params": {
                    "query": "ngược chiều xe máy",
                    "limit": 3,
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"
        results = cast(list[dict[str, object]], result["results"])
        assert len(results) > 0

    async def test_direct_mcp_traffic_verbatim_grep_method(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 202,
                "method": "mcp_traffic_verbatim_grep",
                "params": {
                    "pattern": "ngược chiều",
                    "limit": 3,
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"
        assert int(str(result["total_hits"])) >= 1

    async def test_direct_mcp_traffic_hierarchical_navigate_method(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 203,
                "method": "mcp_traffic_hierarchical_navigate",
                "params": {
                    "target_path": "doc_nd100_2019.c2.s1.a6",
                    "direction": "children",
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"

    async def test_direct_mcp_traffic_sign_catalog_lookup_method(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 204,
                "method": "mcp_traffic_sign_catalog_lookup",
                "params": {
                    "sign_code": "P.102",
                },
            }
        )
        assert res is not None
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["sign_name"] == "Cấm đi ngược chiều"

    async def test_invalid_jsonrpc_returns_32600(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.handle_request({"bad_payload": True})
        assert res is not None
        err = _err(res)
        assert err["code"] == -32600

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
        err = _err(res)
        assert err["code"] == -32601

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
        err = _err(res)
        assert err["code"] == -32602
        assert "validation" in str(err["message"]).lower()

    async def test_server_call_tool_convenience_method(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_sign_catalog_lookup", {"sign_code": "P.102"}
        )
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["sign_name"] == "Cấm đi ngược chiều"

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
        err = _err(res)
        assert err["code"] == E_VECTOR_DIMENSION_MISMATCH
        assert "vector dimension mismatch" in str(err["message"]).lower()
