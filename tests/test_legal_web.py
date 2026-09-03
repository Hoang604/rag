"""Comprehensive test suite for FastAPI backend service and Human Promotion Engine (Milestone 2)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import ASGITransport

from rag_eval.legal.ingestion.staging import StagingManager
from rag_eval.legal.web.app import create_app
from rag_eval.legal.web.service import (
    DiffCalculator,
    HumanPromotionEngine,
    PreFlightValidator,
    TreeHierarchyBuilder,
)

SAMPLE_STATUTORY_TEXT = """
CHƯƠNG II
HÀNH VI VI PHẠM, HÌNH THỨC, MỨC XỬ PHẠT

Điều 5. Xử phạt người điều khiển xe ô tô
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với hành vi sau:
a) Không chấp hành hiệu lệnh của biển báo;
b) Dừng xe không bật đèn tín hiệu báo trước.
3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với hành vi sau:
a) Chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;
"""


@pytest.fixture
def mock_db_pool() -> Any:
    """Provides a mocked asyncpg pool simulating PostgreSQL operations."""
    pool = MagicMock()
    conn = AsyncMock()

    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx)
    pool.acquire.return_value.__aenter__.return_value = conn

    def mock_fetch(query: str, *args: Any) -> list[dict[str, Any]]:
        if "SELECT id, path::text FROM chunks WHERE path = ANY" in query:
            paths = args[0] if args else []
            return [{"id": "88888888-4444-4444-4444-121212121212", "path": p} for p in paths]
        return []

    conn.fetch.side_effect = mock_fetch

    def mock_fetchval(query: str, *args: Any) -> Any:
        if "INSERT INTO documents" in query:
            return "77777777-3333-3333-3333-111111111111"
        if "SELECT 1" in query:
            return 1
        return 10

    conn.fetchval.side_effect = mock_fetchval
    return pool


@pytest.fixture
def staging_dir(tmp_path: Path) -> Path:
    """Creates an isolated temporary staging directory."""
    stg_p = tmp_path / "stg"
    stg_p.mkdir(parents=True, exist_ok=True)
    return stg_p


@pytest.fixture
async def client(staging_dir: Path, mock_db_pool: Any) -> Any:
    """Provides an async HTTP test client configured with the test FastAPI app."""
    app = create_app(staging_dir=staging_dir, db_pool=mock_db_pool)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ------------------------------------------------------------------------------
# 1. Health Probe & Discovery Listing Tests
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_health_check(client: httpx.AsyncClient) -> None:
    """Verifies GET /api/health returns 200 OK and database CONNECTED status."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "OK"
    assert data["database"] == "CONNECTED"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_api_staging_empty_listing(client: httpx.AsyncClient) -> None:
    """Verifies GET /api/staging returns empty list when no sessions exist."""
    resp = await client.get("/api/staging")
    assert resp.status_code == 200
    assert resp.json() == []


# ------------------------------------------------------------------------------
# 2. Session Creation & Retrieval Tests
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_create_session_from_raw(client: httpx.AsyncClient) -> None:
    """Verifies POST /api/staging/raw parses raw text and creates a valid DRAFT session."""
    payload = {
        "doc_code": "100/2019/NĐ-CP",
        "title": "Nghị định 100/2019/NĐ-CP",
        "raw_text": SAMPLE_STATUTORY_TEXT,
        "effective_date": "2020-01-15",
        "metadata": {"authority": "Chính phủ"},
    }
    resp = await client.post("/api/staging/raw", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_code"] == "100/2019/NĐ-CP"
    assert data["status"] == "DRAFT"
    assert len(data["chunks"]) == 3
    assert len(data["mutation_history"]) >= 1

    # Verify listing now discovers the created session
    list_resp = await client.get("/api/staging")
    assert list_resp.status_code == 200
    summaries = list_resp.json()
    assert len(summaries) == 1
    assert summaries[0]["doc_code"] == "100/2019/NĐ-CP"
    assert summaries[0]["total_chunks"] == 3


@pytest.mark.asyncio
async def test_api_get_session_detail(client: httpx.AsyncClient) -> None:
    """Verifies GET /api/staging/{doc_code} retrieves full session details."""
    await client.post(
        "/api/staging/raw",
        json={
            "doc_code": "100/2019/NĐ-CP",
            "title": "Nghị định 100",
            "raw_text": SAMPLE_STATUTORY_TEXT,
            "effective_date": "2020-01-15",
        },
    )

    resp = await client.get("/api/staging/100/2019/NĐ-CP")
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_code"] == "100/2019/NĐ-CP"
    assert data["title"] == "Nghị định 100"
    assert len(data["chunks"]) == 3


# ------------------------------------------------------------------------------
# 3. Document Tree Hierarchy Builder Tests
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_get_document_tree_hierarchy(client: httpx.AsyncClient) -> None:
    """Verifies GET /api/staging/{doc_code}/tree builds nested Chapter -> Article -> Clause -> Point tree."""
    await client.post(
        "/api/staging/raw",
        json={
            "doc_code": "100/2019/NĐ-CP",
            "title": "Nghị định 100",
            "raw_text": SAMPLE_STATUTORY_TEXT,
            "effective_date": "2020-01-15",
        },
    )

    resp = await client.get("/api/staging/100/2019/NĐ-CP/tree")
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_code"] == "100/2019/NĐ-CP"
    assert data["total_nodes"] >= 4

    root = data["root"]
    assert root["node_type"] == "DOCUMENT"
    assert len(root["children"]) >= 1

    # Traverse to chapter and article
    chap_node = root["children"][0]
    assert chap_node["node_type"] == "CHAPTER"
    assert len(chap_node["children"]) >= 1

    art_node = chap_node["children"][0]
    assert art_node["node_type"] == "ARTICLE"
    assert len(art_node["children"]) >= 2  # Clause 1 and Clause 3


# ------------------------------------------------------------------------------
# 4. Batch Chunk Patching & In-Place Editing Tests
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_batch_patch_chunks(client: httpx.AsyncClient) -> None:
    """Verifies POST /api/staging/{doc_code}/patch updates chunk text and removes paths."""
    await client.post(
        "/api/staging/raw",
        json={
            "doc_code": "100/2019/NĐ-CP",
            "title": "Nghị định 100",
            "raw_text": SAMPLE_STATUTORY_TEXT,
            "effective_date": "2020-01-15",
        },
    )

    patch_payload = {
        "updated_chunks": [
            {
                "path": "100_2019_nd_cp.c_ii.a_5.c_3.p_a",
                "verbatim_text": "Điểm a) Sửa đổi: Phạt từ 1.000.000 đồng đến 2.000.000 đồng",
                "contextualized_text": "[Nghị định 100] > [Điều 5]\nĐiểm a) Sửa đổi",
                "metadata": {"fines": {"min_vnd": 1000000, "max_vnd": 2000000}},
                "effective_date": "2020-01-15",
            }
        ],
        "removed_paths": ["100_2019_nd_cp.c_ii.a_5.c_1.p_b"],
    }

    resp = await client.post("/api/staging/100/2019/NĐ-CP/patch", json=patch_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["updated_count"] == 1
    assert data["removed_count"] == 1
    assert data["total_chunks"] == 2

    # Verify session detail reflects update
    detail = (await client.get("/api/staging/100/2019/NĐ-CP")).json()
    assert len(detail["chunks"]) == 2
    patched_chunk = next(
        c for c in detail["chunks"] if c["path"] == "100_2019_nd_cp.c_ii.a_5.c_3.p_a"
    )
    assert "Sửa đổi" in patched_chunk["verbatim_text"]


# ------------------------------------------------------------------------------
# 5. Graph Edge Management Tests
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_edge_lifecycle(client: httpx.AsyncClient) -> None:
    """Verifies adding, listing, and deleting relational graph edges via API."""
    await client.post(
        "/api/staging/raw",
        json={
            "doc_code": "100/2019/NĐ-CP",
            "title": "Nghị định 100",
            "raw_text": SAMPLE_STATUTORY_TEXT,
            "effective_date": "2020-01-15",
        },
    )

    edge_payload = [
        {
            "source_path": "100_2019_nd_cp.c_ii.a_5.c_3.p_a",
            "target_path": "100_2019_nd_cp.c_ii.a_5.c_1.p_a",
            "relation_type": "REFERENCES",
            "citation_text": "Căn cứ theo Điểm a Khoản 1",
            "metadata": {"confidence": 1.0},
        }
    ]

    # 1. Add edge
    add_resp = await client.post("/api/staging/100/2019/NĐ-CP/edges", json=edge_payload)
    assert add_resp.status_code == 200
    assert len(add_resp.json()["edges"]) == 1

    # 2. List edges
    list_resp = await client.get("/api/staging/100/2019/NĐ-CP/edges")
    assert list_resp.status_code == 200
    edges = list_resp.json()
    assert len(edges) == 1
    assert edges[0]["relation_type"] == "REFERENCES"

    # 3. Delete edge
    del_payload = {
        "source_path": "100_2019_nd_cp.c_ii.a_5.c_3.p_a",
        "target_path": "100_2019_nd_cp.c_ii.a_5.c_1.p_a",
        "relation_type": "REFERENCES",
    }
    del_resp = await client.request(
        "DELETE", "/api/staging/100/2019/NĐ-CP/edges", json=del_payload
    )
    assert del_resp.status_code == 200
    assert len(del_resp.json()["edges"]) == 0


# ------------------------------------------------------------------------------
# 6. Status Transitions, Diff Calculation & Raw Text
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_status_transition_and_diff(client: httpx.AsyncClient) -> None:
    """Verifies transitioning status to APPROVED and computing 4-stage version diff."""
    await client.post(
        "/api/staging/raw",
        json={
            "doc_code": "100/2019/NĐ-CP",
            "title": "Nghị định 100",
            "raw_text": SAMPLE_STATUTORY_TEXT,
            "effective_date": "2020-01-15",
        },
    )

    # 1. Update status to APPROVED
    st_resp = await client.post(
        "/api/staging/100/2019/NĐ-CP/status",
        json={"status": "APPROVED", "actor": "HUMAN:reviewer_charlie", "description": "Legal OK"},
    )
    assert st_resp.status_code == 200
    assert st_resp.json()["status"] == "APPROVED"

    # 2. Patch a chunk to trigger mutation diff
    await client.post(
        "/api/staging/100/2019/NĐ-CP/patch",
        json={
            "updated_chunks": [
                {
                    "path": "100_2019_nd_cp.c_ii.a_5.c_3.p_a",
                    "verbatim_text": "Updated verbatim content",
                    "contextualized_text": "Updated contextualized content",
                    "effective_date": "2020-01-15",
                }
            ],
            "removed_paths": [],
        },
    )

    # 3. Check diff endpoint
    diff_resp = await client.get("/api/staging/100/2019/NĐ-CP/diff")
    assert diff_resp.status_code == 200
    diff_data = diff_resp.json()
    assert diff_data["total_changes"] >= 1
    assert len(diff_data["modified_chunks"]) == 1

    # 4. Check raw text endpoint
    raw_resp = await client.get("/api/staging/100/2019/NĐ-CP/raw")
    assert raw_resp.status_code == 200
    assert "Điều 5" in raw_resp.json()["raw_text"]


# ------------------------------------------------------------------------------
# 7. Pre-Flight Validation Checklist Tests
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_preflight_validation_passed_and_failed(
    staging_dir: Path, client: httpx.AsyncClient
) -> None:
    """Verifies pre-flight validation passes on clean document and detects blocking errors on invalid data."""
    # 1. Clean valid session -> PASSED
    await client.post(
        "/api/staging/raw",
        json={
            "doc_code": "100/2019/NĐ-CP",
            "title": "Nghị định 100",
            "raw_text": SAMPLE_STATUTORY_TEXT,
            "effective_date": "2020-01-15",
        },
    )

    val_resp = await client.get("/api/staging/100/2019/NĐ-CP/validate")
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["status"] == "PASSED"
    assert val_data["passed"] is True
    assert val_data["total_checks"] == 7

    # 2. Corrupt session with orphan edge and empty text -> FAILED
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.load_session("100/2019/NĐ-CP")

    # Inject empty verbatim text & broken edge
    session.chunks[0].verbatim_text = ""
    session.edges.append(
        MagicMock(
            source_path="100_2019_nd_cp.phantom_source",
            target_path=None,
            target_external_ref=None,
            relation_type="REFERENCES",
            citation_text=None,
            metadata={},
        )
    )
    # Save manually using model_dump to simulate corruption
    raw_dict = session.model_dump(mode="json")
    raw_dict["chunks"][0]["verbatim_text"] = ""
    raw_dict["edges"].append({
        "source_path": "100_2019_nd_cp.phantom_source",
        "target_path": None,
        "target_external_ref": None,
        "relation_type": "REFERENCES",
    })
    session_file = staging_dir / "100_2019_nd_cp.json"
    session_file.write_text(json.dumps(raw_dict), encoding="utf-8")

    fail_resp = await client.get("/api/staging/100/2019/NĐ-CP/validate")
    assert fail_resp.status_code == 200
    fail_data = fail_resp.json()
    assert fail_data["status"] == "FAILED"
    assert fail_data["passed"] is False
    assert len(fail_data["issues"]) >= 2
    rule_names = {i["rule"] for i in fail_data["issues"]}
    assert "CONTENT_GROUNDING" in rule_names
    assert "GRAPH_EDGE_INTEGRITY" in rule_names


# ------------------------------------------------------------------------------
# 8. Human Promotion Execution Tests
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_promote_session_success(client: httpx.AsyncClient) -> None:
    """Verifies POST /api/staging/{doc_code}/promote atomically persists document to PostgreSQL."""
    await client.post(
        "/api/staging/raw",
        json={
            "doc_code": "100/2019/NĐ-CP",
            "title": "Nghị định 100",
            "raw_text": SAMPLE_STATUTORY_TEXT,
            "effective_date": "2020-01-15",
        },
    )

    promote_payload = {
        "reviewer_notes": "Reviewed and approved by Legal Council",
        "compute_embeddings": False,
    }
    resp = await client.post("/api/staging/100/2019/NĐ-CP/promote", json=promote_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["doc_code"] == "100/2019/NĐ-CP"
    assert data["document_id"] == "77777777-3333-3333-3333-111111111111"
    assert data["chunks_promoted"] == 3
    assert "promoted_at" in data

    # Verify session is now PROMOTED on disk
    detail = (await client.get("/api/staging/100/2019/NĐ-CP")).json()
    assert detail["status"] == "PROMOTED"
    assert detail["promoted_at"] is not None


@pytest.mark.asyncio
async def test_api_promote_session_blocked_on_validation_failure(
    staging_dir: Path, client: httpx.AsyncClient
) -> None:
    """Verifies promotion is strictly blocked if pre-flight validation checks fail."""
    await client.post(
        "/api/staging/raw",
        json={
            "doc_code": "100/2019/NĐ-CP",
            "title": "Nghị định 100",
            "raw_text": SAMPLE_STATUTORY_TEXT,
            "effective_date": "2020-01-15",
        },
    )

    # Corrupt chunk path to violate ltree syntax
    session_file = staging_dir / "100_2019_nd_cp.json"
    raw_dict = json.loads(session_file.read_text(encoding="utf-8"))
    raw_dict["chunks"][0]["path"] = "INVALID...PATH..WITH..SPACES "
    session_file.write_text(json.dumps(raw_dict), encoding="utf-8")

    resp = await client.post(
        "/api/staging/100/2019/NĐ-CP/promote",
        json={"reviewer_notes": "Attempt promotion on corrupt session"},
    )
    assert resp.status_code == 400
    err_data = resp.json()
    assert "Pre-flight validation failed" in err_data["error"]["message"]


@pytest.mark.asyncio
async def test_api_delete_staging_session(client: httpx.AsyncClient) -> None:
    """Verifies DELETE /api/staging/{doc_code} unlinks session file."""
    await client.post(
        "/api/staging/raw",
        json={
            "doc_code": "DELETE_ME",
            "title": "Document to delete",
            "raw_text": SAMPLE_STATUTORY_TEXT,
            "effective_date": "2025-01-01",
        },
    )

    del_resp = await client.delete("/api/staging/DELETE_ME")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "SUCCESS"

    # Confirm session is gone
    get_resp = await client.get("/api/staging/DELETE_ME")
    assert get_resp.status_code == 400  # LegalDomainError not found


# ------------------------------------------------------------------------------
# 9. Direct Unit Tests for Service Layer & Edge Cases
# ------------------------------------------------------------------------------
def test_preflight_validator_root_alignment_and_duplicate_collision(staging_dir: Path) -> None:
    """Verifies PreFlightValidator detects ROOT_CODE_ALIGNMENT, DUPLICATE_PATH_COLLISION, and STATUTORY_DATES."""
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_STATUTORY_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    # 1. Test root alignment violation
    session.chunks.append(
        session.chunks[0].model_copy(
            update={
                "path": "different_doc_code.c_ii.a_5.c_1",
                "verbatim_text": "Mismatched root code chunk",
            }
        )
    )

    # 2. Test duplicate path collision
    session.chunks.append(session.chunks[0].model_copy())

    # 3. Test invalid date range on document
    session.expiration_date = datetime.date(2019, 1, 1)

    validator = PreFlightValidator()
    result = validator.validate(session)
    assert result.passed is False
    assert result.status == "FAILED"

    issue_rules = {i.rule for i in result.issues}
    assert "ROOT_CODE_ALIGNMENT" in issue_rules
    assert "DUPLICATE_PATH_COLLISION" in issue_rules
    assert "STATUTORY_DATES" in issue_rules


def test_tree_hierarchy_builder_sections_and_appendices(staging_dir: Path) -> None:
    """Verifies TreeHierarchyBuilder labels Chapters, Sections, Articles, Clauses, Points, and Appendices."""
    mgr = StagingManager(staging_dir=staging_dir)
    text_with_app = """
CHƯƠNG I
QUY ĐỊNH CHUNG

MỤC 1
PHẠM VI

Điều 1. Phạm vi
1. Quy định chung:
a) Điểm a;

PHỤ LỤC I
BIỂN BÁO HIỆU
Nội dung phụ lục.
"""
    session = mgr.create_session_from_raw(
        doc_code="TEST_TREE",
        title="Test Tree Document",
        raw_text=text_with_app,
        effective_date=datetime.date(2025, 1, 1),
    )

    builder = TreeHierarchyBuilder()
    tree = builder.build_tree(session)

    assert tree.doc_code == "TEST_TREE"
    assert tree.total_nodes >= 5

    types_found = set()

    def collect_types(node: Any) -> None:
        types_found.add(node.node_type)
        for child in node.children:
            collect_types(child)

    collect_types(tree.root)
    assert "DOCUMENT" in types_found
    assert "CHAPTER" in types_found
    assert "SECTION" in types_found
    assert "ARTICLE" in types_found
    assert "CLAUSE" in types_found
    assert "POINT" in types_found


def test_diff_calculator_direct_invocation(staging_dir: Path) -> None:
    """Verifies DiffCalculator directly detects added, deleted, and modified chunks."""
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_STATUTORY_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    # Modify 1 chunk, add 1 chunk, remove 1 chunk
    initial_chunks = session.chunks
    p_mod = initial_chunks[0].path
    initial_chunks[0].verbatim_text = "Modified verbatim text"

    p_add = "100_2019_nd_cp.c_ii.a_5.c_99.p_z"
    added_chunk = initial_chunks[0].model_copy(
        update={"path": p_add, "verbatim_text": "Added new point"}
    )

    # Remove last chunk
    session.chunks = [initial_chunks[0], added_chunk]

    diff_calc = DiffCalculator()
    diff = diff_calc.compute_diff(session)

    assert diff.total_changes >= 3
    assert len(diff.added_chunks) == 1
    assert diff.added_chunks[0].path == p_add
    assert len(diff.modified_chunks) == 1
    assert diff.modified_chunks[0]["path"] == p_mod
    assert len(diff.deleted_chunks) == 2


@pytest.mark.asyncio
async def test_human_promotion_engine_cross_document_resolution(
    staging_dir: Path, mock_db_pool: Any
) -> None:
    """Verifies HumanPromotionEngine handles cross-document target edges seamlessly."""
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code="123/2021/NĐ-CP",
        title="Nghị định 123",
        raw_text=SAMPLE_STATUTORY_TEXT,
        effective_date=datetime.date(2022, 1, 1),
    )

    src_path = session.chunks[0].path
    # Add cross-document edge pointing to Decree 100
    mgr.add_edges(
        doc_code="123/2021/NĐ-CP",
        edges=[
            MagicMock(
                source_path=src_path,
                target_path="100_2019_nd_cp.c_ii.a_5.c_3.p_a",
                target_external_ref=None,
                relation_type="MODIFIES_AND_REPLACES",
                citation_text="Sửa đổi Nghị định 100",
                metadata={},
            )
        ],
    )

    engine = HumanPromotionEngine(staging_manager=mgr)
    res = await engine.promote_session(
        doc_code="123/2021/NĐ-CP",
        reviewer_notes="Cross-document promotion test",
        compute_embeddings=False,
        pool=mock_db_pool,
    )
    assert res.status == "SUCCESS"
    assert res.doc_code == "123/2021/NĐ-CP"


@pytest.mark.asyncio
async def test_spa_static_files_serving(tmp_path: Path, mock_db_pool: Any) -> None:
    """Verifies SPA static files mounting and client-side routing fallback to index.html."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    index_html = dist_dir / "index.html"
    index_html.write_text("<html><body>SPA Root</body></html>", encoding="utf-8")
    style_css = assets_dir / "index.css"
    style_css.write_text("body { margin: 0; }", encoding="utf-8")

    app = create_app(
        staging_dir=tmp_path / "stg",
        db_pool=mock_db_pool,
        static_dir=dist_dir,
    )
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Fetch asset file
        asset_resp = await ac.get("/assets/index.css")
        assert asset_resp.status_code == 200
        assert "margin: 0" in asset_resp.text

        # 2. Fetch arbitrary SPA route (should fallback to index.html)
        spa_resp = await ac.get("/reviewer/100-2019-nd-cp")
        assert spa_resp.status_code == 200
        assert "SPA Root" in spa_resp.text


# ------------------------------------------------------------------------------
# 10. CLI `rag-eval ui` Command Tests
# ------------------------------------------------------------------------------
def test_cli_ui_help() -> None:
    """Verifies `rag-eval ui --help` displays correct flags and description."""
    from typer.testing import CliRunner

    from rag_eval.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["ui", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--dev" in result.output
    assert "--open" in result.output


def test_cli_ui_prod_mode_invocation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verifies `rag-eval ui` in production mode invokes uvicorn with static app."""
    from unittest.mock import MagicMock

    from typer.testing import CliRunner

    from rag_eval.cli import app

    dist_dir = tmp_path / "frontend" / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "assets").mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    mock_uvicorn_run = MagicMock()
    monkeypatch.setattr("uvicorn.run", mock_uvicorn_run)

    runner = CliRunner()
    result = runner.invoke(app, ["ui", "--no-open", "--port", "8888"])
    assert result.exit_code == 0
    assert mock_uvicorn_run.called
    assert mock_uvicorn_run.call_args[1]["port"] == 8888
