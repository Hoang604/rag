"""Unit tests for AST Parser, CPHC chunking engine, and Two-Phase Staging Manager."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path

import pytest

from rag_eval.legal.ingestion.converter import clean_legal_text
from rag_eval.legal.ingestion.cphc import CPHCEngine, synthesize_cphc_prefix
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.ingestion.staging import (
    StagingChunk,
    StagingEdge,
    StagingManager,
)
from rag_eval.legal.schemas import LegalDomainError

SAMPLE_DECREE_TEXT = """
CHƯƠNG II
HÀNH VI VI PHẠM, HÌNH THỨC, MỨC XỬ PHẠT

Điều 5. Xử phạt người điều khiển xe ô tô
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với một trong các hành vi sau đây:
a) Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu;
b) Dừng xe, đỗ xe không có tín hiệu báo trước.
3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện hành vi sau:
a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;
"""


def test_clean_legal_text() -> None:
    """Verifies clean_legal_text eliminates excessive whitespace."""
    raw = "  Điều 1.   Phạm vi điều chỉnh \r\n\r\n\n  Nghị định này quy định...  "
    clean = clean_legal_text(raw)
    assert clean == "Điều 1. Phạm vi điều chỉnh\n\nNghị định này quy định..."


def test_ast_parser_hierarchy() -> None:
    """Verifies LegalASTParser builds a correct syntax tree with nested divisions."""
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(SAMPLE_DECREE_TEXT, doc_title="Nghị định 100")

    assert root.node_type == "DOCUMENT"
    assert len(root.children) == 1  # 1 Chapter

    chap = root.children[0]
    assert chap.node_type == "CHAPTER"
    assert "c_ii" in chap.full_path
    assert len(chap.children) == 1  # 1 Article

    art = chap.children[0]
    assert art.node_type == "ARTICLE"
    assert "a_5" in art.full_path
    assert len(art.children) == 2  # Clause 1 and Clause 3

    cl1 = art.children[0]
    assert cl1.node_type == "CLAUSE"
    assert len(cl1.children) == 2  # Point a and Point b


def test_synthesize_cphc_prefix() -> None:
    """Verifies context lineage prefix synthesis."""
    prefix = synthesize_cphc_prefix(
        doc_title="Nghị định 100",
        chapter_title="Chương II: Xử phạt",
        article_title="Điều 5: Ô tô",
        clause_label="Khoản 3",
        lead_sentence="Phạt tiền từ 800.000 đồng...",
    )
    assert prefix == "[Nghị định 100] > [Chương II: Xử phạt] > [Điều 5: Ô tô] > [Khoản 3: Phạt tiền từ 800.000 đồng...]"


def test_cphc_engine_flattening() -> None:
    """Verifies CPHCEngine flattens leaf AST nodes into contextualized chunks."""
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(SAMPLE_DECREE_TEXT, doc_title="Nghị định 100/2019/NĐ-CP")

    cphc = CPHCEngine(
        document_id=uuid.uuid4(),
        doc_code="100/2019/NĐ-CP",
        doc_title="Nghị định 100/2019/NĐ-CP",
        effective_date=datetime.date(2020, 1, 15),
    )
    chunks = cphc.chunk_ast(root)

    # 2 points from Clause 1, 1 point from Clause 3 = 3 leaf chunks
    assert len(chunks) == 3
    for chunk in chunks:
        assert chunk.document_id == cphc.document_id
        assert "[Nghị định 100/2019/NĐ-CP]" in chunk.contextualized_text
        assert "c_ii" in chunk.path


# ------------------------------------------------------------------------------
# StagingManager Unit Tests
# ------------------------------------------------------------------------------
def test_stg_create_and_load(tmp_path: Path) -> None:
    """Verifies StagingManager creates and reloads session from disk."""
    mgr = StagingManager(staging_dir=tmp_path)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )
    assert len(session.chunks) == 3
    assert session.doc_code == "100/2019/NĐ-CP"

    # Reload from disk
    loaded = mgr.load_session("100/2019/NĐ-CP")
    assert len(loaded.chunks) == 3
    assert loaded.title == "Nghị định 100"


def test_stg_patch_chunks(tmp_path: Path) -> None:
    """Verifies surgical chunk patching without modifying untouched chunks."""
    mgr = StagingManager(staging_dir=tmp_path)
    mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    target_path = "100_2019_n_cp.c_ii.a_5.c_3.p_a"
    updated_chunk = StagingChunk(
        path=target_path,
        verbatim_text="Điểm a) Sửa đổi: Phạt từ 1.000.000 đến 2.000.000",
        contextualized_text="[Nghị định 100] > [Điều 5]\nĐiểm a) Sửa đổi",
        metadata={"fines": {"min_vnd": 1000000, "max_vnd": 2000000}},
        effective_date="2020-01-15",
    )

    session = mgr.patch_chunks(
        doc_code="100/2019/NĐ-CP",
        updated_chunks=[updated_chunk],
    )
    assert len(session.chunks) == 3
    patched = next(c for c in session.chunks if c.path == target_path)
    assert patched.metadata["fines"]["min_vnd"] == 1000000


def test_stg_corrupted_json(tmp_path: Path) -> None:
    """Verifies corrupted JSON raises LegalDomainError."""
    mgr = StagingManager(staging_dir=tmp_path)
    file_p = tmp_path / "corrupted_doc.json"
    file_p.write_text("{ corrupted invalid json ...", encoding="utf-8")

    with pytest.raises(LegalDomainError, match="is corrupted"):
        mgr.load_session("corrupted_doc")


def test_stg_dedup_edges(tmp_path: Path) -> None:
    """Verifies adding duplicate edges is idempotently deduplicated."""
    mgr = StagingManager(staging_dir=tmp_path)
    mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    edge1 = StagingEdge(
        source_path="100_2019_n_cp.c_ii.a_5.c_3.p_a",
        target_path="100_2019_n_cp.c_ii.a_5.c_11",
        relation_type="HAS_ADDITIONAL_SANCTION",
        citation_text="Tước GPLX",
    )
    edge2 = StagingEdge(
        source_path="100_2019_n_cp.c_ii.a_5.c_3.p_a",
        target_path="100_2019_n_cp.c_ii.a_5.c_11",
        relation_type="HAS_ADDITIONAL_SANCTION",
        citation_text="Tước GPLX (Updated)",
    )

    session = mgr.add_edges("100/2019/NĐ-CP", [edge1, edge2])
    assert len(session.edges) == 1
    assert session.edges[0].citation_text == "Tước GPLX (Updated)"


def test_stg_delete_non_existent(tmp_path: Path) -> None:
    """Verifies deleting non-existent session safely returns False."""
    mgr = StagingManager(staging_dir=tmp_path)
    assert mgr.delete_session("non_existent_doc") is False
