"""Unit tests for LegalMCPTools and LegalMCPServer JSON-RPC dispatch."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag_eval.legal.ingestion.staging import StagingManager
from rag_eval.legal.mcp.server import (
    LegalMCPServer,
    create_legal_mcp_server,
)
from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.schemas import LegalDomainError

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
            "path": "doc_100_2019_nd_cp.c_ii.a_5.c_3.p_a",
            "verbatim_text": "Điểm a) Điều khiển xe chạy quá tốc độ từ 05 km/h đến dưới 10 km/h",
            "contextualized_text": "[Nghị định 100] > [Điều 5]\nĐiểm a) Điều khiển xe chạy quá tốc độ từ 05 km/h đến dưới 10 km/h",
            "metadata": json.dumps({"fines": {"min_vnd": 800000, "max_vnd": 1000000}}),
            "effective_date": "2020-01-15",
            "expiration_date": None,
            "rrf_score": 0.032,
            "similarity_score": 0.95,
            "id": "88888888-4444-4444-4444-121212121212",
            "edge_id": "99999999-5555-5555-5555-131313131313",
            "source_chunk_id": "88888888-4444-4444-4444-121212121212",
            "target_chunk_id": None,
            "target_external_ref": "Điều 12 Luật GTĐB",
            "relation_type": "REFERENCES",
            "citation_text": "theo Điều 12",
            "depth": 1,
            "rel_depth": 2,
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
    """Verifies MCP server JSON-RPC initialize handshake contains server instructions with dynamic date."""
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
    assert "instructions" in resp["result"]
    assert "Leaf Nodes" in resp["result"]["instructions"]
    assert "TÍNH ĐẾN:" in resp["result"]["instructions"]


@pytest.mark.asyncio
async def test_mcp_server_instructions_on_instance() -> None:
    """Verifies that MCPServer instance preserves instructions in internal configuration."""
    server = create_legal_mcp_server()
    assert server.instructions is not None
    assert "Leaf Nodes" in server.instructions
    assert "TÍNH ĐẾN:" in server.instructions


@pytest.mark.asyncio
async def test_build_dynamic_corpus_manifest_live_statuses(mock_pool: Any) -> None:
    """Verifies dynamic manifest accurately categorizes ACTIVE, PARTIALLY_MODIFIED, and EXPIRED statuses with custom dates."""
    # Custom rows representing active, partially modified, and expired documents
    mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
    mock_conn.fetch.return_value = [
        {
            "doc_code": "100/2019/NĐ-CP",
            "title": "Nghị định quy định xử phạt vi phạm hành chính",
            "effective_date": datetime.date(2020, 1, 15),
            "expiration_date": None,
            "status": "PARTIALLY_MODIFIED",
            "modifying_doc_code": "123/2021/NĐ-CP",
        },
        {
            "doc_code": "123/2021/NĐ-CP",
            "title": "Nghị định sửa đổi bổ sung một số điều",
            "effective_date": datetime.date(2022, 1, 1),
            "expiration_date": None,
            "status": "ACTIVE",
            "modifying_doc_code": None,
        },
        {
            "doc_code": "46/2016/NĐ-CP",
            "title": "Nghị định quy định xử phạt giao thông đường bộ",
            "effective_date": datetime.date(2016, 8, 1),
            "expiration_date": datetime.date(2020, 1, 15),
            "status": "EXPIRED",
            "modifying_doc_code": "100/2019/NĐ-CP",
        },
    ]

    tools = LegalMCPTools(pool=mock_pool)
    test_date = datetime.date(2026, 9, 1)
    manifest = await tools.build_dynamic_corpus_manifest(as_of_date=test_date)

    assert "TÍNH ĐẾN: 01/09/2026" in manifest
    assert "[100/2019/NĐ-CP]" in manifest
    assert "[CÒN HIỆU LỰC MỘT PHẦN] (Sửa đổi, bổ sung bởi: `[123/2021/NĐ-CP]`)" in manifest
    assert "[123/2021/NĐ-CP]" in manifest
    assert "[CÒN HIỆU LỰC TOÀN BỘ]" in manifest
    assert "[46/2016/NĐ-CP]" in manifest
    assert "[HẾT HIỆU LỰC] (Thay thế bởi: `[100/2019/NĐ-CP]`)" in manifest


@pytest.mark.asyncio
async def test_mcp_server_tools_schema_rich_descriptions() -> None:
    """Verifies all 10 tools have comprehensive Vietnamese affirmative descriptions, examples, and no leaky dense_vector."""
    server = create_legal_mcp_server()
    tools = await server.list_tools()
    tool_dict = {t.name: t for t in tools}

    assert len(tool_dict) == 10
    hs_tool = tool_dict["mcp_traffic_hybrid_search"]
    assert "Truy xuất các điều khoản quy định mức xử phạt" in (hs_tool.description or "")
    # Invariant: dense_vector must NOT be exposed as an input argument for LLM
    assert "dense_vector" not in hs_tool.input_schema["properties"]
    assert "query" in hs_tool.input_schema["properties"]
    assert "Câu hỏi bằng ngôn ngữ tự nhiên" in hs_tool.input_schema["properties"]["query"]["description"]


@pytest.mark.asyncio
async def test_mcp_tools_affirmative_contracts_zero_negation() -> None:
    """Verifies all tool descriptions use affirmative framing without negative shouting."""
    server = create_legal_mcp_server()
    tools = await server.list_tools()

    for t in tools:
        desc = t.description or ""
        assert "DO NOT USE" not in desc
        assert "NEVER" not in desc
        assert len(desc) > 20


@pytest.mark.asyncio
async def test_mcp_hybrid_search_dispatch_natural_query_only(mock_pool: Any) -> None:
    """Verifies calling hybrid_search with only natural language query executes cleanly."""
    tools = LegalMCPTools(pool=mock_pool)
    server = LegalMCPServer(tools=tools)

    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_hybrid_search",
            "arguments": {"query": "vượt quá tốc độ 10 km/h xe ô tô", "limit": 5},
        },
    }
    resp = await server.handle_request_dict(req)
    assert resp is not None
    assert "result" in resp
    assert resp["result"]["total_hits"] >= 1
    hit = resp["result"]["hits"][0]
    assert hit["doc_code"] == "100/2019/NĐ-CP"


@pytest.mark.asyncio
async def test_mcp_temporal_date_flexible_formats(mock_pool: Any) -> None:
    """Verifies temporal violation date accepts flexible Vietnamese statutory date strings."""
    tools = LegalMCPTools(pool=mock_pool)
    res = await tools.hybrid_search(
        query="chạy quá tốc độ",
        temporal_violation_date="ngày 15 tháng 01 năm 2020",
    )
    assert res.temporal_as_of == "2020-01-15"


@pytest.mark.asyncio
async def test_hybrid_search_null_vector_isolation(mock_pool: Any) -> None:
    """Verifies that passing dense_vector=None executes pure sparse search without errors."""
    tools = LegalMCPTools(pool=mock_pool)
    res = await tools.hybrid_search(query="vượt đèn đỏ", dense_vector=None)
    assert res.total_hits >= 1
    assert res.hits[0].score > 0.0


@pytest.mark.asyncio
async def test_hybrid_search_statutory_citation_exact_match(mock_pool: Any) -> None:
    """Verifies querying statutory citations with slashes and units preserves raw text."""
    tools = LegalMCPTools(pool=mock_pool)
    res = await tools.hybrid_search(query="Nghị định 100/2019/NĐ-CP tốc độ 05 km/h", dense_vector=None)
    assert res.total_hits >= 1
    assert res.hits[0].doc_code == "100/2019/NĐ-CP"
    assert "km/h" in res.hits[0].verbatim_text


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
    assert resp["result"]["matches"][0]["score"] >= 0.9


@pytest.mark.asyncio
async def test_hierarchical_navigate_dynamic_article_root(mock_pool: Any) -> None:
    """Verifies hierarchical_navigate resolves dynamic Article root and relative depth."""
    tools = LegalMCPTools(pool=mock_pool)
    res = await tools.hierarchical_navigate(
        path="doc_100.c_ii.s_1.a_5.c_1.p_a", direction="FULL_ARTICLE"
    )
    assert res.total_nodes >= 1
    assert res.nodes[0].relative_depth >= 0


@pytest.mark.asyncio
async def test_mcp_hierarchical_navigate_invalid_direction_rejected(mock_pool: Any) -> None:
    """Verifies passing invalid direction returns descriptive LegalDomainError."""
    tools = LegalMCPTools(pool=mock_pool)
    with pytest.raises(LegalDomainError, match="Invalid navigation direction"):
        await tools.hierarchical_navigate(path="doc_100.a_5", direction="INVALID_DIRECTION")


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
    assert not (tmp_path / "100_2019_nd_cp.json").exists()


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
            "path": "100_2019_nd_cp.c_ii.a_5.c_3.p_a",
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


@pytest.mark.asyncio
async def test_official_mcpserver_sdk_tools_list() -> None:
    """Verifies that the official MCPServer instance from the SDK exposes all 10 tools."""
    server = create_legal_mcp_server()
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}
    assert len(tool_names) == 10
    assert "mcp_traffic_hybrid_search" in tool_names
    assert "mcp_traffic_stg_commit" in tool_names
