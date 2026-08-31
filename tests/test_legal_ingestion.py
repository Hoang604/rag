"""Unit tests for LegalASTParser, CPHCEngine, and Ingestion Pipeline."""

from __future__ import annotations

import datetime
import uuid

from rag_eval.legal.ingestion.converter import clean_legal_text
from rag_eval.legal.ingestion.cphc import CPHCEngine, synthesize_cphc_prefix
from rag_eval.legal.ingestion.parser import LegalASTParser

SAMPLE_DECREE_TEXT = """
CHƯƠNG II
HÀNH VI VI PHẠM, HÌNH THỨC, MỨC XỬ PHẠT

Điều 5. Xử phạt người điều khiển xe ô tô
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với hành vi sau đây:
a) Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu;
b) Dừng xe, đỗ xe không có tín hiệu báo cho người điều khiển phương tiện khác biết.
2. Phạt tiền từ 400.000 đồng đến 600.000 đồng đối với hành vi:
a) Chuyển làn đường không đúng nơi cho phép hoặc không có tín hiệu báo trước;
b) Đi vào khu vực cấm, đường có biển báo hiệu có nội dung cấm đi vào.
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
    assert chap.index_label == "Chương II"
    assert len(chap.children) == 1  # 1 Article

    art = chap.children[0]
    assert art.node_type == "ARTICLE"
    assert art.index_label == "Điều 5"
    assert len(art.children) == 2  # 2 Clauses

    cl1 = art.children[0]
    assert cl1.node_type == "CLAUSE"
    assert cl1.index_label == "Khoản 1"
    assert len(cl1.children) == 2  # 2 Points: a, b

    pt_a = cl1.children[0]
    assert pt_a.node_type == "POINT"
    assert pt_a.index_label == "Điểm a"
    assert "Không chấp hành hiệu lệnh" in pt_a.raw_text


def test_synthesize_cphc_prefix() -> None:
    """Verifies CPHC context prefix synthesis format."""
    prefix = synthesize_cphc_prefix(
        doc_title="Nghị định 100/2019/NĐ-CP",
        chapter_title="Chương II - Xử phạt",
        article_label="Điều 5",
        article_title="Xử phạt xe ô tô",
        clause_label="Khoản 1",
        lead_sentence="Phạt tiền từ 200.000 đồng đến 400.000 đồng",
    )
    expected = "[Nghị định 100/2019/NĐ-CP] > [Chương II - Xử phạt] > [Điều 5: Xử phạt xe ô tô] > [Khoản 1: Phạt tiền từ 200.000 đồng đến 400.000 đồng]"
    assert prefix == expected


def test_cphc_engine_flattening() -> None:
    """Verifies CPHCEngine flattens AST into self-contained atomic leaf chunks."""
    doc_id = uuid.uuid4()
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(SAMPLE_DECREE_TEXT, doc_title="Nghị định 100/2019/NĐ-CP")

    cphc = CPHCEngine(
        document_id=doc_id,
        doc_code="100/2019/NĐ-CP",
        doc_title="Nghị định 100/2019/NĐ-CP",
        effective_date=datetime.date(2020, 1, 15),
    )
    chunks = cphc.chunk_ast(root)

    # 4 points in sample text (Clause 1: 2 points, Clause 2: 2 points)
    assert len(chunks) == 4
    for c in chunks:
        assert c.document_id == doc_id
        assert "[Nghị định 100/2019/NĐ-CP]" in c.contextualized_text
        assert "[Điều 5" in c.contextualized_text
        assert c.effective_date == datetime.date(2020, 1, 15)
