"""End-to-End Integration and System Hardening Test Suite for Vietnamese Traffic Law RAG.

Covers the full statutory lifecycle from raw ingestion AST parsing, AI Agent MCP
mutations and gated commit, to Reviewer FastAPI backend workflows, Pre-Flight
Integrity Gate enforcement, and Human Promotion into PostgreSQL production tables.
"""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport
from typer.testing import CliRunner

from rag_eval.cli import app as cli_app
from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingEdge,
    StagingManager,
    StagingStatus,
)
from rag_eval.legal.mcp.server import LegalMCPServer
from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.web.app import create_app
from rag_eval.legal.web.service import (
    DiffCalculator,
    HumanPromotionEngine,
    PreFlightValidator,
    TreeHierarchyBuilder,
)

RAW_STATUTORY_DECREE_100 = """
CHƯƠNG II
HÀNH VI VI PHẠM, HÌNH THỨC, MỨC XỬ PHẠT VÀ BIỆN PHÁP KHẮC PHỤC HẬU QUẢ

MỤC 1
VI PHẠM QUY TẮC GIAO THÔNG ĐƯỜNG BỘ

Điều 5. Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông đường bộ
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường;
b) Dừng xe, đỗ xe không có tín hiệu báo cho người điều khiển phương tiện khác biết.
3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;
"""

RAW_STATUTORY_DECREE_123 = """
CHƯƠNG I
SỬA ĐỔI, BỔ SUNG MỘT SỐ ĐIỀU CỦA NGHỊ ĐỊNH SỐ 100/2019/NĐ-CP

Điều 2. Sửa đổi, bổ sung một số điều của Nghị định số 100/2019/NĐ-CP
1. Sửa đổi Điểm a Khoản 3 Điều 5 như sau:
a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h bị phạt tiền từ 800.000 đồng đến 1.000.000 đồng;
"""


def create_mock_db_pool(
    doc_id: uuid.UUID | None = None,
    chunk_uuids: dict[str, uuid.UUID] | None = None,
) -> MagicMock:
    """Constructs a strictly typed mock asyncpg connection pool simulating PostgreSQL."""
    pool = MagicMock()
    conn = AsyncMock()

    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx)
    pool.acquire.return_value.__aenter__.return_value = conn

    fixed_doc_uuid = doc_id or uuid.uuid4()
    known_chunks: dict[str, uuid.UUID] = chunk_uuids or {}

    def mock_fetch(query: str, *args: Any) -> list[dict[str, Any]]:
        if "SELECT id, path::text FROM chunks WHERE path = ANY" in query:
            paths: list[str] = args[0] if args and isinstance(args[0], list) else []
            results: list[dict[str, Any]] = []
            for p in paths:
                cid = known_chunks.get(p, uuid.uuid4())
                results.append({"id": str(cid), "path": p})
            return results
        if "SELECT * FROM chunks" in query or "SELECT c.id" in query:
            return []
        return []

    conn.fetch.side_effect = mock_fetch

    def mock_fetchval(query: str, *args: Any) -> Any:
        if "INSERT INTO documents" in query:
            return str(fixed_doc_uuid)
        if "SELECT 1" in query or "SELECT count" in query:
            return 1
        return 1

    conn.fetchval.side_effect = mock_fetchval
    conn.executemany = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="OK")
    return pool


# ==============================================================================
# 1. Full Ingestion & Staging Lifecycle E2E Test
# ==============================================================================
@pytest.mark.asyncio
async def test_full_ingestion_and_staging_lifecycle_e2e(tmp_path: Path) -> None:
    """Verifies complete end-to-end statutory lifecycle across all 6 core stages.

    1. Ingestion into Staging (DRAFT, AST snapshot, mutation history)
    2. AI Agent MCP mutations (stg_preview windowing, stg_patch, stg_add_edges)
    3. AI Agent stg_commit (AGENT_COMMITTED status, zero DB writes, preserved on disk)
    4. Reviewer FastAPI interactions (listing, tree hierarchy, diff, in-place edit, APPROVED)
    5. Pre-flight integrity gate (corruption detection & blocking, resolution & pass)
    6. Human Promotion execution (atomic multi-table persistence with embeddings, PROMOTED audit)
    """
    staging_dir = tmp_path / "stg"
    staging_dir.mkdir(parents=True, exist_ok=True)
    doc_code = "100/2019/NĐ-CP"
    title = "Nghị định 100/2019/NĐ-CP"
    effective_date = datetime.date(2020, 1, 15)

    # --------------------------------------------------------------------------
    # Stage 1: Ingest raw statutory text into staging
    # --------------------------------------------------------------------------
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code=doc_code,
        title=title,
        raw_text=RAW_STATUTORY_DECREE_100,
        effective_date=effective_date,
        metadata={"authority": "Chính phủ", "sign_place": "Hà Nội"},
    )

    assert session.status == StagingStatus.DRAFT
    assert session.doc_code == doc_code
    assert session.title == title
    assert session.effective_date == effective_date
    assert session.raw_text == RAW_STATUTORY_DECREE_100
    assert session.raw_ast_snapshot is not None
    assert len(session.raw_ast_snapshot) == len(session.chunks)
    assert len(session.chunks) == 3  # 2 points from Clause 1, 1 point from Clause 3
    assert len(session.mutation_history) == 1
    assert session.mutation_history[0].actor == "SYSTEM"
    assert session.mutation_history[0].action_type == "CREATED"

    # --------------------------------------------------------------------------
    # Stage 2: AI Agent MCP tool mutations
    # --------------------------------------------------------------------------
    tools = LegalMCPTools(staging_manager=mgr)
    server = LegalMCPServer(tools=tools)

    # 2a. stg_preview with windowing
    preview_req = {
        "jsonrpc": "2.0",
        "id": 101,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_stg_preview",
            "arguments": {"doc_code": doc_code, "limit": 2, "offset": 0},
        },
    }
    prev_resp = await server.handle_request_dict(preview_req)
    assert prev_resp is not None
    assert "result" in prev_resp
    assert prev_resp["result"]["total_chunks"] == 3
    assert prev_resp["result"]["total_matched"] == 3
    assert len(prev_resp["result"]["chunks"]) == 2
    assert prev_resp["result"]["has_more"] is True

    # 2b. stg_patch surgical updating
    target_path = session.chunks[2].path  # Clause 3 Point a
    assert "c_3.p_a" in target_path
    patch_req = {
        "jsonrpc": "2.0",
        "id": 102,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_stg_patch",
            "arguments": {
                "doc_code": doc_code,
                "updated_chunks": [
                    {
                        "path": target_path,
                        "verbatim_text": "Điểm a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h (Mức phạt: 800.000đ - 1.000.000đ)",
                        "contextualized_text": f"[{title}] > [Điều 5]\nĐiểm a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h",
                        "metadata": {"fines": {"min_vnd": 800000, "max_vnd": 1000000}},
                        "effective_date": "2020-01-15",
                    }
                ],
            },
        },
    }
    patch_resp = await server.handle_request_dict(patch_req)
    assert patch_resp is not None
    assert patch_resp["result"]["status"] == "SUCCESS"
    assert patch_resp["result"]["total_chunks_after_patch"] == 3

    # 2c. stg_add_edges directed relation attaching
    ref_target_path = session.chunks[0].path  # Clause 1 Point a
    edge_req = {
        "jsonrpc": "2.0",
        "id": 103,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_stg_add_edges",
            "arguments": {
                "doc_code": doc_code,
                "edges": [
                    {
                        "source_path": target_path,
                        "target_path": ref_target_path,
                        "relation_type": "REFERENCES",
                        "citation_text": "Căn cứ quy định về biển báo tại Điểm a Khoản 1",
                        "metadata": {"confidence": 0.98},
                    }
                ],
            },
        },
    }
    edge_resp = await server.handle_request_dict(edge_req)
    assert edge_resp is not None
    assert edge_resp["result"]["status"] == "SUCCESS"
    assert edge_resp["result"]["total_edges"] == 1

    # --------------------------------------------------------------------------
    # Stage 3: AI Agent stg_commit
    # --------------------------------------------------------------------------
    commit_req = {
        "jsonrpc": "2.0",
        "id": 104,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_stg_commit",
            "arguments": {"doc_code": doc_code},
        },
    }
    commit_resp = await server.handle_request_dict(commit_req)
    assert commit_resp is not None
    assert commit_resp["result"]["status"] == "AGENT_COMMITTED"
    assert commit_resp["result"]["total_chunks"] == 3
    assert commit_resp["result"]["total_edges"] == 1
    assert "committed_at" in commit_resp["result"]

    # Verify staging file is PRESERVED on disk
    stg_file = staging_dir / "100_2019_nd_cp.json"
    assert stg_file.exists()

    committed_session = mgr.load_session(doc_code)
    assert committed_session.status == StagingStatus.AGENT_COMMITTED
    assert committed_session.committed_at is not None
    assert len(committed_session.mutation_history) == 4  # CREATED, CHUNK_PATCHED, EDGES_ADDED, AGENT_COMMITTED

    # --------------------------------------------------------------------------
    # Stage 4: Reviewer UI backend interactions via FastAPI
    # --------------------------------------------------------------------------
    mock_pool = create_mock_db_pool()
    app = create_app(staging_dir=staging_dir, db_pool=mock_pool)
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 4a. Discovery listing
        list_res = await client.get("/api/staging")
        assert list_res.status_code == 200
        summaries = list_res.json()
        assert len(summaries) == 1
        assert summaries[0]["doc_code"] == doc_code
        assert summaries[0]["status"] == "AGENT_COMMITTED"
        assert summaries[0]["total_chunks"] == 3
        assert summaries[0]["total_edges"] == 1

        # 4b. Tree hierarchy retrieval
        tree_res = await client.get(f"/api/staging/{doc_code}/tree")
        assert tree_res.status_code == 200
        tree_data = tree_res.json()
        assert tree_data["doc_code"] == doc_code
        assert tree_data["total_nodes"] >= 5
        root = tree_data["root"]
        assert root["node_type"] == "DOCUMENT"
        chap = root["children"][0]
        assert chap["node_type"] == "CHAPTER"
        sec = chap["children"][0]
        assert sec["node_type"] == "SECTION"
        art = sec["children"][0]
        assert art["node_type"] == "ARTICLE"
        assert len(art["children"]) == 2  # Clause 1 and Clause 3

        # 4c. Version diff comparison against baseline AST
        diff_res = await client.get(f"/api/staging/{doc_code}/diff")
        assert diff_res.status_code == 200
        diff_data = diff_res.json()
        assert diff_data["total_changes"] >= 1
        assert len(diff_data["modified_chunks"]) == 1
        assert diff_data["modified_chunks"][0]["path"] == target_path

        # 4d. Reviewer in-place chunk patch
        reviewer_patch = {
            "updated_chunks": [
                {
                    "path": target_path,
                    "verbatim_text": "Điểm a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h (Đã thẩm định chuẩn hóa).",
                    "contextualized_text": f"[{title}] > [Điều 5]\nĐiểm a) Đã thẩm định chuẩn hóa",
                    "metadata": {"fines": {"min_vnd": 800000, "max_vnd": 1000000}, "reviewer_checked": True},
                    "effective_date": "2020-01-15",
                }
            ],
            "removed_paths": [],
        }
        patch_res = await client.post(f"/api/staging/{doc_code}/patch", json=reviewer_patch)
        assert patch_res.status_code == 200
        assert patch_res.json()["status"] == "SUCCESS"

        # 4e. Reviewer transitions status to APPROVED
        status_payload = {
            "status": "APPROVED",
            "actor": "HUMAN:reviewer_le",
            "description": "Thẩm định toàn văn đạt chuẩn pháp lý",
        }
        st_res = await client.post(f"/api/staging/{doc_code}/status", json=status_payload)
        assert st_res.status_code == 200
        assert st_res.json()["status"] == "APPROVED"

        # ----------------------------------------------------------------------
        # Stage 5: Pre-Flight Validation Gate
        # ----------------------------------------------------------------------
        # 5a. Introduce deliberate corruption (corrupt ltree path in chunk)
        corrupt_session = mgr.load_session(doc_code)
        valid_path_backup = corrupt_session.chunks[0].path
        corrupt_session.chunks[0].path = "invalid..ltree.path with spaces"
        mgr.save_session(corrupt_session)

        # Pre-flight validation must fail
        val_fail_res = await client.get(f"/api/staging/{doc_code}/validate")
        assert val_fail_res.status_code == 200
        val_fail_data = val_fail_res.json()
        assert val_fail_data["status"] == "FAILED"
        assert val_fail_data["passed"] is False
        assert any(i["rule"] == "LTREE_PATH_SYNTAX" for i in val_fail_data["issues"])

        # Attempted promotion MUST be blocked (HTTP 400)
        promote_blocked_res = await client.post(
            f"/api/staging/{doc_code}/promote",
            json={"reviewer_notes": "Attempting promotion with broken path"},
        )
        assert promote_blocked_res.status_code == 400
        assert "Pre-flight validation failed" in promote_blocked_res.json()["error"]["message"]

        # 5b. Fix corruption and re-validate
        fixed_session = mgr.load_session(doc_code)
        fixed_session.chunks[0].path = valid_path_backup
        mgr.save_session(fixed_session)

        val_pass_res = await client.get(f"/api/staging/{doc_code}/validate")
        assert val_pass_res.status_code == 200
        assert val_pass_res.json()["status"] == "PASSED"
        assert val_pass_res.json()["passed"] is True

        # ----------------------------------------------------------------------
        # Stage 6: Human Promotion Execution
        # ----------------------------------------------------------------------
        promote_res = await client.post(
            f"/api/staging/{doc_code}/promote",
            json={
                "reviewer_notes": "Phê duyệt chính thức nạp CSDL sản xuất",
                "compute_embeddings": False,
            },
        )
        assert promote_res.status_code == 200
        promote_data = promote_res.json()
        assert promote_data["status"] == "SUCCESS"
        assert promote_data["doc_code"] == doc_code
        assert promote_data["chunks_promoted"] == 3
        assert promote_data["edges_promoted"] == 1
        assert "promoted_at" in promote_data

        # Verify database pool operations executed atomically
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        assert conn.transaction.called
        assert conn.executemany.call_count >= 2  # chunks + graph_edges

        # Assert staging session is PROMOTED on disk and preserved with audit trail
        final_session = mgr.load_session(doc_code)
        assert final_session.status == StagingStatus.PROMOTED
        assert final_session.promoted_at is not None
        assert stg_file.exists()  # Staging file is PRESERVED on disk

        last_mutation = final_session.mutation_history[-1]
        assert last_mutation.action_type == "PROMOTED_TO_PRODUCTION"
        assert last_mutation.actor == "HUMAN:reviewer"
        assert "Phê duyệt chính thức nạp CSDL sản xuất" in (last_mutation.description or "")


# ==============================================================================
# 2. Multi-Document Cross-Referencing & Promotion E2E
# ==============================================================================
@pytest.mark.asyncio
async def test_multi_document_cross_referencing_and_promotion_e2e(tmp_path: Path) -> None:
    """Verifies multi-document staging, cross-document edge resolution, and sequential promotion."""
    staging_dir = tmp_path / "stg"
    staging_dir.mkdir(parents=True, exist_ok=True)
    mgr = StagingManager(staging_dir=staging_dir)

    # 1. Ingest Decree 100
    session_100 = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=RAW_STATUTORY_DECREE_100,
        effective_date=datetime.date(2020, 1, 15),
    )
    target_100_chunk_path = session_100.chunks[2].path

    # 2. Ingest Decree 123
    session_123 = mgr.create_session_from_raw(
        doc_code="123/2021/NĐ-CP",
        title="Nghị định 123",
        raw_text=RAW_STATUTORY_DECREE_123,
        effective_date=datetime.date(2022, 1, 1),
    )
    src_123_chunk_path = session_123.chunks[0].path

    # Attach cross-document edge from Decree 123 pointing to Decree 100
    cross_edge = StagingEdge(
        source_path=src_123_chunk_path,
        target_path=target_100_chunk_path,
        relation_type="MODIFIES_AND_REPLACES",
        citation_text="Sửa đổi Điểm a Khoản 3 Điều 5 Nghị định 100",
    )
    mgr.add_edges("123/2021/NĐ-CP", [cross_edge])

    # 3. Simulate Decree 100 already in PostgreSQL
    fixed_100_doc_uuid = uuid.uuid4()
    fixed_100_chunk_uuid = uuid.uuid4()
    known_chunks_in_db = {target_100_chunk_path: fixed_100_chunk_uuid}

    mock_pool = create_mock_db_pool(
        doc_id=fixed_100_doc_uuid, chunk_uuids=known_chunks_in_db
    )

    # Promote Decree 123
    engine = HumanPromotionEngine(staging_manager=mgr)
    promo_result = await engine.promote_session(
        doc_code="123/2021/NĐ-CP",
        reviewer_notes="Promote Decree 123 with cross-document relation",
        compute_embeddings=False,
        pool=mock_pool,
    )

    assert promo_result.status == "SUCCESS"
    assert promo_result.doc_code == "123/2021/NĐ-CP"
    assert promo_result.edges_promoted == 1

    # Reload Decree 123 from disk and verify PROMOTED
    reloaded_123 = mgr.load_session("123/2021/NĐ-CP")
    assert reloaded_123.status == StagingStatus.PROMOTED
    assert len(reloaded_123.edges) == 1
    assert reloaded_123.edges[0].relation_type == "MODIFIES_AND_REPLACES"


# ==============================================================================
# 3. Exhaustive Pre-Flight Validation Rules Verification
# ==============================================================================
def test_preflight_validator_exhaustive_rules(tmp_path: Path) -> None:
    """Verifies all 7 pre-flight validation rules detect violations accurately."""
    mgr = StagingManager(staging_dir=tmp_path)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=RAW_STATUTORY_DECREE_100,
        effective_date=datetime.date(2020, 1, 15),
    )

    validator = PreFlightValidator()

    # Base valid session -> PASS
    res_valid = validator.validate(session)
    assert res_valid.passed is True
    assert res_valid.status == "PASSED"
    assert len(res_valid.issues) == 0

    # Rule 1: LTREE_PATH_SYNTAX
    sess_bad_path = session.model_copy(deep=True)
    sess_bad_path.chunks[0].path = "invalid.path with space.1"
    res_bad_path = validator.validate(sess_bad_path)
    assert res_bad_path.passed is False
    assert any(i.rule == "LTREE_PATH_SYNTAX" for i in res_bad_path.issues)

    # Rule 2: ROOT_CODE_ALIGNMENT
    sess_mismatch_root = session.model_copy(deep=True)
    sess_mismatch_root.chunks[0].path = "other_doc_code.c_ii.a_5"
    res_mismatch = validator.validate(sess_mismatch_root)
    assert res_mismatch.passed is False
    assert any(i.rule == "ROOT_CODE_ALIGNMENT" for i in res_mismatch.issues)

    # Rule 3: PARENT_CHILD_CONTINUITY (Zero chunks)
    sess_zero_chunks = session.model_copy(deep=True)
    sess_zero_chunks.chunks = []
    res_zero = validator.validate(sess_zero_chunks)
    assert res_zero.passed is False
    assert any(i.rule == "PARENT_CHILD_CONTINUITY" for i in res_zero.issues)

    # Rule 4: STATUTORY_DATES (Expiration < Effective)
    sess_bad_dates = session.model_copy(deep=True)
    sess_bad_dates.expiration_date = datetime.date(2010, 1, 1)
    res_dates = validator.validate(sess_bad_dates)
    assert res_dates.passed is False
    assert any(i.rule == "STATUTORY_DATES" for i in res_dates.issues)

    # Rule 5: CONTENT_GROUNDING (Empty verbatim_text)
    sess_empty_text = session.model_copy(deep=True)
    sess_empty_text.chunks[0].verbatim_text = "   "
    res_empty = validator.validate(sess_empty_text)
    assert res_empty.passed is False
    assert any(i.rule == "CONTENT_GROUNDING" for i in res_empty.issues)

    # Rule 6: GRAPH_EDGE_INTEGRITY (Orphan source_path)
    sess_bad_edge = session.model_copy(deep=True)
    sess_bad_edge.edges = [
        StagingEdge(
            source_path="100_2019_nd_cp.phantom_source_chunk",
            target_path=session.chunks[0].path,
            relation_type="REFERENCES",
        )
    ]
    res_edge = validator.validate(sess_bad_edge)
    assert res_edge.passed is False
    assert any(i.rule == "GRAPH_EDGE_INTEGRITY" for i in res_edge.issues)

    # Rule 7: DUPLICATE_PATH_COLLISION
    sess_dup_path = session.model_copy(deep=True)
    sess_dup_path.chunks.append(session.chunks[0].model_copy())
    res_dup = validator.validate(sess_dup_path)
    assert res_dup.passed is False
    assert any(i.rule == "DUPLICATE_PATH_COLLISION" for i in res_dup.issues)


# ==============================================================================
# 4. Tree Hierarchy Builder & 4-Stage Diff Calculator
# ==============================================================================
def test_tree_hierarchy_builder_and_diff_calculator(tmp_path: Path) -> None:
    """Verifies tree hierarchy node construction and 4-stage version diff detection."""
    mgr = StagingManager(staging_dir=tmp_path)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=RAW_STATUTORY_DECREE_100,
        effective_date=datetime.date(2020, 1, 15),
    )

    # 1. Tree Hierarchy Builder
    builder = TreeHierarchyBuilder()
    tree = builder.build_tree(session)
    assert tree.doc_code == "100/2019/NĐ-CP"
    assert tree.total_nodes >= 6

    # Verify labels and node types
    root = tree.root
    assert root.node_type == "DOCUMENT"
    assert len(root.children) == 1
    chap = root.children[0]
    assert chap.node_type == "CHAPTER"
    assert "Chương" in chap.label

    # 2. Diff Calculator: modify 1 chunk, add 1 chunk, remove 1 chunk
    initial_snapshot_count = len(session.chunks)
    p_mod = session.chunks[0].path
    session.chunks[0].verbatim_text = "Nội dung nguyên văn đã sửa đổi"
    session.chunks[0].contextualized_text = "Nội dung ngữ cảnh đã sửa đổi"

    p_new = "100_2019_nd_cp.c_ii.s_1.a_5.c_99.p_z"
    new_chunk = StagingChunk(
        path=p_new,
        verbatim_text="Điểm z mới thêm",
        contextualized_text="Ngữ cảnh điểm z",
        effective_date=datetime.date(2020, 1, 15),
    )
    # Remove last chunk and append new chunk
    session.chunks = [session.chunks[0], session.chunks[1], new_chunk]

    calculator = DiffCalculator()
    diff = calculator.compute_diff(session)

    assert diff.doc_code == "100/2019/NĐ-CP"
    assert diff.total_changes >= 3
    assert len(diff.added_chunks) == 1
    assert diff.added_chunks[0].path == p_new
    assert len(diff.modified_chunks) == 1
    assert diff.modified_chunks[0]["path"] == p_mod
    assert len(diff.deleted_chunks) == (initial_snapshot_count - 2)


# ==============================================================================
# 5. CLI UI Runner & SPA Static Asset Serving Verification
# ==============================================================================
def test_cli_ui_help_and_arguments() -> None:
    """Verifies `rag-eval ui --help` displays all flags."""
    runner = CliRunner()
    result = runner.invoke(cli_app, ["ui", "--help"])
    assert result.exit_code == 0
    assert "Human-in-the-Loop Legal Staging Reviewer" in result.output
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--dev" in result.output
    assert "--open" in result.output


def test_cli_ui_prod_mode_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verifies `rag-eval ui` executes uvicorn runner with production static directory."""
    dist_dir = tmp_path / "frontend" / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "assets").mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<!DOCTYPE html><html><body>SPA Root</body></html>", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    mock_uvicorn_run = MagicMock()
    monkeypatch.setattr("uvicorn.run", mock_uvicorn_run)

    runner = CliRunner()
    result = runner.invoke(cli_app, ["ui", "--no-open", "--host", "0.0.0.0", "--port", "9000"])
    assert result.exit_code == 0
    assert mock_uvicorn_run.called
    assert mock_uvicorn_run.call_args[1]["host"] == "0.0.0.0"
    assert mock_uvicorn_run.call_args[1]["port"] == 9000


@pytest.mark.asyncio
async def test_spa_production_static_mount_and_fallback_routing(tmp_path: Path) -> None:
    """Verifies static asset serving and SPA HTML5 client-side routing fallback."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    index_html = dist_dir / "index.html"
    index_html.write_text("<!DOCTYPE html><html><head><title>SPA</title></head><body><div id='root'></div></body></html>", encoding="utf-8")

    bundle_js = assets_dir / "index-12345.js"
    bundle_js.write_text("console.log('SPA Bundle');", encoding="utf-8")

    bundle_css = assets_dir / "index-67890.css"
    bundle_css.write_text("body { background: #f8fafc; }", encoding="utf-8")

    app = create_app(
        staging_dir=tmp_path / "stg",
        db_pool=create_mock_db_pool(),
        static_dir=dist_dir,
    )
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Direct asset downloads
        js_resp = await client.get("/assets/index-12345.js")
        assert js_resp.status_code == 200
        assert "console.log('SPA Bundle')" in js_resp.text

        css_resp = await client.get("/assets/index-67890.css")
        assert css_resp.status_code == 200
        assert "background: #f8fafc" in css_resp.text

        # 2. SPA client-side routes fallback to index.html
        root_resp = await client.get("/")
        assert root_resp.status_code == 200
        assert "<div id='root'></div>" in root_resp.text

        route_resp = await client.get("/reviewer/100-2019-nd-cp")
        assert route_resp.status_code == 200
        assert "<div id='root'></div>" in route_resp.text

        nested_route_resp = await client.get("/tree/diff/100-2019-nd-cp")
        assert nested_route_resp.status_code == 200
        assert "<div id='root'></div>" in nested_route_resp.text
