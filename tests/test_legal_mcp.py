"""Unit tests for LegalMCPTools and LegalMCPServer JSON-RPC dispatch."""

from __future__ import annotations

import datetime
from pathlib import Path

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
async def test_stg_commit_lifecycle(tmp_path: Path) -> None:
    """Verifies agent commit transitions staging session to AGENT_COMMITTED and preserves file on disk."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    stg_mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    tools = LegalMCPTools(staging_manager=stg_mgr)
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
            "arguments": {"doc_code": "100/2019/NĐ-CP"},
        },
    }
    resp_commit = await server.handle_request_dict(req_commit)
    assert resp_commit is not None
    assert resp_commit["result"]["status"] == "AGENT_COMMITTED"
    assert resp_commit["result"]["total_chunks"] == 1
    assert resp_commit["result"]["total_edges"] == 0
    assert "committed_at" in resp_commit["result"]

    # Verify staging file was PRESERVED on disk (not deleted)
    staging_file = tmp_path / "100_2019_nd_cp.json"
    assert staging_file.exists()

    # Verify session status and mutation history
    loaded = stg_mgr.load_session("100/2019/NĐ-CP")
    assert loaded.status.value == "AGENT_COMMITTED"
    assert loaded.committed_at is not None
    assert len(loaded.mutation_history) >= 2


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


@pytest.mark.asyncio
async def test_stg_commit_cross_document_edge_resolution(tmp_path: Path) -> None:
    """Verifies stg_commit preserves cross-document edges in staging session without DB writes."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    stg_mgr.create_session_from_raw(
        doc_code="123/2021/NĐ-CP",
        title="Nghị định 123",
        raw_text=SAMPLE_TEXT,
        effective_date=datetime.date(2022, 1, 1),
    )

    # Attach cross-document edge pointing to Decree 100
    cross_edge = {
        "source_path": "123_2021_nd_cp.c_ii.a_5.c_3.p_a",
        "target_path": "100_2019_nd_cp.c_ii.a_5.c_3.p_a",
        "relation_type": "MODIFIES_AND_REPLACES",
        "citation_text": "Sửa đổi Điểm a Khoản 3 Điều 5 Nghị định 100",
    }
    tools = LegalMCPTools(staging_manager=stg_mgr)
    await tools.stg_add_edges(doc_code="123/2021/NĐ-CP", edges=[cross_edge])

    # Commit
    res = await tools.stg_commit(doc_code="123/2021/NĐ-CP")
    assert res.status == "AGENT_COMMITTED"
    assert res.total_edges == 1

    session = stg_mgr.load_session("123/2021/NĐ-CP")
    assert session.status.value == "AGENT_COMMITTED"
    assert len(session.edges) == 1


@pytest.mark.asyncio
async def test_stg_commit_rejects_unresolvable_source_path(tmp_path: Path) -> None:
    """Verifies stg_commit raises LegalDomainError when source_path does not exist in staged document."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    stg_mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    bad_edge = {
        "source_path": "100_2019_nd_cp.invalid_clause_path",
        "target_path": "100_2019_nd_cp.c_ii.a_5.c_3.p_a",
        "relation_type": "REFERENCES",
    }
    tools = LegalMCPTools(staging_manager=stg_mgr)
    await tools.stg_add_edges(doc_code="100/2019/NĐ-CP", edges=[bad_edge])

    with pytest.raises(LegalDomainError, match="Invalid edge source path"):
        await tools.stg_commit(doc_code="100/2019/NĐ-CP")


@pytest.mark.asyncio
async def test_stg_preview_pagination_windowing(tmp_path: Path) -> None:
    """Verifies stg_preview respects limit, offset, and computes total_matched and has_more correctly."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    multi_chunk_text = """
Điều 1. Điều 1
1. Khoản 1
2. Khoản 2
3. Khoản 3
4. Khoản 4
5. Khoản 5
"""
    stg_mgr.create_session_from_raw(
        doc_code="TEST_PAGINATION",
        title="Test Pagination",
        raw_text=multi_chunk_text,
        effective_date=datetime.date(2025, 1, 1),
    )

    tools = LegalMCPTools(staging_manager=stg_mgr)

    # Page 1: limit 2, offset 0
    p1 = await tools.stg_preview(doc_code="TEST_PAGINATION", limit=2, offset=0)
    assert p1.total_matched == 5
    assert len(p1.chunks) == 2
    assert p1.has_more is True
    assert p1.offset == 0
    assert p1.limit == 2

    # Page 2: limit 2, offset 2
    p2 = await tools.stg_preview(doc_code="TEST_PAGINATION", limit=2, offset=2)
    assert len(p2.chunks) == 2
    assert p2.has_more is True

    # Page 3: limit 2, offset 4
    p3 = await tools.stg_preview(doc_code="TEST_PAGINATION", limit=2, offset=4)
    assert len(p3.chunks) == 1
    assert p3.has_more is False
