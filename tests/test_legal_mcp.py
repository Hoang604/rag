"""Unit tests for LegalMCPTools and LegalMCPServer JSON-RPC dispatch."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag_eval.legal.ingestion.staging import StagingManager
from rag_eval.legal.mcp.server import LegalMCPServer
from rag_eval.legal.mcp.tools import LegalMCPTools

SAMPLE_TEXT = """
CHƯƠNG II
HÀNH VI VI PHẠM

Điều 5. Xử phạt người điều khiển xe ô tô
3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện hành vi sau:
a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;
"""


@pytest.fixture
def mock_pool() -> Any:
    """Provides a mocked asyncpg pool simulating database responses."""
    pool = MagicMock()
    conn = AsyncMock()

    # Configure asyncpg connection.transaction() async context manager
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx)

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
        if "INSERT INTO documents" in query:
            return "88888888-4444-4444-4444-121212121212"
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
    """Verifies MCP server lists the 10 canonical Agent-First and Staging tools."""
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
        "mcp_traffic_stg_preview",
        "mcp_traffic_stg_patch",
        "mcp_traffic_stg_add_edges",
        "mcp_traffic_stg_commit",
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


# ------------------------------------------------------------------------------
# Staging MCP Tool Integration Tests
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stg_commit_lifecycle(mock_pool: Any, tmp_path: Path) -> None:
    """Verifies full promotion lifecycle from staging to DB and cleanup."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    stg_mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    tools = LegalMCPTools(pool=mock_pool, staging_manager=stg_mgr)
    server = LegalMCPServer(tools=tools)

    # 1. Preview
    req_prev = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_stg_preview",
            "arguments": {"doc_code": "100/2019/NĐ-CP"},
        },
    }
    resp_prev = await server.handle_request_dict(req_prev)
    assert resp_prev is not None
    assert resp_prev["result"]["total_chunks"] == 1

    # 2. Commit
    req_commit = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_stg_commit",
            "arguments": {"doc_code": "100/2019/NĐ-CP", "compute_embeddings": False},
        },
    }
    resp_commit = await server.handle_request_dict(req_commit)
    assert resp_commit is not None
    assert resp_commit["result"]["status"] == "SUCCESS"
    assert resp_commit["result"]["chunks_committed"] == 1

    # Verify staging file was cleaned up
    assert not (tmp_path / "100_2019_n_cp.json").exists()


@pytest.mark.asyncio
async def test_stg_patch_mcp_dispatch(tmp_path: Path) -> None:
    """Verifies patching chunks via MCP tool dispatch."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    stg_mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    tools = LegalMCPTools(staging_manager=stg_mgr)
    server = LegalMCPServer(tools=tools)

    patch_payload = [
        {
            "path": "100_2019_n_cp.c_ii.a_5.c_3.p_a",
            "verbatim_text": "Điểm a) Sửa đổi: Phạt 2 triệu",
            "contextualized_text": "[Nghị định 100] > [Điều 5]\nĐiểm a) Sửa đổi",
            "metadata": {"fines": {"min_vnd": 2000000}},
            "effective_date": "2020-01-15",
        }
    ]

    req_patch = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_stg_patch",
            "arguments": {
                "doc_code": "100/2019/NĐ-CP",
                "updated_chunks": patch_payload,
            },
        },
    }
    resp_patch = await server.handle_request_dict(req_patch)
    assert resp_patch is not None
    assert resp_patch["result"]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_stg_preview_missing_doc(tmp_path: Path) -> None:
    """Verifies requesting non-existent staging doc returns domain error."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    tools = LegalMCPTools(staging_manager=stg_mgr)
    server = LegalMCPServer(tools=tools)

    req_missing = {
        "jsonrpc": "2.0",
        "id": 13,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_stg_preview",
            "arguments": {"doc_code": "999/2099/NĐ-CP"},
        },
    }
    resp_missing = await server.handle_request_dict(req_missing)
    assert resp_missing is not None
    assert "error" in resp_missing
    assert "does not exist" in resp_missing["error"]["message"]
