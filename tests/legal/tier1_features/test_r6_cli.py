from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from rag_eval.cli import app
from tests.legal.runners import LegalE2ETestRunner


class TestR6CLIAndQA:
    """Tests CLI execution schemas, legal migrations, ingestion, server, headless tools, and end-to-end querying."""

    @pytest.fixture(autouse=True)
    def _mock_unit_embeddings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mock neural embeddings during CLI unit testing to eliminate model loading overhead."""
        monkeypatch.setattr(
            "rag_eval.legal.ingestion.loader.compute_chunk_embeddings",
            lambda texts, **kwargs: [[0.01] * 384 for _ in texts],
        )

    @pytest.mark.asyncio
    async def test_legal_e2e_runner_executes_query_successfully(self) -> None:
        runner = LegalE2ETestRunner()
        result = await runner.execute_e2e_query("Không chấp hành hiệu lệnh đèn tín hiệu giao thông xe ô tô")
        assert len(result["retrieved_matches"]) > 0
        top = result["retrieved_matches"][0]
        assert top["min_fine_vnd"] == 800000
        assert top["max_fine_vnd"] == 1000000
        assert "100/2019/ND-CP" in top["doc_code"]

    @pytest.mark.asyncio
    async def test_legal_e2e_runner_traversal_paths_populated(self) -> None:
        runner = LegalE2ETestRunner()
        result = await runner.execute_e2e_query("xe máy đi ngược chiều đường một chiều")
        assert len(result["retrieved_matches"]) > 0
        top_match = result["retrieved_matches"][0]
        assert top_match["min_fine_vnd"] == 4000000
        assert top_match["max_fine_vnd"] == 5000000
        assert "c8.p_a" in top_match["path"]


    def test_cli_legal_ingest_dry_run(self, tmp_path: Path) -> None:
        runner = CliRunner()
        doc_file = tmp_path / "sample_law.txt"
        doc_file.write_text(
            "Điều 5. Xử phạt người điều khiển xe ô tô\n"
            "1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với người điều khiển xe ô tô thực hiện một trong các hành vi vi phạm sau đây:\n"
            "a) Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường;\n",
            encoding="utf-8",
        )

        res = runner.invoke(
            app,
            [
                "legal-ingest",
                "--file",
                str(doc_file),
                "--doc-code",
                "100/2019/ND-CP",
                "--doc-type",
                "NGHI_DINH",
                "--no-embed",
            ],
        )
        assert res.exit_code == 0
        assert "Ingestion successful" in res.stdout

    def test_cli_legal_query_positional(self) -> None:
        runner = CliRunner()
        res = runner.invoke(app, ["legal-query", "Vượt đèn đỏ xe ô tô phạt bao nhiêu?"])
        assert res.exit_code == 0
        assert "Traffic Law MCP Hybrid Search" in res.stdout

    def test_cli_legal_query_flag_short(self) -> None:
        runner = CliRunner()
        res = runner.invoke(app, ["legal-query", "-q", "Vượt đèn đỏ xe ô tô phạt bao nhiêu?"])
        assert res.exit_code == 0
        assert "Traffic Law MCP Hybrid Search" in res.stdout

    def test_cli_legal_query_flag_long(self) -> None:
        runner = CliRunner()
        res = runner.invoke(app, ["legal-query", "--query", "Vượt đèn đỏ xe ô tô phạt bao nhiêu?"])
        assert res.exit_code == 0
        assert "Traffic Law MCP Hybrid Search" in res.stdout

    def test_cli_legal_query_json_format(self) -> None:
        runner = CliRunner()
        res = runner.invoke(
            app,
            ["legal-query", "-q", "Vượt đèn đỏ xe ô tô phạt bao nhiêu?", "--format", "json"],
        )
        assert res.exit_code == 0
        parsed = cast(dict[str, object], json.loads(res.stdout))
        assert "results" in parsed

    def test_cli_legal_query_output_file(self, tmp_path: Path) -> None:
        runner = CliRunner()
        out_file = tmp_path / "query_trace.json"
        res = runner.invoke(
            app,
            [
                "legal-query",
                "-q",
                "Vượt đèn đỏ xe ô tô phạt bao nhiêu?",
                "--output",
                str(out_file),
            ],
        )
        assert res.exit_code == 0
        assert out_file.exists()
        parsed = cast(dict[str, object], json.loads(out_file.read_text(encoding="utf-8")))
        assert "results" in parsed

    def test_cli_legal_query_missing_query(self) -> None:
        runner = CliRunner()
        res = runner.invoke(app, ["legal-query"])
        assert res.exit_code != 0
        assert "Missing query" in res.stdout

    def test_cli_legal_query_invalid_format(self) -> None:
        runner = CliRunner()
        res = runner.invoke(
            app,
            ["legal-query", "-q", "Test query", "--format", "unsupported_fmt"],
        )
        assert res.exit_code != 0
        assert "Unknown format" in res.stdout

    # --------------------------------------------------------------------------
    # Headless MCP Tool Runner (rag-eval legal-tool) Tests for All 7 Tools
    # --------------------------------------------------------------------------

    def test_cli_legal_tool_corpus_validate(self) -> None:
        runner = CliRunner()
        args = json.dumps({"document_id": "doc_100_2019_nd_cp"})
        res = runner.invoke(app, ["legal-tool", "mcp_traffic_corpus_validate", "-a", args])
        assert res.exit_code == 0
        parsed = cast(dict[str, object], json.loads(res.stdout))
        assert parsed.get("jsonrpc") == "2.0"
        assert "result" in parsed

    def test_cli_legal_tool_hybrid_search(self) -> None:
        runner = CliRunner()
        args = json.dumps({"query": "nồng độ cồn", "limit": 3})
        res = runner.invoke(app, ["legal-tool", "mcp_traffic_hybrid_search", "-a", args])
        assert res.exit_code == 0
        parsed = cast(dict[str, object], json.loads(res.stdout))
        assert parsed.get("jsonrpc") == "2.0"
        result_dict = cast(dict[str, object], parsed.get("result", {}))
        assert "results" in result_dict

    def test_cli_legal_tool_hierarchical_navigate(self) -> None:
        runner = CliRunner()
        args = json.dumps({
            "target_path": "doc_100_2019_nd_cp.a5.c3.p_a",
            "direction": "PARENT_CHAIN",
        })
        res = runner.invoke(app, ["legal-tool", "mcp_traffic_hierarchical_navigate", "-a", args])
        assert res.exit_code == 0
        parsed = cast(dict[str, object], json.loads(res.stdout))
        assert parsed.get("jsonrpc") == "2.0"
        assert "result" in parsed

    def test_cli_legal_tool_graph_traverse(self) -> None:
        runner = CliRunner()
        args = json.dumps({
            "start_chunk_id": "chk_nd100_art5_cl3_pta",
            "max_depth": 2,
        })
        res = runner.invoke(app, ["legal-tool", "mcp_traffic_graph_traverse", "-a", args])
        assert res.exit_code == 0
        parsed = cast(dict[str, object], json.loads(res.stdout))
        assert parsed.get("jsonrpc") == "2.0"
        assert "result" in parsed



    def test_cli_legal_tool_sign_catalog_lookup(self) -> None:
        runner = CliRunner()
        args = json.dumps({"sign_code": "P.102"})
        res = runner.invoke(app, ["legal-tool", "mcp_traffic_sign_catalog_lookup", "-a", args])
        assert res.exit_code == 0
        parsed = cast(dict[str, object], json.loads(res.stdout))
        assert parsed.get("jsonrpc") == "2.0"
        result_dict = cast(dict[str, object], parsed.get("result", {}))
        total = result_dict.get("total_matches", 0)
        assert isinstance(total, int) and total >= 1

    def test_cli_legal_tool_knowledge_cache_query(self) -> None:
        runner = CliRunner()
        args = json.dumps({"natural_query": "vượt đèn đỏ ô tô"})
        res = runner.invoke(app, ["legal-tool", "mcp_traffic_knowledge_cache_query", "-a", args])
        assert res.exit_code == 0
        parsed = cast(dict[str, object], json.loads(res.stdout))
        assert parsed.get("jsonrpc") == "2.0"
        assert "result" in parsed

    def test_cli_legal_tool_knowledge_cache_write(self) -> None:
        runner = CliRunner()
        args = json.dumps({
            "natural_query": "vượt đèn đỏ ô tô",
            "answer": "Phạt tiền từ 800.000 đến 1.000.000 đồng.",
            "citations": ["100/2019/ND-CP Điều 5 Khoản 3 Điểm a"],
        })
        res = runner.invoke(app, ["legal-tool", "mcp_traffic_knowledge_cache_write", "-a", args])
        assert res.exit_code == 0
        parsed = cast(dict[str, object], json.loads(res.stdout))
        assert parsed.get("jsonrpc") == "2.0"
        assert "result" in parsed

    def test_cli_legal_tool_output_file(self, tmp_path: Path) -> None:
        runner = CliRunner()
        out_file = tmp_path / "sign_output.json"
        args = json.dumps({"sign_code": "P.102"})
        res = runner.invoke(
            app,
            [
                "legal-tool",
                "mcp_traffic_sign_catalog_lookup",
                "--args",
                args,
                "--output",
                str(out_file),
                "--no-raw",
            ],
        )
        assert res.exit_code == 0
        assert out_file.exists()
        parsed = cast(dict[str, object], json.loads(out_file.read_text(encoding="utf-8")))
        assert parsed.get("jsonrpc") == "2.0"
        assert "result" in parsed
        assert "Tool output written to" in res.stdout

    def test_cli_legal_tool_invalid_json(self) -> None:
        runner = CliRunner()
        res = runner.invoke(app, ["legal-tool", "mcp_traffic_sign_catalog_lookup", "-a", "{bad_json: 123}"])
        assert res.exit_code != 0
        assert "Error parsing JSON arguments" in res.stdout

    def test_cli_legal_tool_invalid_args_type(self) -> None:
        runner = CliRunner()
        res = runner.invoke(app, ["legal-tool", "mcp_traffic_sign_catalog_lookup", "-a", '["list", "not", "dict"]'])
        assert res.exit_code != 0
        assert "Tool arguments must be a JSON object" in res.stdout

    def test_cli_legal_tool_unknown_tool(self) -> None:
        runner = CliRunner()
        res = runner.invoke(app, ["legal-tool", "non_existent_tool_name", "-a", "{}"])
        assert res.exit_code != 0
        parsed = cast(dict[str, object], json.loads(res.stdout))
        assert "error" in parsed
        err_dict = cast(dict[str, object], parsed["error"])
        assert err_dict.get("code") == -32601

    def test_cli_legal_tool_validation_error(self) -> None:
        runner = CliRunner()
        # CorpusValidateParams has extra="forbid" and requires document_id
        res = runner.invoke(
            app,
            ["legal-tool", "mcp_traffic_corpus_validate", "-a", '{"invalid_unexpected_field": true}'],
        )
        assert res.exit_code != 0
        parsed = cast(dict[str, object], json.loads(res.stdout))
        assert "error" in parsed
        err_dict = cast(dict[str, object], parsed["error"])
        assert err_dict.get("code") == -32602
