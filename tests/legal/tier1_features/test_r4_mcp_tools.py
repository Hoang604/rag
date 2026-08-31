"""Tier 1: Feature Coverage tests for Requirement 4 (R4) - Production MCP 7-Tool Server."""

from __future__ import annotations

from typing import cast

import pytest

from rag_eval.legal.mcp.server import LegalMCPServer
from rag_eval.legal.mcp.tools import LegalMCPTools
from tests.legal.mocks.mock_db import MockDatabasePool


def _res(r: dict[str, object]) -> dict[str, object]:
    val = r.get("result")
    assert isinstance(val, dict)
    return val


def _err(r: dict[str, object]) -> dict[str, object]:
    val = r.get("error")
    assert isinstance(val, dict)
    return val


@pytest.mark.asyncio
class TestR4MCPServer:
    """Tests JSON-RPC 2.0 interface contracts for all 7 specialized MCP tools directly against LegalMCPServer."""

    @pytest.fixture(autouse=True)
    def _mock_unit_embeddings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mock neural embeddings during MCP tool unit testing."""
        monkeypatch.setattr(
            "rag_eval.legal.ingestion.loader.compute_chunk_embeddings",
            lambda texts, **kwargs: [[0.01] * 384 for _ in texts],
        )

    async def test_tool_1_corpus_validate_returns_valid_contract(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_corpus_validate", {"document_id": "doc_nd100"}
        )
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        assert result["status"] == "success"
        assert result["is_valid"] is True
        assert int(str(result["total_chunks_scanned"])) >= 5

    async def test_tool_2_hybrid_search_executes_dense_and_sparse_fusion(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_hybrid_search",
            {"query": "đèn đỏ ô tô", "limit": 3, "effective_at": "2025-01-01"},
        )
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        results = cast(list[dict[str, object]], result["results"])
        assert len(results) > 0
        assert len(str(results[0]["verbatim_text"])) > 0
        assert str(results[0]["doc_code"]) in ("100/2019/ND-CP", "36/2024/QH15")

    async def test_tool_3_hierarchical_navigate_retrieves_parent_chain(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_hierarchical_navigate",
            {"target_path": "doc_nd100_2019.c2.s1.a5", "direction": "PARENT_CHAIN"},
        )
        assert res["jsonrpc"] == "2.0"
        result = _res(res)
        nodes = cast(list[dict[str, object]], result["nodes"])
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
        result = _res(res)
        paths = cast(list[dict[str, object]], result["traversal_paths"])
        assert len(paths) >= 1
        assert paths[0]["target_doc_code"] == "QCVN 41:2019/BGTVT"

    async def test_tool_6_sign_catalog_lookup_exact_and_fuzzy(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        # Exact lookup
        res_exact = await server.call_tool(
            "mcp_traffic_sign_catalog_lookup", {"sign_code": "P.102"}
        )
        r_exact = _res(res_exact)
        assert str(r_exact["sign_name"]) == "Cấm đi ngược chiều"
        assert int(str(r_exact["total_matches"])) >= 1
        signs_exact = cast(list[dict[str, object]], r_exact["signs"])
        assert len(signs_exact) >= 1
        assert signs_exact[0]["sign_code"] == "P.102"
        pen_refs = signs_exact[0].get("penalty_references")
        assert isinstance(pen_refs, list)
        assert len(pen_refs) > 0

        # Fuzzy lookup (P102 without dot)
        res_fuzzy = await server.call_tool(
            "mcp_traffic_sign_catalog_lookup", {"sign_code": "P102"}
        )
        r_fuzzy = _res(res_fuzzy)
        assert str(r_fuzzy["sign_name"]) == "Cấm đi ngược chiều"
        assert int(str(r_fuzzy["total_matches"])) >= 1
        signs_fuzzy = cast(list[dict[str, object]], r_fuzzy["signs"])
        assert len(signs_fuzzy) >= 1

    async def test_tool_7_knowledge_cache_lifecycle(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        # Query miss
        res_miss = await server.call_tool(
            "mcp_traffic_knowledge_cache_query", {"query_hash": "hash_xyz"}
        )
        r_miss = _res(res_miss)
        assert r_miss["status"] == "miss"
        assert r_miss["cache_hit"] is False
        assert r_miss["cached_entry"] is None

        # Write
        res_write = await server.call_tool(
            "mcp_traffic_knowledge_cache_write",
            {"natural_query": "vượt đèn đỏ", "answer": "Answer text"},
        )
        r_write = _res(res_write)
        assert r_write["status"] == "written"

        # Query hit
        res_hit = await server.call_tool(
            "mcp_traffic_knowledge_cache_query", {"natural_query": "vượt đèn đỏ"}
        )
        r_hit = _res(res_hit)
        assert r_hit["status"] == "hit"
        assert r_hit["cache_hit"] is True
        assert r_hit["cached_entry"] is not None

    async def test_tool_8_verbatim_grep_exact_and_regex_filtering(self) -> None:
        """Verifies verbatim_grep with Trigram GIN simulation and regex."""
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))

        # Substring search
        res_sub = await server.call_tool(
            "mcp_traffic_verbatim_grep",
            {
                "pattern": "đèn đỏ",
                "is_regex": False,
                "limit": 5,
            },
        )
        assert res_sub["jsonrpc"] == "2.0"
        r_sub = _res(res_sub)
        assert r_sub["status"] == "success"
        assert int(str(r_sub["total_hits"])) >= 1
        sub_results = cast(list[dict[str, object]], r_sub["results"])
        matched_chunks = [r for r in sub_results if "đèn đỏ" in str(r["verbatim_text"]).lower()]
        assert len(matched_chunks) >= 1

        # Regex search
        res_reg = await server.call_tool(
            "mcp_traffic_verbatim_grep",
            {
                "pattern": r"vượt.*đèn",
                "is_regex": True,
                "limit": 3,
            },
        )
        assert res_reg["jsonrpc"] == "2.0"
        r_reg = _res(res_reg)
        assert r_reg["status"] == "success"

    async def test_tool_8_verbatim_grep_redos_safety_pre_validation(self) -> None:
        """Verifies Google RE2 ReDoS safety analyzer rejects catastrophic backtracking patterns."""
        from rag_eval.legal.mcp.server import E_AST_GROUNDING_VALIDATION

        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))

        # Nested quantifier attack pattern (a+)+$
        res_attack_1 = await server.call_tool(
            "mcp_traffic_verbatim_grep",
            {
                "pattern": r"(a+)+$",
                "is_regex": True,
            },
        )
        assert "error" in res_attack_1
        err1 = _err(res_attack_1)
        assert err1["code"] == E_AST_GROUNDING_VALIDATION
        assert "redos" in str(err1["message"]).lower()

        # Overlapping alternation attack pattern (a|a)+
        res_attack_2 = await server.call_tool(
            "mcp_traffic_verbatim_grep",
            {
                "pattern": r"((a|a)+)$",
                "is_regex": True,
            },
        )
        assert "error" in res_attack_2
        err2 = _err(res_attack_2)
        assert err2["code"] == E_AST_GROUNDING_VALIDATION

    async def test_tool_9_graph_edge_write_foreign_key_and_upsert(self) -> None:
        """Verifies graph_edge_write persists edges with validation."""
        pool = MockDatabasePool()
        server = LegalMCPServer(LegalMCPTools(pool=pool))

        # Successful graph edge persistence
        res_ok = await server.call_tool(
            "mcp_traffic_graph_edge_write",
            {
                "source_id": "chk_nd100_art5_cl3_pta",
                "relation_type": "REFERENCES_TECHNICAL_STANDARD",
                "target_id": "QCVN 41:2019/BGTVT Điều 10",
                "confidence": 0.95,
            },
        )
        assert res_ok["jsonrpc"] == "2.0"
        r_ok = _res(res_ok)
        assert r_ok["status"] == "success"

    async def test_unknown_method_returns_jsonrpc_32601_error(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool("mcp_non_existent_tool", {})
        err = _err(res)
        assert err["code"] == -32601
        assert "not found" in str(err["message"]).lower()

    async def test_invalid_parameters_returns_jsonrpc_32602_error(self) -> None:
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))
        res = await server.call_tool(
            "mcp_traffic_hybrid_search",
            {"query": "đèn đỏ", "fine_min_vnd": -100},
        )
        err = _err(res)
        assert err["code"] == -32602

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
        r_d6 = _res(res_d6)
        nodes_d6 = cast(list[dict[str, object]], r_d6["nodes"])
        assert len(nodes_d6) > 0
        assert all(str(n["path"]).startswith("doc_nd100_2019.c2.s1.a5") for n in nodes_d6)

        # Depth 3 node in TT31 -> resolves article at depth 2
        res_d3 = await server.call_tool(
            "mcp_traffic_hierarchical_navigate",
            {
                "target_path": "doc_tt31_2019.a6.c1",
                "direction": "FULL_ARTICLE",
            },
        )
        assert res_d3["jsonrpc"] == "2.0"
        r_d3 = _res(res_d3)
        nodes_d3 = cast(list[dict[str, object]], r_d3["nodes"])
        assert len(nodes_d3) > 0
        assert all(str(n["path"]).startswith("doc_tt31_2019.a6") for n in nodes_d3)

    async def test_f27_expanded_in_memory_sign_catalog_fallback(self) -> None:
        """F-27: Verifies all 13 standard signs exist in sign catalog table."""
        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))

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
            result = _res(res)
            assert result["status"] == "success", f"Sign {code} lookup failed: {result}"
            assert int(str(result["total_matches"])) >= 1
            signs_list = cast(list[dict[str, object]], result["signs"])
            assert len(signs_list) >= 1
            assert expected_name_part.lower() in str(result["sign_name"]).lower()
            pen_refs_fallback = signs_list[0].get("penalty_references")
            assert isinstance(pen_refs_fallback, list)

    async def test_f32_operational_mock_fallback_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """F-32: Verifies connection failure always fails fast with -32001 StorageConnectionError."""
        from unittest.mock import AsyncMock, patch

        from rag_eval.legal.mcp.server import E_STORAGE_CONNECTION

        tools_prod = LegalMCPTools(pool=None)
        server_prod = LegalMCPServer(tools_prod)

        with patch("rag_eval.legal.mcp.tools.get_db_pool", new_callable=AsyncMock) as mock_get_pool:
            mock_get_pool.side_effect = RuntimeError("PostgreSQL connection refused on port 5432")
            res_fail = await server_prod.call_tool("mcp_traffic_corpus_validate", {"document_id": "doc_nd100"})
            assert "error" in res_fail
            err = _err(res_fail)
            assert err["code"] == E_STORAGE_CONNECTION
            assert "connection" in str(err["message"]).lower()

    async def test_f33_vector_float_sanitization_rejects_nan_and_inf(self) -> None:
        """F-33: Verifies NaN and Inf vector inputs are rejected with VectorDimensionMismatchError (-32003)."""
        from rag_eval.legal.mcp.server import E_VECTOR_DIMENSION_MISMATCH

        server = LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))

        # 1. NaN in knowledge_cache_query query_vector
        res_cache_nan = await server.call_tool(
            "mcp_traffic_knowledge_cache_query",
            {"natural_query": "vượt đèn đỏ", "query_vector": [float("nan")] * 384},
        )
        assert "error" in res_cache_nan
        err1 = _err(res_cache_nan)
        assert err1["code"] == E_VECTOR_DIMENSION_MISMATCH
        assert "non-finite" in str(err1["message"]).lower()

        # 2. Inf in knowledge_cache_query query_vector
        res_cache_inf = await server.call_tool(
            "mcp_traffic_knowledge_cache_query",
            {"natural_query": "vượt đèn đỏ", "query_vector": [float("inf")] * 384},
        )
        assert "error" in res_cache_inf
        err2 = _err(res_cache_inf)
        assert err2["code"] == E_VECTOR_DIMENSION_MISMATCH
