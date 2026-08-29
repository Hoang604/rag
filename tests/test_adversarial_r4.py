"""Adversarial stress-testing suite for Milestone R4 (MCP Server & Tools).

Tests:
1. Protocol conformance: JSON-RPC 2.0 error codes (-32700, -32600, -32601, -32602, -32603, -32008).
2. Schema discovery: tools/list verification across all 7 tools (+ write tool).
3. Lifecycle methods: initialize handshake, notifications/initialized, ping.
4. Input validation & boundary stress: missing required parameters, extra forbidden parameters,
   type violations, boundary constraints (ge/le), malformed JSON strings, SQL injection strings,
   and concurrent load under MockDatabasePool.
5. Stdio JSON-RPC stream parse error (-32700) handling.
"""

from __future__ import annotations

import asyncio
import io
import json
from unittest.mock import patch

import pytest

from rag_eval.legal.mcp.server import (
    RPC_INVALID_PARAMS,
    RPC_INVALID_REQUEST,
    RPC_METHOD_NOT_FOUND,
    RPC_PARSE_ERROR,
    LegalMCPServer,
)
from rag_eval.legal.mcp.tools import LegalMCPTools
from tests.legal.mocks.mock_db import MockDatabasePool


@pytest.fixture
def mcp_server() -> LegalMCPServer:
    """Fixture providing LegalMCPServer initialized with MockDatabasePool."""
    return LegalMCPServer(LegalMCPTools(pool=MockDatabasePool()))


# ==============================================================================
# 1. Lifecycle & Handshake Conformance Tests
# ==============================================================================


@pytest.mark.asyncio
class TestMCPLifecycleConformance:
    """Verifies MCP handshake, ping, notifications, and schema discovery."""

    async def test_initialize_negotiates_correct_protocol_version(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": "init-req-1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "adversarial-tester", "version": "9.9.9"},
            },
        }
        resp = await mcp_server.handle_request(req)
        assert resp is not None
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == "init-req-1"
        assert "result" in resp
        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "vietnamese-traffic-law-mcp"
        assert result["capabilities"]["tools"]["listChanged"] is False

    async def test_notifications_initialized_emits_no_packet(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        resp = await mcp_server.handle_request(req)
        assert resp is None

    async def test_ping_returns_empty_dict(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": 999,
            "method": "ping",
            "params": {},
        }
        resp = await mcp_server.handle_request(req)
        assert resp is not None
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 999
        assert resp["result"] == {}

    async def test_tools_list_manifests_integrity(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": "tools-list-id",
            "method": "tools/list",
            "params": {},
        }
        resp = await mcp_server.handle_request(req)
        assert resp is not None
        assert resp["jsonrpc"] == "2.0"
        tools = resp["result"]["tools"]
        assert len(tools) == 8  # 7 specialized query tools + knowledge_cache_write

        expected_tools = {
            "mcp_traffic_corpus_validate",
            "mcp_traffic_hybrid_search",
            "mcp_traffic_hierarchical_navigate",
            "mcp_traffic_graph_traverse",
            "mcp_traffic_scope_override_detect",
            "mcp_traffic_sign_catalog_lookup",
            "mcp_traffic_knowledge_cache_query",
            "mcp_traffic_knowledge_cache_write",
        }
        discovered_tools = {t["name"] for t in tools}
        assert expected_tools == discovered_tools

        for t in tools:
            assert "description" in t and len(t["description"]) > 10
            schema = t["inputSchema"]
            assert schema["type"] == "object"
            assert "properties" in schema


# ==============================================================================
# 2. Adversarial Protocol & Error Handling (-32700, -32600, -32601, -32602)
# ==============================================================================


@pytest.mark.asyncio
class TestAdversarialProtocolErrors:
    """Stress tests protocol error handling with invalid, malformed, or corrupt payloads."""

    async def test_invalid_request_not_a_dict(
        self, mcp_server: LegalMCPServer
    ) -> None:
        invalid_payloads: list[object] = [
            "raw string payload",
            ["list", "instead", "of", "dict"],
            12345,
            True,
            None,
        ]
        for p in invalid_payloads:
            resp = await mcp_server.handle_request(p)
            assert resp is not None
            assert resp["jsonrpc"] == "2.0"
            assert resp["error"]["code"] == RPC_INVALID_REQUEST

    async def test_invalid_request_missing_or_wrong_jsonrpc_version(
        self, mcp_server: LegalMCPServer
    ) -> None:
        bad_versions = [
            {"id": 1, "method": "ping"},  # missing jsonrpc
            {"jsonrpc": "1.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.1", "id": 1, "method": "ping"},
            {"jsonrpc": 2.0, "id": 1, "method": "ping"},  # float instead of string
        ]
        for p in bad_versions:
            resp = await mcp_server.handle_request(p)
            assert resp is not None
            assert resp["jsonrpc"] == "2.0"
            assert resp["error"]["code"] == RPC_INVALID_REQUEST

    async def test_invalid_request_missing_or_empty_method(
        self, mcp_server: LegalMCPServer
    ) -> None:
        bad_methods = [
            {"jsonrpc": "2.0", "id": 1},  # missing method
            {"jsonrpc": "2.0", "id": 1, "method": ""},
            {"jsonrpc": "2.0", "id": 1, "method": 123},
            {"jsonrpc": "2.0", "id": 1, "method": None},
        ]
        for p in bad_methods:
            resp = await mcp_server.handle_request(p)
            assert resp is not None
            assert resp["jsonrpc"] == "2.0"
            assert resp["error"]["code"] == RPC_INVALID_REQUEST

    async def test_invalid_params_not_a_json_object(
        self, mcp_server: LegalMCPServer
    ) -> None:
        bad_params = [
            {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": "string_params"},
            {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": [1, 2, 3]},
            {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": 42},
        ]
        for p in bad_params:
            resp = await mcp_server.handle_request(p)
            assert resp is not None
            assert resp["jsonrpc"] == "2.0"
            assert resp["error"]["code"] == RPC_INVALID_PARAMS

    async def test_method_not_found_code_32601(
        self, mcp_server: LegalMCPServer
    ) -> None:
        unknown_methods = [
            "non_existent_method",
            "mcp_traffic_non_existent",
            "admin/shutdown",
            "system_command_exec",
        ]
        for m in unknown_methods:
            resp = await mcp_server.handle_request(
                {"jsonrpc": "2.0", "id": f"err-{m}", "method": m, "params": {}}
            )
            assert resp is not None
            assert resp["jsonrpc"] == "2.0"
            assert resp["error"]["code"] == RPC_METHOD_NOT_FOUND

    async def test_tools_call_missing_name_returns_32602(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"arguments": {"query": "test"}},  # missing 'name'
        }
        resp = await mcp_server.handle_request(req)
        assert resp is not None
        assert resp["error"]["code"] == RPC_INVALID_PARAMS
        assert "Missing 'name'" in resp["error"]["message"]

    async def test_tools_call_invalid_arguments_type_returns_32602(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_hybrid_search",
                "arguments": ["not", "an", "object"],
            },
        }
        resp = await mcp_server.handle_request(req)
        assert resp is not None
        assert resp["error"]["code"] == RPC_INVALID_PARAMS
        assert "must be an object" in resp["error"]["message"]


# ==============================================================================
# 3. Adversarial Schema Validation Stress (-32602)
# ==============================================================================


@pytest.mark.asyncio
class TestAdversarialSchemaValidation:
    """Stress tests Pydantic schema validation: required fields, bounds, extra forbidden fields."""

    async def test_corpus_validate_missing_required_document_id(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": "cv-1",
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_corpus_validate",
                "arguments": {"check_orphaned_points": True},  # missing document_id
            },
        }
        resp = await mcp_server.handle_request(req)
        assert resp is not None
        assert resp["error"]["code"] == RPC_INVALID_PARAMS
        assert "data" in resp["error"]

    async def test_corpus_validate_extra_forbidden_fields(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": "cv-2",
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_corpus_validate",
                "arguments": {
                    "document_id": "100/2019/ND-CP",
                    "unexpected_extra_field": "exploit_attempt",
                },
            },
        }
        resp = await mcp_server.handle_request(req)
        assert resp is not None
        assert resp["error"]["code"] == RPC_INVALID_PARAMS

    async def test_hybrid_search_missing_required_query(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": "hs-1",
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_hybrid_search",
                "arguments": {"limit": 10},  # missing query
            },
        }
        resp = await mcp_server.handle_request(req)
        assert resp is not None
        assert resp["error"]["code"] == RPC_INVALID_PARAMS

    async def test_hybrid_search_boundary_limits_ge_and_le(
        self, mcp_server: LegalMCPServer
    ) -> None:
        # limit < 1 (ge=1 violated)
        req_low = {
            "jsonrpc": "2.0",
            "id": "hs-low",
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_hybrid_search",
                "arguments": {"query": "vượt đèn đỏ", "limit": 0},
            },
        }
        resp_low = await mcp_server.handle_request(req_low)
        assert resp_low is not None
        assert resp_low["error"]["code"] == RPC_INVALID_PARAMS

        # limit > 50 (le=50 violated)
        req_high = {
            "jsonrpc": "2.0",
            "id": "hs-high",
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_hybrid_search",
                "arguments": {"query": "vượt đèn đỏ", "limit": 51},
            },
        }
        resp_high = await mcp_server.handle_request(req_high)
        assert resp_high is not None
        assert resp_high["error"]["code"] == RPC_INVALID_PARAMS

        # negative fine_min_vnd (ge=0 violated)
        req_neg_fine = {
            "jsonrpc": "2.0",
            "id": "hs-neg-fine",
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_hybrid_search",
                "arguments": {"query": "vượt đèn đỏ", "fine_min_vnd": -1000},
            },
        }
        resp_neg = await mcp_server.handle_request(req_neg_fine)
        assert resp_neg is not None
        assert resp_neg["error"]["code"] == RPC_INVALID_PARAMS

    async def test_hierarchical_navigate_invalid_direction_literal(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req = {
            "jsonrpc": "2.0",
            "id": "hn-1",
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_hierarchical_navigate",
                "arguments": {
                    "target_path": "doc_nd100_2019.c2.s1.a5",
                    "direction": "INVALID_DIRECTION_STRING",
                },
            },
        }
        resp = await mcp_server.handle_request(req)
        assert resp is not None
        assert resp["error"]["code"] == RPC_INVALID_PARAMS

    async def test_graph_traverse_depth_bounds(
        self, mcp_server: LegalMCPServer
    ) -> None:
        # max_depth < 1
        req_0 = {
            "jsonrpc": "2.0",
            "id": "gt-0",
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_graph_traverse",
                "arguments": {
                    "start_chunk_id": "chk_nd100_art5_cl3_pta",
                    "max_depth": 0,
                },
            },
        }
        resp_0 = await mcp_server.handle_request(req_0)
        assert resp_0 is not None
        assert resp_0["error"]["code"] == RPC_INVALID_PARAMS

        # max_depth > 4
        req_5 = {
            "jsonrpc": "2.0",
            "id": "gt-5",
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_graph_traverse",
                "arguments": {
                    "start_chunk_id": "chk_nd100_art5_cl3_pta",
                    "max_depth": 5,
                },
            },
        }
        resp_5 = await mcp_server.handle_request(req_5)
        assert resp_5 is not None
        assert resp_5["error"]["code"] == RPC_INVALID_PARAMS

    async def test_sign_catalog_lookup_limit_bounds(
        self, mcp_server: LegalMCPServer
    ) -> None:
        req_high = {
            "jsonrpc": "2.0",
            "id": "sig-high",
            "method": "tools/call",
            "params": {
                "name": "mcp_traffic_sign_catalog_lookup",
                "arguments": {"sign_code": "P.102", "limit": 25},  # le=20 violated
            },
        }
        resp_high = await mcp_server.handle_request(req_high)
        assert resp_high is not None
        assert resp_high["error"]["code"] == RPC_INVALID_PARAMS


# ==============================================================================
# 4. Stress Inputs: Unicode, Long Strings, SQL Injection, Special Characters
# ==============================================================================


@pytest.mark.asyncio
class TestStressInputsAndSecurity:
    """Stress tests server behavior against SQL injection, long queries, and complex Unicode."""

    async def test_sql_injection_resilience_in_hybrid_search(
        self, mcp_server: LegalMCPServer
    ) -> None:
        sqli_queries = [
            "'; DROP TABLE legal_chunks; --",
            "' UNION SELECT * FROM users --",
            "1' OR '1'='1",
            "'; SELECT pg_sleep(5); --",
        ]
        for q in sqli_queries:
            resp = await mcp_server.call_tool(
                "mcp_traffic_hybrid_search",
                {"query": q, "limit": 5},
            )
            assert resp["jsonrpc"] == "2.0"
            assert "result" in resp
            assert resp["result"]["status"] == "success"

    async def test_extreme_length_vietnamese_query(
        self, mcp_server: LegalMCPServer
    ) -> None:
        long_query = "Người điều khiển xe ô tô chạy quá tốc độ trên đường cao tốc " * 200
        resp = await mcp_server.call_tool(
            "mcp_traffic_hybrid_search",
            {"query": long_query, "limit": 5},
        )
        assert resp["jsonrpc"] == "2.0"
        assert resp["result"]["status"] == "success"

    async def test_complex_unicode_and_vietnamese_diacritics(
        self, mcp_server: LegalMCPServer
    ) -> None:
        unicode_queries = [
            "Ô tô 🚗 vi phạm nồng độ cồn mức 3 > 80mg/100ml máu 🍺",
            "§ 5, Điều 5, Khoản 3, Điểm a: Phạt tiền từ 800.000 đồng",
            "Xe cứu thương 🚑 đang làm nhiệm vụ khẩn cấp có tín hiệu còi đèn",
            "Biển báo P.102 ⛔ vs Hiệu lệnh Cảnh sát giao thông 👮",
        ]
        for uq in unicode_queries:
            resp = await mcp_server.call_tool(
                "mcp_traffic_hybrid_search",
                {"query": uq, "limit": 3},
            )
            assert resp["jsonrpc"] == "2.0"
            assert resp["result"]["status"] == "success"

    async def test_concurrent_load_burst(
        self, mcp_server: LegalMCPServer
    ) -> None:
        """Fires 50 concurrent requests simultaneously to verify race conditions & stability."""
        tasks = [
            mcp_server.call_tool(
                "mcp_traffic_hybrid_search",
                {"query": f"truy vấn song song {i}", "limit": 2},
            )
            for i in range(50)
        ]
        results = await asyncio.gather(*tasks)
        assert len(results) == 50
        for r in results:
            assert r["jsonrpc"] == "2.0"
            assert r["result"]["status"] == "success"


# ==============================================================================
# 5. Stdio JSON-RPC Stream Parse Error (-32700) Testing
# ==============================================================================


@pytest.mark.asyncio
class TestStdioStreamParseErrors:
    """Verifies that malformed JSON on Stdio triggers RPC_PARSE_ERROR (-32700)."""

    async def test_stdio_handles_malformed_json_and_valid_requests(
        self, mcp_server: LegalMCPServer
    ) -> None:
        # Simulate lines passed into stdin stream
        input_lines = [
            b"not a valid json\n",
            b"\n",  # empty line
            b'{"jsonrpc": "2.0", "id": "p1", "method": "ping", "params": {}}\n',
            b'{"malformed": "json"\n',  # missing closing brace
        ]

        reader = asyncio.StreamReader()
        for line in input_lines:
            reader.feed_data(line)
        reader.feed_eof()

        captured_stdout = io.StringIO()

        with patch("sys.stdout", captured_stdout):
            # Run the message loop directly from reader
            while True:
                line_bytes = await reader.readline()
                if not line_bytes:
                    break
                line_str = line_bytes.decode("utf-8").strip()
                if not line_str:
                    continue

                try:
                    payload = json.loads(line_str)
                except (json.JSONDecodeError, UnicodeDecodeError) as err:
                    err_resp = mcp_server._error_response(
                        None, RPC_PARSE_ERROR, f"Parse error: {err}"
                    )
                    captured_stdout.write(json.dumps(err_resp) + "\n")
                    continue

                response = await mcp_server.handle_request(payload)
                if response is not None:
                    captured_stdout.write(
                        json.dumps(response, ensure_ascii=False) + "\n"
                    )

        output_lines = [
            line for line in captured_stdout.getvalue().strip().split("\n") if line
        ]
        assert len(output_lines) == 3

        # 1st line: Parse Error -32700
        res1 = json.loads(output_lines[0])
        assert res1["error"]["code"] == RPC_PARSE_ERROR
        assert res1["id"] is None

        # 2nd line: Ping Success
        res2 = json.loads(output_lines[1])
        assert res2["id"] == "p1"
        assert res2["result"] == {}

        # 3rd line: Parse Error -32700
        res3 = json.loads(output_lines[2])
        assert res3["error"]["code"] == RPC_PARSE_ERROR
        assert res3["id"] is None


# ==============================================================================
# 6. Domain Error Hierarchy & Propagation (-32001..-32008) (F-13, F-14)
# ==============================================================================


@pytest.mark.asyncio
class TestDomainErrorHierarchyAndPropagation:
    """Stress tests LegalDomainError hierarchy and database failure propagation."""

    async def test_domain_error_hierarchy_codes_and_payloads(
        self, mcp_server: LegalMCPServer
    ) -> None:
        from rag_eval.legal.mcp.server import (
            ASTGroundingValidationError,
            CorpusNotFoundError,
            HierarchyNavigationError,
            KnowledgeCacheMissError,
            PrecedenceConflictError,
            StatementTimeoutError,
            StorageConnectionError,
            VectorDimensionMismatchError,
        )

        domain_errors = [
            (StorageConnectionError("DB connection lost", data={"host": "pg16"}), -32001),
            (CorpusNotFoundError("Document not found", data={"doc": "999"}), -32002),
            (VectorDimensionMismatchError("Dim mismatch: expected 384, got 1536"), -32003),
            (HierarchyNavigationError("Invalid path syntax", data={"path": "bad..path"}), -32004),
            (KnowledgeCacheMissError("Cache key expired"), -32005),
            (PrecedenceConflictError("Conflict between rules"), -32006),
            (ASTGroundingValidationError("AST parsing failed"), -32007),
            (StatementTimeoutError("Query exceeded 5000ms"), -32008),
        ]

        for err_instance, expected_code in domain_errors:
            with patch.object(mcp_server.tools, "hybrid_search", side_effect=err_instance):
                resp = await mcp_server.call_tool(
                    "mcp_traffic_hybrid_search", {"query": "test query"}
                )
                assert resp["jsonrpc"] == "2.0"
                assert "error" in resp
                assert resp["error"]["code"] == expected_code
                assert resp["error"]["message"] == err_instance.message
                if err_instance.data:
                    assert resp["error"]["data"] == err_instance.data

    async def test_database_postgres_error_propagation_not_swallowed(self) -> None:
        """Verifies asyncpg.PostgresError is never swallowed into fake success results."""
        from unittest.mock import AsyncMock, MagicMock

        import asyncpg

        mock_conn = AsyncMock()
        mock_tx = MagicMock()
        mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx.__aexit__ = AsyncMock(return_value=None)
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        mock_conn.execute.side_effect = asyncpg.PostgresError("connection closed unexpectedly")
        mock_conn.fetch.side_effect = asyncpg.PostgresError("relation does not exist")
        mock_conn.fetchrow.side_effect = asyncpg.PostgresError("syntax error in SQL")

        mock_pool = MagicMock(spec=asyncpg.Pool)
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        tools = LegalMCPTools(pool=mock_pool)
        server = LegalMCPServer(tools=tools)

        # 1. hybrid_search must raise or return error -32001
        res = await server.call_tool("mcp_traffic_hybrid_search", {"query": "đèn đỏ"})
        assert "error" in res
        assert res["error"]["code"] == -32001

        # 2. hierarchical_navigate must return error
        res_nav = await server.call_tool(
            "mcp_traffic_hierarchical_navigate",
            {"target_path": "doc_nd100_2019.c2.s1.a5", "direction": "PARENT_CHAIN"},
        )
        assert "error" in res_nav
        assert res_nav["error"]["code"] in (-32001, -32004)

        # 3. graph_traverse must return error -32001
        res_gt = await server.call_tool(
            "mcp_traffic_graph_traverse", {"start_chunk_id": "c1a2b3c4-d5e6-7f8a-9b0c-123456789abc"}
        )
        assert "error" in res_gt
        assert res_gt["error"]["code"] == -32001

