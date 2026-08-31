"""Unit tests for LegalMCPTools and LegalMCPServer JSON-RPC dispatch."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag_eval.legal.mcp.server import LegalMCPServer
from rag_eval.legal.mcp.tools import LegalMCPTools


@pytest.fixture
def mock_pool() -> Any:
    """Provides a mocked asyncpg pool simulating database responses."""
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    # Mock default fetch responses
    conn.fetch.return_value = [
        {
            "chunk_id": "88888888-4444-4444-4444-121212121212",
            "doc_code": "100/2019/NĐ-CP",
            "doc_title": "Nghị định 100",
            "path": "doc_100_2019_nd_cp.a_5.c_3.p_a",
            "verbatim_text": "Điểm a) Điều khiển xe chạy quá tốc độ",
            "contextualized_text": "[Nghị định 100] > [Điều 5]\nĐiểm a) Điều khiển xe chạy quá tốc độ",
            "metadata": json.dumps({"fines": {"min_vnd": 800000, "max_vnd": 1000000}}),
            "effective_date": "2020-01-15",
            "expiration_date": None,
            "rrf_score": 0.032,
            "similarity_score": 0.85,
            "id": "88888888-4444-4444-4444-121212121212",
            "edge_id": "99999999-5555-5555-5555-131313131313",
            "source_chunk_id": "88888888-4444-4444-4444-121212121212",
            "target_chunk_id": None,
            "target_external_ref": "Điều 12 Luật GTĐB",
            "relation_type": "REFERENCES",
            "citation_text": "theo Điều 12",
            "depth": 1,
            "target_path": None,
            "target_text": None,
        }
    ]

    def mock_fetchval(query: str, *args: Any) -> Any:
        if "WHERE NOT EXISTS" in query:
            return 0
        return 10

    conn.fetchval.side_effect = mock_fetchval
    return pool


@pytest.mark.asyncio
async def test_mcp_server_initialize() -> None:
    """Verifies MCP server JSON-RPC initialize handshake."""
    server = LegalMCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    }
    resp = await server.handle_request_dict(req)
    assert resp is not None
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert resp["result"]["serverInfo"]["name"] == "vietnamese-traffic-law-mcp"


@pytest.mark.asyncio
async def test_mcp_server_tools_list() -> None:
    """Verifies MCP server lists the 6 canonical Agent-First tools."""
    server = LegalMCPServer()
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
    }
    resp = await server.handle_request_dict(req)
    assert resp is not None
    tools = resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    expected_tools = {
        "mcp_traffic_hybrid_search",
        "mcp_traffic_verbatim_grep",
        "mcp_traffic_hierarchical_navigate",
        "mcp_traffic_graph_traverse",
        "mcp_traffic_graph_edge_write",
        "mcp_traffic_corpus_validate",
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
async def test_mcp_hybrid_search_dispatch(mock_pool: Any) -> None:
    """Verifies execution of hybrid_search via MCP tool dispatch."""
    tools = LegalMCPTools(pool=mock_pool)
    server = LegalMCPServer(tools=tools)

    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_hybrid_search",
            "arguments": {"query": "vượt quá tốc độ 10 km/h", "limit": 5},
        },
    }
    resp = await server.handle_request_dict(req)
    assert resp is not None
    assert "result" in resp
    assert resp["result"]["total_hits"] >= 1
    hit = resp["result"]["hits"][0]
    assert hit["doc_code"] == "100/2019/NĐ-CP"


@pytest.mark.asyncio
async def test_mcp_verbatim_grep_dispatch(mock_pool: Any) -> None:
    """Verifies execution of verbatim_grep via MCP tool dispatch."""
    tools = LegalMCPTools(pool=mock_pool)
    server = LegalMCPServer(tools=tools)

    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_verbatim_grep",
            "arguments": {"pattern": "tốc độ", "is_regex": False},
        },
    }
    resp = await server.handle_request_dict(req)
    assert resp is not None
    assert "result" in resp
    assert resp["result"]["total_matches"] >= 1


@pytest.mark.asyncio
async def test_mcp_corpus_validate_dispatch(mock_pool: Any) -> None:
    """Verifies execution of corpus_validate."""
    tools = LegalMCPTools(pool=mock_pool)
    server = LegalMCPServer(tools=tools)

    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_corpus_validate",
            "arguments": {},
        },
    }
    resp = await server.handle_request_dict(req)
    assert resp is not None
    assert resp["result"]["status"] == "HEALTHY"
