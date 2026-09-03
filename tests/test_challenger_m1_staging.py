"""Adversarial stress and boundary tests for Staging Lifecycle & MCP Tool Decoupling (Milestone 1).

Covers:
- Strict state transitions (DRAFT -> AGENT_COMMITTED -> APPROVED -> PROMOTED).
- State transition timestamp validation (committed_at, promoted_at).
- Strict rejection of invalid/unresolvable edge source paths during stg_commit.
- Preservation of staging session JSON on disk after stg_commit (zero deletion/DB writes).
- Resilience against malformed JSON, corrupt session files, missing schema fields.
- Edge deduplication semantics (composite key collision, external references).
- Zero-DB dependency decoupling for agent staging operations.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingDocumentSession,
    StagingEdge,
    StagingManager,
    StagingStatus,
)
from rag_eval.legal.mcp.server import LegalMCPServer
from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.schemas import (
    E_AST_GROUNDING_VALIDATION,
    E_CORPUS_INTEGRITY_VIOLATION,
    LegalDomainError,
)

SAMPLE_DECREE_RAW = """
CHƯƠNG I
QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
Nghị định này quy định về xử phạt vi phạm hành chính trong lĩnh vực giao thông.

CHƯƠNG II
HÀNH VI VI PHẠM

Điều 5. Xử phạt người điều khiển xe ô tô
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với hành vi sau:
a) Không chấp hành hiệu lệnh biển báo;
b) Dừng xe không có tín hiệu báo trước.
"""


# ------------------------------------------------------------------------------
# 1. Staging Status Transitions & State Machine Stress Tests
# ------------------------------------------------------------------------------
def test_staging_lifecycle_full_status_transitions(tmp_path: Path) -> None:
    """Verifies complete sequential status lifecycle: DRAFT -> AGENT_COMMITTED -> APPROVED -> PROMOTED."""
    mgr = StagingManager(staging_dir=tmp_path)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_RAW,
        effective_date=datetime.date(2020, 1, 15),
    )

    # Initial state must be DRAFT
    assert session.status == StagingStatus.DRAFT
    assert session.committed_at is None
    assert session.promoted_at is None
    assert len(session.mutation_history) == 1
    assert session.mutation_history[0].action_type == "CREATED"

    # Step 1: Agent commits session
    s_committed = mgr.update_session_status(
        doc_code="100/2019/NĐ-CP",
        status=StagingStatus.AGENT_COMMITTED,
        actor="AGENT",
        description="Agent finished structuring decree",
    )
    assert s_committed.status == StagingStatus.AGENT_COMMITTED
    assert s_committed.committed_at is not None
    assert s_committed.promoted_at is None
    assert len(s_committed.mutation_history) == 2
    assert s_committed.mutation_history[-1].action_type == "STATUS_TRANSITION_AGENT_COMMITTED"
    assert s_committed.mutation_history[-1].diff_payload == {
        "old_status": "DRAFT",
        "new_status": "AGENT_COMMITTED",
    }

    # Step 2: Human reviewer approves
    s_approved = mgr.update_session_status(
        doc_code="100/2019/NĐ-CP",
        status=StagingStatus.APPROVED,
        actor="HUMAN:reviewer_bob",
        description="Legal validation passed",
    )
    assert s_approved.status == StagingStatus.APPROVED
    assert s_approved.committed_at is not None  # Preserved
    assert s_approved.promoted_at is None
    assert len(s_approved.mutation_history) == 3
    assert s_approved.mutation_history[-1].actor == "HUMAN:reviewer_bob"

    # Step 3: Human promotes to production PostgreSQL
    s_promoted = mgr.update_session_status(
        doc_code="100/2019/NĐ-CP",
        status=StagingStatus.PROMOTED,
        actor="SYSTEM",
        description="Promoted to production",
    )
    assert s_promoted.status == StagingStatus.PROMOTED
    assert s_promoted.committed_at is not None
    assert s_promoted.promoted_at is not None
    assert len(s_promoted.mutation_history) == 4
    assert s_promoted.mutation_history[-1].action_type == "STATUS_TRANSITION_PROMOTED"


def test_staging_status_invalid_enum_rejected() -> None:
    """Verifies that invalid status enum strings are rejected by Pydantic validation."""
    with pytest.raises(ValidationError):
        StagingDocumentSession(
            doc_code="TEST_INVALID_STATUS",
            title="Test Invalid",
            status="INVALID_STATUS_VALUE",  # type: ignore[arg-type]
            effective_date=datetime.date(2025, 1, 1),
        )


# ------------------------------------------------------------------------------
# 2. Source Path Grounding & Rejection during stg_commit
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stg_commit_rejects_nonexistent_source_path(tmp_path: Path) -> None:
    """Verifies stg_commit raises LegalDomainError(E_AST_GROUNDING_VALIDATION) when edge source_path is phantom."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    stg_mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_RAW,
        effective_date=datetime.date(2020, 1, 15),
    )

    tools = LegalMCPTools(staging_manager=stg_mgr)

    # Attach edge with non-existent source chunk path
    phantom_edge = {
        "source_path": "100_2019_nd_cp.c_ii.a_999.c_1",
        "target_path": "100_2019_nd_cp.c_i.a_1",
        "relation_type": "REFERENCES",
    }
    await tools.stg_add_edges(doc_code="100/2019/NĐ-CP", edges=[phantom_edge])

    # stg_commit must fail
    with pytest.raises(LegalDomainError) as exc_info:
        await tools.stg_commit(doc_code="100/2019/NĐ-CP")

    assert exc_info.value.error_code == E_AST_GROUNDING_VALIDATION
    assert "Invalid edge source path" in exc_info.value.message
    assert "100_2019_nd_cp.c_ii.a_999.c_1" in exc_info.value.message

    # Verify session remains DRAFT and was NOT committed
    session = stg_mgr.load_session("100/2019/NĐ-CP")
    assert session.status == StagingStatus.DRAFT
    assert session.committed_at is None


@pytest.mark.asyncio
async def test_stg_commit_accepts_valid_source_with_external_target(tmp_path: Path) -> None:
    """Verifies stg_commit succeeds when source_path exists even if target_path is external or None."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    session = stg_mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_RAW,
        effective_date=datetime.date(2020, 1, 15),
    )
    valid_source = session.chunks[0].path

    tools = LegalMCPTools(staging_manager=stg_mgr)
    external_edge = {
        "source_path": valid_source,
        "target_path": None,
        "target_external_ref": "Điều 8 Luật Giao thông đường bộ 2008",
        "relation_type": "REFERENCES",
        "citation_text": "Căn cứ theo Điều 8 Luật GTĐB",
    }
    await tools.stg_add_edges(doc_code="100/2019/NĐ-CP", edges=[external_edge])

    res = await tools.stg_commit(doc_code="100/2019/NĐ-CP")
    assert res.status == "AGENT_COMMITTED"
    assert res.total_edges == 1

    committed_session = stg_mgr.load_session("100/2019/NĐ-CP")
    assert committed_session.status == StagingStatus.AGENT_COMMITTED
    assert committed_session.edges[0].target_external_ref == "Điều 8 Luật Giao thông đường bộ 2008"


# ------------------------------------------------------------------------------
# 3. File Preservation on Disk & Zero DB Writes
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stg_commit_strictly_preserves_file_on_disk(tmp_path: Path) -> None:
    """Verifies that stg_commit NEVER deletes or unlinks the staging file from disk."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    stg_mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_RAW,
        effective_date=datetime.date(2020, 1, 15),
    )

    staging_file = tmp_path / "100_2019_nd_cp.json"
    assert staging_file.exists()

    # Instantiate MCP tools with NO database pool (pool=None)
    tools = LegalMCPTools(pool=None, staging_manager=stg_mgr)
    commit_res = await tools.stg_commit(doc_code="100/2019/NĐ-CP")

    assert commit_res.status == "AGENT_COMMITTED"
    # File MUST still exist on disk
    assert staging_file.exists()
    assert staging_file.stat().st_size > 0

    # Parse raw file on disk to confirm serialized content
    content = json.loads(staging_file.read_text(encoding="utf-8"))
    assert content["status"] == "AGENT_COMMITTED"
    assert content["committed_at"] is not None
    assert len(content["mutation_history"]) >= 2


@pytest.mark.asyncio
async def test_mcp_server_stg_commit_json_rpc_dispatch(tmp_path: Path) -> None:
    """Verifies MCP JSON-RPC protocol dispatch for stg_commit without DB pool."""
    stg_mgr = StagingManager(staging_dir=tmp_path)
    stg_mgr.create_session_from_raw(
        doc_code="46/2016/NĐ-CP",
        title="Nghị định 46",
        raw_text=SAMPLE_DECREE_RAW,
        effective_date=datetime.date(2016, 8, 1),
    )

    tools = LegalMCPTools(pool=None, staging_manager=stg_mgr)
    server = LegalMCPServer(tools=tools)

    req = {
        "jsonrpc": "2.0",
        "id": 101,
        "method": "tools/call",
        "params": {
            "name": "mcp_traffic_stg_commit",
            "arguments": {"doc_code": "46/2016/NĐ-CP"},
        },
    }
    resp = await server.handle_request_dict(req)
    assert resp is not None
    assert "result" in resp
    assert resp["result"]["status"] == "AGENT_COMMITTED"
    assert resp["result"]["doc_code"] == "46/2016/NĐ-CP"


# ------------------------------------------------------------------------------
# 4. Error Handling: Malformed JSON, Corrupted Sessions, Missing Files
# ------------------------------------------------------------------------------
def test_load_nonexistent_session_raises_domain_error(tmp_path: Path) -> None:
    """Verifies loading a non-existent document code raises LegalDomainError(E_CORPUS_INTEGRITY_VIOLATION)."""
    mgr = StagingManager(staging_dir=tmp_path)
    with pytest.raises(LegalDomainError) as exc_info:
        mgr.load_session("NON_EXISTENT_DOC")
    assert exc_info.value.error_code == E_CORPUS_INTEGRITY_VIOLATION
    assert "does not exist" in exc_info.value.message


def test_load_corrupted_json_session_raises_domain_error(tmp_path: Path) -> None:
    """Verifies loading a syntactically invalid JSON staging file raises LegalDomainError."""
    mgr = StagingManager(staging_dir=tmp_path)
    bad_file = tmp_path / "broken_doc.json"
    bad_file.write_text("{\n  \"doc_code\": \"broken\",\n  \"chunks\": [INVALID_JSON_HERE", encoding="utf-8")

    with pytest.raises(LegalDomainError) as exc_info:
        mgr.load_session("broken_doc")
    assert exc_info.value.error_code == E_CORPUS_INTEGRITY_VIOLATION
    assert "is corrupted" in exc_info.value.message


def test_list_sessions_skips_malformed_and_hidden_files(tmp_path: Path) -> None:
    """Verifies list_sessions gracefully ignores corrupt files, hidden files, and empty directories."""
    mgr = StagingManager(staging_dir=tmp_path)

    # 1. Valid session
    mgr.create_session_from_raw(
        doc_code="VALID_DOC_1",
        title="Valid Document 1",
        raw_text=SAMPLE_DECREE_RAW,
        effective_date=datetime.date(2025, 1, 1),
    )

    # 2. Corrupted JSON file
    (tmp_path / "corrupted.json").write_text("NOT_A_JSON_STRING", encoding="utf-8")

    # 3. Schema invalid file (missing required fields)
    (tmp_path / "schema_invalid.json").write_text(json.dumps({"some_key": "some_value"}), encoding="utf-8")

    # 4. Hidden file
    (tmp_path / ".hidden.json").write_text(json.dumps({"doc_code": "HIDDEN"}), encoding="utf-8")

    summaries = mgr.list_sessions()
    assert len(summaries) == 1
    assert summaries[0].doc_code == "VALID_DOC_1"


def test_delete_nonexistent_session_returns_false(tmp_path: Path) -> None:
    """Verifies deleting a non-existent session safely returns False without raising."""
    mgr = StagingManager(staging_dir=tmp_path)
    assert mgr.delete_session("NON_EXISTENT_DOC") is False


# ------------------------------------------------------------------------------
# 5. Graph Edge Deduplication Semantics
# ------------------------------------------------------------------------------
def test_staging_edge_deduplication_semantics(tmp_path: Path) -> None:
    """Verifies comprehensive edge deduplication rules:
    - Same (source, target, relation_type) updates in-place.
    - Same (source, target) with different relation_type creates distinct edges.
    - Same source with target=None and different relation_type creates distinct edges.
    """
    mgr = StagingManager(staging_dir=tmp_path)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_RAW,
        effective_date=datetime.date(2020, 1, 15),
    )
    src = session.chunks[0].path
    tgt = session.chunks[1].path

    e1 = StagingEdge(
        source_path=src,
        target_path=tgt,
        relation_type="REFERENCES",
        citation_text="Initial citation",
    )
    e2 = StagingEdge(
        source_path=src,
        target_path=tgt,
        relation_type="REFERENCES",
        citation_text="Overwritten citation",
    )
    e3 = StagingEdge(
        source_path=src,
        target_path=tgt,
        relation_type="SANCTIONS",
        citation_text="Different relation type",
    )
    e4 = StagingEdge(
        source_path=src,
        target_path=None,
        target_external_ref="QCVN 41:2019/BGTVT",
        relation_type="REFERENCES",
    )
    e5 = StagingEdge(
        source_path=src,
        target_path=None,
        target_external_ref="QCVN 41:2019/BGTVT",
        relation_type="OVERRIDES",
    )

    mgr.add_edges("100/2019/NĐ-CP", [e1, e2, e3, e4, e5])
    reloaded = mgr.load_session("100/2019/NĐ-CP")

    # e1 and e2 collide on (src, tgt, REFERENCES) -> length 4 distinct edges
    assert len(reloaded.edges) == 4
    ref_edge = next(e for e in reloaded.edges if e.target_path == tgt and e.relation_type == "REFERENCES")
    assert ref_edge.citation_text == "Overwritten citation"


# ------------------------------------------------------------------------------
# 6. Surgical Chunk Patching Edge Cases
# ------------------------------------------------------------------------------
def test_staging_chunk_patching_edge_cases(tmp_path: Path) -> None:
    """Verifies edge cases in patch_chunks: removing non-existent paths, patching new chunk."""
    mgr = StagingManager(staging_dir=tmp_path)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_RAW,
        effective_date=datetime.date(2020, 1, 15),
    )
    initial_count = len(session.chunks)

    # Remove non-existent path should be a no-op
    s_removed = mgr.patch_chunks(
        doc_code="100/2019/NĐ-CP",
        updated_chunks=[],
        removed_paths=["non.existent.path"],
    )
    assert len(s_removed.chunks) == initial_count

    # Add a brand new chunk path via surgical update
    new_chunk = StagingChunk(
        path="100_2019_nd_cp.c_ii.a_5.c_99",
        verbatim_text="Khoản 99. Quy định mới bổ sung",
        contextualized_text="[Nghị định 100] > [Điều 5] > [Khoản 99]",
        effective_date=datetime.date(2020, 1, 15),
    )
    s_added = mgr.patch_chunks(
        doc_code="100/2019/NĐ-CP",
        updated_chunks=[new_chunk],
    )
    assert len(s_added.chunks) == initial_count + 1
    assert any(c.path == "100_2019_nd_cp.c_ii.a_5.c_99" for c in s_added.chunks)
