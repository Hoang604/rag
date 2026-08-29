"""Adversarial stress test harness for Milestone R6 verification gate.

Tests:
1. Complete removal of duplicate tests/legal/schemas.py and zero legacy schema imports across tests and src.
2. MockDatabasePool hybrid search ranking with Vietnamese synonyms, token overlap, and absence of hardcoded score bonuses (+50.0).
3. MockDatabasePool graph traversal cycle prevention across cyclic structures with direction="BOTH" and arbitrary depth.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import pytest

from rag_eval.legal.schemas import (
    GraphRelationType,
)
from tests.legal.mocks.mock_db import MockDatabasePool


def test_legacy_schemas_file_and_imports_absence() -> None:
    """Verify tests/legal/schemas.py is deleted and no test or src file imports from it."""
    root_dir = pathlib.Path(__file__).parent.parent.parent
    legacy_schema_file = root_dir / "tests" / "legal" / "schemas.py"
    assert not legacy_schema_file.exists(), f"Legacy {legacy_schema_file} must NOT exist!"

    # Scan all .py files in src/ and tests/ (excluding this challenger test file)
    current_file = pathlib.Path(__file__).resolve()
    offending_files: list[str] = []
    import_pattern = re.compile(r"^\s*(from|import)\s+tests\.legal\.schemas", re.MULTILINE)

    for search_dir in [root_dir / "src", root_dir / "tests"]:
        for py_file in search_dir.rglob("*.py"):
            if py_file.resolve() == current_file:
                continue
            text = py_file.read_text(encoding="utf-8")
            if import_pattern.search(text):
                offending_files.append(str(py_file.relative_to(root_dir)))

    assert len(offending_files) == 0, f"Found legacy schema imports in: {offending_files}"


@pytest.mark.asyncio
async def test_hybrid_search_vietnamese_synonyms_and_rrf_ranking() -> None:
    """Verify hybrid search ranks results via authentic lexical/token overlap and RRF without shortcuts."""
    pool = MockDatabasePool()

    # Query 1: Red light passenger car with Vietnamese colloquial phrasing
    res1 = await pool.execute_hybrid_search(
        query="vượt đèn đỏ ô tô phạt bao nhiêu tiền",
        vehicle_category="CAR",
        limit=5,
    )
    assert len(res1) > 0
    top_match = res1[0]
    # Verify top match is the red light sanction chunk
    assert "c3.p_a" in top_match["path"] or "art5" in top_match["path"]
    assert top_match["norm_role"] == "SANCTION_PRINCIPAL"
    assert top_match["min_fine_vnd"] == 800_000
    assert top_match["max_fine_vnd"] == 1_000_000
    # Verify RRF score is mathematically bounded in (0, 1) and derived from dense/sparse ranks
    assert 0.0 < top_match["rrf_score"] < 1.0
    expected_rrf = (1.0 / (60 + top_match["dense_rank"])) + (1.0 / (60 + top_match["sparse_rank"]))
    assert abs(top_match["rrf_score"] - expected_rrf) < 1e-6

    # Query 2: Motorbike one-way wrong direction violation with natural Vietnamese
    res2 = await pool.execute_hybrid_search(
        query="xe máy đi ngược chiều đường một chiều phạt bao nhiêu",
        vehicle_category="xe máy",
        limit=5,
    )
    assert len(res2) > 0
    top_bike = res2[0]
    assert "chk_nd100_art6_cl8_pta" == top_bike["chunk_id"]
    assert top_bike["min_fine_vnd"] == 1_000_000
    assert top_bike["max_fine_vnd"] == 2_000_000
    assert top_bike["rrf_score"] > 0.0

    # Query 3: Technical standard reference (non-penalty query)
    res3 = await pool.execute_hybrid_search(
        query="tốc độ tối đa cho phép trong khu vực đông dân cư",
        limit=5,
    )
    assert len(res3) > 0
    # Verify results contain TT31 or QCVN41 chunks
    doc_codes = {m["doc_code"] for m in res3}
    assert "31/2019/TT-BGTVT" in doc_codes or "100/2019/ND-CP" in doc_codes


@pytest.mark.asyncio
async def test_graph_traversal_cycle_prevention_direction_both() -> None:
    """Verify execute_graph_traversal prevents infinite loops and duplicate nodes in cyclic graphs."""
    pool = MockDatabasePool()

    # Construct an adversarial cyclic graph:
    # node_A <-> node_B <-> node_C <-> node_A (3-cycle)
    # plus self-loop on node_D and cross-link node_B <-> node_D
    synthetic_edges: list[dict[str, Any]] = [
        {
            "edge_id": "e_ab",
            "source_chunk_id": "node_A",
            "target_chunk_id": "node_B",
            "source_path": "path.A",
            "target_path": "path.B",
            "target_doc_code": "DOC_B",
            "target_chunk_index": "Điều B",
            "target_norm_role": "PRESCRIPTION_DUTY",
            "target_contextualized_text": "Text B",
            "relation_type": GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value,
            "confidence_score": 1.0,
        },
        {
            "edge_id": "e_bc",
            "source_chunk_id": "node_B",
            "target_chunk_id": "node_C",
            "source_path": "path.B",
            "target_path": "path.C",
            "target_doc_code": "DOC_C",
            "target_chunk_index": "Điều C",
            "target_norm_role": "SANCTION_PRINCIPAL",
            "target_contextualized_text": "Text C",
            "relation_type": GraphRelationType.DEFINES_SANCTION_FOR.value,
            "confidence_score": 0.9,
        },
        {
            "edge_id": "e_ca",
            "source_chunk_id": "node_C",
            "target_chunk_id": "node_A",
            "source_path": "path.C",
            "target_path": "path.A",
            "target_doc_code": "DOC_A",
            "target_chunk_index": "Điều A",
            "target_norm_role": "HYPOTHESIS_CONDITION",
            "target_contextualized_text": "Text A",
            "relation_type": GraphRelationType.MODIFIES_AND_REPLACES.value,
            "confidence_score": 0.8,
        },
        {
            "edge_id": "e_bd",
            "source_chunk_id": "node_B",
            "target_chunk_id": "node_D",
            "source_path": "path.B",
            "target_path": "path.D",
            "target_doc_code": "DOC_D",
            "target_chunk_index": "Điều D",
            "target_norm_role": "REMEDIAL_MEASURE",
            "target_contextualized_text": "Text D",
            "relation_type": GraphRelationType.OVERRIDES_PRIORITY.value,
            "confidence_score": 0.95,
        },
        {
            "edge_id": "e_dd_self",
            "source_chunk_id": "node_D",
            "target_chunk_id": "node_D",
            "source_path": "path.D",
            "target_path": "path.D",
            "target_doc_code": "DOC_D",
            "target_chunk_index": "Điều D",
            "target_norm_role": "REMEDIAL_MEASURE",
            "target_contextualized_text": "Text D Self",
            "relation_type": GraphRelationType.OVERRIDES_PRIORITY.value,
            "confidence_score": 0.5,
        },
    ]

    pool.graph_edges = synthetic_edges

    # Test 1: Start at node_A with direction="BOTH" and max_depth=5
    results_both = await pool.execute_graph_traversal(
        start_chunk_id="node_A",
        direction="BOTH",
        max_depth=5,
    )

    # In a 4-node graph (A, B, C, D) starting at A, traversal must discover B, C, D exactly once
    target_ids = [r["target_chunk_id"] for r in results_both]
    assert len(target_ids) == len(set(target_ids)), f"Cycles detected! Visited nodes not unique: {target_ids}"
    assert set(target_ids) == {"node_B", "node_C", "node_D"}
    # node_A itself should not appear in target results since it's the start node
    assert "node_A" not in target_ids

    # Test 2: Start at node_D (contains self loop) with max_depth=3
    results_d = await pool.execute_graph_traversal(
        start_chunk_id="node_D",
        direction="BOTH",
        max_depth=3,
    )
    target_ids_d = [r["target_chunk_id"] for r in results_d]
    assert len(target_ids_d) == len(set(target_ids_d)), f"Self-loop caused duplicates: {target_ids_d}"
    assert "node_D" not in target_ids_d
    assert set(target_ids_d) == {"node_B", "node_A", "node_C"}

    # Test 3: Edge type filtering
    results_filtered = await pool.execute_graph_traversal(
        start_chunk_id="node_A",
        allowed_edge_types=[GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value],
        direction="BOTH",
        max_depth=3,
    )
    assert len(results_filtered) == 1
    assert results_filtered[0]["target_chunk_id"] == "node_B"
