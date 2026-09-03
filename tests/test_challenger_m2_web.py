"""Empirical Challenger Test Suite for Milestone 2.

Adversarially probes:
1. Pre-flight integrity validation: rejection of orphan chunks, bad ltree paths,
   invalid dates, whitespace/empty text, corrupted edges, and path collisions.
2. Human Promotion Engine: atomic rollback guarantees on database errors and
   unassigned chunk UUIDs, ensuring zero state corruption in staging sessions.
3. Document Tree Hierarchy Builder: deeply nested paths, out-of-order chunks,
   sections, clauses, and appendix resolution.
4. Version Mutation Diff Calculator: multi-field updates, absent AST snapshots,
   and edge diff tracking.
5. FastAPI REST API endpoints: special characters in statutory codes with slashes,
   missing query/body parameters, and offline database health handling.
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

from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingDocumentSession,
    StagingEdge,
    StagingManager,
    StagingStatus,
)
from rag_eval.legal.schemas import (
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
)
from rag_eval.legal.web.app import create_app
from rag_eval.legal.web.service import (
    DiffCalculator,
    HumanPromotionEngine,
    PreFlightValidator,
    TreeHierarchyBuilder,
)

SAMPLE_DECREE_TEXT = """
CHƯƠNG I
QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
1. Nghị định này quy định về xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ.
2. Đối tượng áp dụng bao gồm tổ chức, cá nhân vi phạm.
a) Người điều khiển xe cơ giới;
b) Người điều khiển xe thô sơ.

CHƯƠNG II
HÀNH VI VI PHẠM VÀ HÌNH THỨC XỬ PHẠT

Điều 5. Xử phạt người điều khiển xe ô tô
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với hành vi sau:
a) Không chấp hành hiệu lệnh của biển báo;
b) Dừng xe không có tín hiệu báo trước.
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
            return [{"id": str(uuid.uuid4()), "path": p} for p in paths]
        return []

    conn.fetch.side_effect = mock_fetch

    def mock_fetchval(query: str, *args: Any) -> Any:
        if "INSERT INTO documents" in query:
            return "11111111-2222-3333-4444-555555555555"
        if "SELECT 1" in query:
            return 1
        return 1

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


# ==============================================================================
# 1. Adversarial Pre-Flight Validation Tests
# ==============================================================================
def test_preflight_rejection_empty_chunks_session(staging_dir: Path) -> None:
    """Verifies that a staging session containing zero chunks is strictly rejected."""
    now = datetime.datetime.now(datetime.UTC)
    session = StagingDocumentSession(
        doc_code="100/2019/NĐ-CP",
        title="Empty Decree",
        status=StagingStatus.DRAFT,
        effective_date=datetime.date(2020, 1, 15),
        created_at=now,
        updated_at=now,
        chunks=[],
        edges=[],
    )
    validator = PreFlightValidator()
    result = validator.validate(session)

    assert result.passed is False
    assert result.status == "FAILED"
    rules = [i.rule for i in result.issues if i.blocking]
    assert "PARENT_CHILD_CONTINUITY" in rules


@pytest.mark.parametrize(
    "invalid_path",
    [
        "",  # Empty path
        " ",  # Whitespace path
        ".c_1.a_1",  # Leading dot
        "100_2019_nd_cp.c_1.",  # Trailing dot
        "100_2019_nd_cp..c_1",  # Consecutive dots
        "100_2019_nd_cp.c 1.a 1",  # Spaces in segment
        "100_2019_nd_cp.c@1.a#1",  # Invalid characters
        "100_2019_nd_cp/c_1/a_1",  # Slashes instead of dots
    ],
)
def test_preflight_rejection_malformed_ltree_syntax(
    staging_dir: Path, invalid_path: str
) -> None:
    """Verifies that any violation of PostgreSQL ltree dot-syntax triggers blocking LTREE_PATH_SYNTAX."""
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    # Force invalid ltree path on first chunk
    session.chunks[0].path = invalid_path

    validator = PreFlightValidator()
    result = validator.validate(session)

    assert result.passed is False
    assert result.status == "FAILED"
    rules = [i.rule for i in result.issues if i.blocking]
    assert "LTREE_PATH_SYNTAX" in rules


def test_preflight_rejection_root_code_misalignment(staging_dir: Path) -> None:
    """Verifies that chunks prefixed with an unrelated document code are rejected."""
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    # Corrupt prefix from 100_2019_nd_cp to 123_2021_nd_cp
    session.chunks[0].path = "123_2021_nd_cp.c_i.a_1.c_1"

    validator = PreFlightValidator()
    result = validator.validate(session)

    assert result.passed is False
    issue = next(i for i in result.issues if i.rule == "ROOT_CODE_ALIGNMENT")
    assert issue.blocking is True
    assert "does not align with sanitized document code" in issue.message


@pytest.mark.parametrize(
    "doc_eff, doc_exp, chunk_eff, chunk_exp, expected_violation",
    [
        (None, None, datetime.date(2020, 1, 1), None, "Document effective_date cannot be null"),
        (
            datetime.date(2020, 1, 1),
            datetime.date(2019, 1, 1),
            datetime.date(2020, 1, 1),
            None,
            "cannot be earlier than effective_date",
        ),
        (
            datetime.date(2020, 1, 1),
            None,
            None,
            None,
            "has null effective_date",
        ),
        (
            datetime.date(2020, 1, 1),
            None,
            datetime.date(2020, 1, 1),
            datetime.date(2019, 12, 31),
            "is earlier than effective_date",
        ),
    ],
)
def test_preflight_rejection_statutory_dates(
    staging_dir: Path,
    doc_eff: datetime.date | None,
    doc_exp: datetime.date | None,
    chunk_eff: datetime.date | None,
    chunk_exp: datetime.date | None,
    expected_violation: str,
) -> None:
    """Verifies that invalid statutory date logic (null effective dates, inverted ranges) is blocked."""
    now = datetime.datetime.now(datetime.UTC)
    chunk = StagingChunk(
        path="100_2019_nd_cp.c_i.a_1",
        verbatim_text="Sample text",
        contextualized_text="Sample context",
        effective_date=chunk_eff or datetime.date(2020, 1, 1),
        expiration_date=chunk_exp,
    )
    if chunk_eff is None:
        object.__setattr__(chunk, "effective_date", None)

    session = StagingDocumentSession(
        doc_code="100/2019/NĐ-CP",
        title="Test Dates",
        status=StagingStatus.DRAFT,
        effective_date=doc_eff or datetime.date(2020, 1, 1),
        expiration_date=doc_exp,
        created_at=now,
        updated_at=now,
        chunks=[chunk],
    )
    if doc_eff is None:
        object.__setattr__(session, "effective_date", None)

    validator = PreFlightValidator()
    result = validator.validate(session)

    assert result.passed is False
    date_issues = [i for i in result.issues if i.rule == "STATUTORY_DATES"]
    assert len(date_issues) >= 1
    assert any(expected_violation in i.message for i in date_issues)


@pytest.mark.parametrize("bad_text", ["", "   ", "\n\t  \r\n"])
def test_preflight_rejection_empty_and_whitespace_text(
    staging_dir: Path, bad_text: str
) -> None:
    """Verifies that empty or whitespace-only verbatim/contextualized text is blocked."""
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    # Empty verbatim text
    session.chunks[0].verbatim_text = bad_text
    validator = PreFlightValidator()
    result = validator.validate(session)

    assert result.passed is False
    cg_issues = [i for i in result.issues if i.rule == "CONTENT_GROUNDING"]
    assert len(cg_issues) >= 1
    assert cg_issues[0].blocking is True

    # Empty contextualized text
    session.chunks[0].verbatim_text = "Valid text"
    session.chunks[0].contextualized_text = bad_text
    result2 = validator.validate(session)
    assert result2.passed is False
    assert any(i.rule == "CONTENT_GROUNDING" for i in result2.issues)


def test_preflight_rejection_bad_graph_edges(staging_dir: Path) -> None:
    """Verifies that orphan edge sources and unanchored edge targets are blocked."""
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    valid_src = session.chunks[0].path

    # 1. Edge with non-existent source
    session.edges.append(
        StagingEdge(
            source_path="100_2019_nd_cp.phantom_nonexistent_chunk",
            target_path=valid_src,
            relation_type="REFERENCES",
        )
    )

    # 2. Edge with neither target_path nor target_external_ref
    session.edges.append(
        StagingEdge(
            source_path=valid_src,
            target_path=None,
            target_external_ref=None,
            relation_type="REFERENCES",
        )
    )

    validator = PreFlightValidator()
    result = validator.validate(session)

    assert result.passed is False
    edge_issues = [i for i in result.issues if i.rule == "GRAPH_EDGE_INTEGRITY"]
    assert len(edge_issues) == 2
    assert all(i.blocking for i in edge_issues)


def test_preflight_rejection_duplicate_path_collision(staging_dir: Path) -> None:
    """Verifies that duplicate chunk paths are detected and blocked."""
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    # Clone chunk to create duplicate path
    session.chunks.append(session.chunks[0].model_copy())

    validator = PreFlightValidator()
    result = validator.validate(session)

    assert result.passed is False
    dup_issues = [i for i in result.issues if i.rule == "DUPLICATE_PATH_COLLISION"]
    assert len(dup_issues) == 1
    assert dup_issues[0].blocking is True
    assert dup_issues[0].path == session.chunks[0].path


# ==============================================================================
# 2. Human Promotion Engine & Atomic Rollback Verification
# ==============================================================================
@pytest.mark.asyncio
async def test_promotion_engine_rejects_preflight_failure_without_db_call(
    staging_dir: Path, mock_db_pool: Any
) -> None:
    """Verifies that HumanPromotionEngine blocks invalid sessions before any DB write."""
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    # Corrupt session
    session.chunks[0].verbatim_text = ""
    mgr.save_session(session)

    engine = HumanPromotionEngine(staging_manager=mgr)
    with pytest.raises(LegalDomainError) as exc_info:
        await engine.promote_session(
            doc_code="100/2019/NĐ-CP",
            pool=mock_db_pool,
        )

    assert exc_info.value.error_code == E_CORPUS_INTEGRITY_VIOLATION
    assert "Pre-flight validation failed" in str(exc_info.value)

    # Verify session on disk remains DRAFT
    reloaded = mgr.load_session("100/2019/NĐ-CP")
    assert reloaded.status == StagingStatus.DRAFT
    assert reloaded.promoted_at is None


@pytest.mark.asyncio
async def test_promotion_engine_fails_on_unassigned_source_uuid_and_preserves_status(
    staging_dir: Path, mock_db_pool: Any
) -> None:
    """Verifies that if PostgresBulkLoader fails to return a UUID for a chunk, promotion aborts without mutating session."""
    mgr = StagingManager(staging_dir=staging_dir)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )
    # Transition to APPROVED
    mgr.update_session_status(
        doc_code="100/2019/NĐ-CP",
        status=StagingStatus.APPROVED,
        actor="HUMAN:senior_reviewer",
        description="Approved for production",
    )

    # Attach an edge
    mgr.add_edges(
        doc_code="100/2019/NĐ-CP",
        edges=[
            StagingEdge(
                source_path=session.chunks[0].path,
                target_path=session.chunks[1].path,
                relation_type="REFERENCES",
            )
        ],
    )

    # Mock conn.fetch returning empty list (simulating missing chunk UUID in returning clause)
    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.side_effect = None
    conn.fetch.return_value = []

    engine = HumanPromotionEngine(staging_manager=mgr)
    with pytest.raises(LegalDomainError) as exc_info:
        await engine.promote_session(
            doc_code="100/2019/NĐ-CP",
            pool=mock_db_pool,
            compute_embeddings=False,
        )

    assert exc_info.value.error_code == E_CORPUS_INTEGRITY_VIOLATION
    assert "was not assigned a valid UUID" in str(exc_info.value)

    # Crucial assertion: Session status must NOT be PROMOTED!
    reloaded = mgr.load_session("100/2019/NĐ-CP")
    assert reloaded.status == StagingStatus.APPROVED
    assert reloaded.promoted_at is None


@pytest.mark.asyncio
async def test_promotion_engine_db_exception_preserves_staging_state(
    staging_dir: Path, mock_db_pool: Any
) -> None:
    """Verifies that when database execution fails (e.g. timeout or constraint error), staging state is untouched."""
    mgr = StagingManager(staging_dir=staging_dir)
    mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )
    mgr.update_session_status(
        doc_code="100/2019/NĐ-CP",
        status=StagingStatus.APPROVED,
        actor="HUMAN:reviewer",
        description="Ready",
    )

    conn = mock_db_pool.acquire.return_value.__aenter__.return_value
    conn.executemany.side_effect = RuntimeError("Database connection reset by peer")

    engine = HumanPromotionEngine(staging_manager=mgr)
    with pytest.raises(RuntimeError, match="Database connection reset by peer"):
        await engine.promote_session(
            doc_code="100/2019/NĐ-CP",
            pool=mock_db_pool,
            compute_embeddings=False,
        )

    # Assert session is preserved in APPROVED state and not corrupted
    reloaded = mgr.load_session("100/2019/NĐ-CP")
    assert reloaded.status == StagingStatus.APPROVED
    assert reloaded.promoted_at is None


# ==============================================================================
# 3. Boundary Cases in Tree Hierarchy Building
# ==============================================================================
def test_tree_builder_empty_chunks(staging_dir: Path) -> None:
    """Verifies that TreeHierarchyBuilder handles a session with zero chunks gracefully."""
    now = datetime.datetime.now(datetime.UTC)
    session = StagingDocumentSession(
        doc_code="EMPTY_DOC",
        title="Empty Document",
        status=StagingStatus.DRAFT,
        effective_date=datetime.date(2025, 1, 1),
        created_at=now,
        updated_at=now,
        chunks=[],
    )
    builder = TreeHierarchyBuilder()
    tree = builder.build_tree(session)

    assert tree.doc_code == "EMPTY_DOC"
    assert tree.total_nodes == 1
    assert tree.root.node_type == "DOCUMENT"
    assert len(tree.root.children) == 0


def test_tree_builder_deeply_nested_hierarchy(staging_dir: Path) -> None:
    """Verifies that TreeHierarchyBuilder builds deep 6-tier hierarchy (Doc > Chap > Sec > Art > Clause > Point)."""
    now = datetime.datetime.now(datetime.UTC)
    deep_chunks = [
        StagingChunk(
            path="test_deep.c_i.s_1.a_5.c_3.p_a",
            verbatim_text="Điểm a Khoản 3 Điều 5 Mục 1 Chương I",
            contextualized_text="[Deep Context]",
            effective_date=datetime.date(2025, 1, 1),
        ),
        StagingChunk(
            path="test_deep.c_i.s_1.a_5.c_3.p_b",
            verbatim_text="Điểm b Khoản 3 Điều 5 Mục 1 Chương I",
            contextualized_text="[Deep Context B]",
            effective_date=datetime.date(2025, 1, 1),
        ),
    ]
    session = StagingDocumentSession(
        doc_code="test_deep",
        title="Deep Document",
        status=StagingStatus.DRAFT,
        effective_date=datetime.date(2025, 1, 1),
        created_at=now,
        updated_at=now,
        chunks=deep_chunks,
    )

    builder = TreeHierarchyBuilder()
    tree = builder.build_tree(session)

    assert tree.total_nodes == 7  # root + c_i + s_1 + a_5 + c_3 + p_a + p_b
    root = tree.root
    assert root.node_type == "DOCUMENT"

    c_node = root.children[0]
    assert c_node.node_type == "CHAPTER"
    assert c_node.label == "Chương I"

    s_node = c_node.children[0]
    assert s_node.node_type == "SECTION"
    assert s_node.label == "Mục 1"

    a_node = s_node.children[0]
    assert a_node.node_type == "ARTICLE"
    assert a_node.label == "Điều 5"

    clause_node = a_node.children[0]
    assert clause_node.node_type == "CLAUSE"
    assert clause_node.label == "Khoản 3"

    assert len(clause_node.children) == 2
    p_a = clause_node.children[0]
    assert p_a.node_type == "POINT"
    assert p_a.label == "Điểm a"
    assert p_a.verbatim_text == "Điểm a Khoản 3 Điều 5 Mục 1 Chương I"


def test_tree_builder_out_of_order_chunks_deterministic(staging_dir: Path) -> None:
    """Verifies that inserting chunk paths in reverse or random order yields an identically sorted tree."""
    now = datetime.datetime.now(datetime.UTC)
    chunks_unordered = [
        StagingChunk(
            path="test_order.c_ii.a_10",
            verbatim_text="Điều 10",
            contextualized_text="Context 10",
            effective_date=datetime.date(2025, 1, 1),
        ),
        StagingChunk(
            path="test_order.c_i.a_1",
            verbatim_text="Điều 1",
            contextualized_text="Context 1",
            effective_date=datetime.date(2025, 1, 1),
        ),
        StagingChunk(
            path="test_order.c_i.a_2",
            verbatim_text="Điều 2",
            contextualized_text="Context 2",
            effective_date=datetime.date(2025, 1, 1),
        ),
    ]
    session = StagingDocumentSession(
        doc_code="test_order",
        title="Unordered Test",
        status=StagingStatus.DRAFT,
        effective_date=datetime.date(2025, 1, 1),
        created_at=now,
        updated_at=now,
        chunks=chunks_unordered,
    )

    builder = TreeHierarchyBuilder()
    tree = builder.build_tree(session)

    # Root should have 2 children in alphabetical/canonical order: c_i then c_ii
    assert len(tree.root.children) == 2
    assert tree.root.children[0].path == "test_order.c_i"
    assert tree.root.children[1].path == "test_order.c_ii"
    assert len(tree.root.children[0].children) == 2
    assert tree.root.children[0].children[0].path == "test_order.c_i.a_1"
    assert tree.root.children[0].children[1].path == "test_order.c_i.a_2"


# ==============================================================================
# 4. Boundary Cases in Diff Calculator
# ==============================================================================
def test_diff_calculator_without_ast_baseline(staging_dir: Path) -> None:
    """Verifies that if raw_ast_snapshot is None, all current chunks are treated as ADDED."""
    now = datetime.datetime.now(datetime.UTC)
    chunks = [
        StagingChunk(
            path="doc.c_1.a_1",
            verbatim_text="Verbatim text",
            contextualized_text="Context text",
            effective_date=datetime.date(2025, 1, 1),
        )
    ]
    session = StagingDocumentSession(
        doc_code="doc",
        title="No Baseline Doc",
        status=StagingStatus.DRAFT,
        effective_date=datetime.date(2025, 1, 1),
        created_at=now,
        updated_at=now,
        chunks=chunks,
        raw_ast_snapshot=None,
    )

    calculator = DiffCalculator()
    diff = calculator.compute_diff(session)

    assert diff.total_changes == 1
    assert len(diff.added_chunks) == 1
    assert diff.added_chunks[0].path == "doc.c_1.a_1"
    assert len(diff.deleted_chunks) == 0
    assert len(diff.modified_chunks) == 0


def test_diff_calculator_multi_field_modifications(staging_dir: Path) -> None:
    """Verifies that simultaneous changes to verbatim_text, contextualized_text, and metadata are tracked."""
    now = datetime.datetime.now(datetime.UTC)
    baseline = [
        {
            "path": "doc.c_1.a_1",
            "verbatim_text": "Old verbatim",
            "contextualized_text": "Old contextualized",
            "metadata": {"version": 1, "type": "initial"},
            "effective_date": "2025-01-01",
        }
    ]
    current = [
        StagingChunk(
            path="doc.c_1.a_1",
            verbatim_text="New verbatim",
            contextualized_text="New contextualized",
            metadata={"version": 2, "type": "updated"},
            effective_date=datetime.date(2025, 1, 1),
        )
    ]
    session = StagingDocumentSession(
        doc_code="doc",
        title="Multi-Field Diff",
        status=StagingStatus.DRAFT,
        effective_date=datetime.date(2025, 1, 1),
        created_at=now,
        updated_at=now,
        chunks=current,
        raw_ast_snapshot=baseline,
    )

    calculator = DiffCalculator()
    diff = calculator.compute_diff(session)

    assert len(diff.modified_chunks) == 1
    mod = diff.modified_chunks[0]
    assert mod["path"] == "doc.c_1.a_1"
    assert set(mod["modified_fields"]) == {"verbatim_text", "contextualized_text", "metadata"}

    field_changes = {e.field_name: e for e in diff.diff_entries if e.change_type == "MODIFIED"}
    assert field_changes["verbatim_text"].old_value == "Old verbatim"
    assert field_changes["verbatim_text"].new_value == "New verbatim"
    assert field_changes["contextualized_text"].old_value == "Old contextualized"
    assert field_changes["metadata"].new_value == {"version": 2, "type": "updated"}


# ==============================================================================
# 5. FastAPI REST API Endpoint Robustness & Edge Cases
# ==============================================================================
@pytest.mark.asyncio
async def test_api_complex_statutory_codes_with_slashes(client: httpx.AsyncClient) -> None:
    """Verifies that statutory codes with slashes (e.g. 100/2019/NĐ-CP, 01/2020/TT-BGTVT) route flawlessly across all endpoints."""
    complex_codes = [
        "100/2019/NĐ-CP",
        "01/2020/TT-BGTVT",
        "QCVN 41:2019/BGTVT",
    ]

    for code in complex_codes:
        # 1. Create
        create_resp = await client.post(
            "/api/staging/raw",
            json={
                "doc_code": code,
                "title": f"Title for {code}",
                "raw_text": SAMPLE_DECREE_TEXT,
                "effective_date": "2020-01-01",
            },
        )
        assert create_resp.status_code == 200
        assert create_resp.json()["doc_code"] == code

        # 2. Get Detail
        detail_resp = await client.get(f"/api/staging/{code}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["doc_code"] == code

        # 3. Get Tree
        tree_resp = await client.get(f"/api/staging/{code}/tree")
        assert tree_resp.status_code == 200
        assert tree_resp.json()["doc_code"] == code

        # 4. Validate
        val_resp = await client.get(f"/api/staging/{code}/validate")
        assert val_resp.status_code == 200
        assert val_resp.json()["status"] == "PASSED"

        # 5. Get Diff
        diff_resp = await client.get(f"/api/staging/{code}/diff")
        assert diff_resp.status_code == 200

        # 6. Get Raw
        raw_resp = await client.get(f"/api/staging/{code}/raw")
        assert raw_resp.status_code == 200

        # 7. Delete
        del_resp = await client.delete(f"/api/staging/{code}")
        assert del_resp.status_code == 200


@pytest.mark.asyncio
async def test_api_delete_edge_with_query_params_and_validation(client: httpx.AsyncClient) -> None:
    """Verifies edge deletion with query parameters and bad request when missing required fields."""
    await client.post(
        "/api/staging/raw",
        json={
            "doc_code": "100/2019/NĐ-CP",
            "title": "Nghị định 100",
            "raw_text": SAMPLE_DECREE_TEXT,
            "effective_date": "2020-01-15",
        },
    )

    # Add edge
    await client.post(
        "/api/staging/100/2019/NĐ-CP/edges",
        json=[
            {
                "source_path": "100_2019_nd_cp.c_i.a_1.c_1",
                "target_path": "100_2019_nd_cp.c_i.a_1.c_2",
                "relation_type": "REFERENCES",
            }
        ],
    )

    # Missing parameters -> 400
    bad_del = await client.request("DELETE", "/api/staging/100/2019/NĐ-CP/edges")
    assert bad_del.status_code == 400
    assert "Must provide at least source_path and relation_type" in bad_del.json()["detail"]

    # Delete with query params
    good_del = await client.delete(
        "/api/staging/100/2019/NĐ-CP/edges",
        params={
            "source_path": "100_2019_nd_cp.c_i.a_1.c_1",
            "target_path": "100_2019_nd_cp.c_i.a_1.c_2",
            "relation_type": "REFERENCES",
        },
    )
    assert good_del.status_code == 200
    assert len(good_del.json()["edges"]) == 0


@pytest.mark.asyncio
async def test_api_health_check_database_offline(staging_dir: Path) -> None:
    """Verifies GET /api/health returns database: UNAVAILABLE when db_pool is None or failing."""
    failing_pool = MagicMock()
    conn = AsyncMock()
    conn.fetchval.side_effect = RuntimeError("Connection refused")
    failing_pool.acquire.return_value.__aenter__.return_value = conn

    app = create_app(staging_dir=staging_dir, db_pool=failing_pool)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "OK"
        assert data["database"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_api_patch_nonexistent_document_raises_400(client: httpx.AsyncClient) -> None:
    """Verifies that patching a non-existent document returns 400 with LegalDomainError."""
    resp = await client.post(
        "/api/staging/NON_EXISTENT_DOC/patch",
        json={"updated_chunks": [], "removed_paths": []},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == E_CORPUS_INTEGRITY_VIOLATION
