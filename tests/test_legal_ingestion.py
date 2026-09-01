"""Unit tests for AST Parser, LegalLexer, PDF Layout Extractor, and Staging Manager."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path

import pytest

from rag_eval.legal.ingestion.converter import clean_legal_text, load_legal_document
from rag_eval.legal.ingestion.cphc import CPHCEngine, synthesize_cphc_prefix
from rag_eval.legal.ingestion.layout import PDFLayoutExtractor
from rag_eval.legal.ingestion.lexer import LegalLexer
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


def test_lexer_multiline_title_stitching() -> None:
    """Verifies LegalLexer stitches multi-line Chapter and Article titles with lookahead."""
    sample_multiline = """
CHƯƠNG II
HÀNH VI VI PHẠM, HÌNH THỨC XỬ PHẠT
VÀ BIỆN PHÁP KHẮC PHỤC HẬU QUẢ

MỤC 1
VI PHẠM QUY TẮC GIAO THÔNG
ĐƯỜNG BỘ

Điều 5. Xử phạt người điều khiển xe ô tô
và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông
1. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng:
a) Chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;
"""
    lexer = LegalLexer(doc_code="100/2019/NĐ-CP")
    tokens = lexer.tokenize(sample_multiline)

    chap_token = next(t for t in tokens if t.token_type == "CHAPTER")
    assert chap_token.title == "HÀNH VI VI PHẠM, HÌNH THỨC XỬ PHẠT VÀ BIỆN PHÁP KHẮC PHỤC HẬU QUẢ"

    sec_token = next(t for t in tokens if t.token_type == "SECTION")
    assert sec_token.title == "VI PHẠM QUY TẮC GIAO THÔNG ĐƯỜNG BỘ"

    art_token = next(t for t in tokens if t.token_type == "ARTICLE")
    assert art_token.title == "Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông"


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
    assert cl1.clause_kind == "CONTAINER_STEM"
    assert len(cl1.children) == 2  # Point a and Point b


def test_ast_parser_sections_and_appendices() -> None:
    """Verifies LegalASTParser builds tree with Sections (Mục) and Appendices (Phụ lục)."""
    text_with_sec_and_app = """
CHƯƠNG II
QUY TẮC GIAO THÔNG

MỤC 1
QUY ĐỊNH CHUNG

Điều 5. Tốc độ xe
1. Người lái xe phải tuân thủ tốc độ:
a) Không vượt quá tốc độ tối đa;

PHỤ LỤC I
BIỂN BÁO HIỆU ĐƯỜNG BỘ
Nội dung phụ lục biển báo hiệu đường bộ.
"""
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(text_with_sec_and_app, doc_title="Nghị định 100")

    assert len(root.children) == 2  # 1 Chapter + 1 Appendix
    chap = root.children[0]
    assert chap.node_type == "CHAPTER"
    assert len(chap.children) == 1  # 1 Section
    sec = chap.children[0]
    assert sec.node_type == "SECTION"
    assert "s_1" in sec.full_path
    assert len(sec.children) == 1  # 1 Article
    art = sec.children[0]
    assert art.node_type == "ARTICLE"

    app = root.children[1]
    assert app.node_type == "APPENDIX"
    assert "app_i" in app.full_path
    assert app.title == "BIỂN BÁO HIỆU ĐƯỜNG BỘ"


def test_ast_parser_lead_sentence_vs_title() -> None:
    """Verifies Article without sub-clauses preserves regulatory body in raw_text without polluting title."""
    text_no_clause = """
Điều 1. Phạm vi điều chỉnh
Nghị định này quy định về hành vi vi phạm hành chính, hình thức, mức xử phạt trong lĩnh vực giao thông.
"""
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(text_no_clause, doc_title="Nghị định 100")

    assert len(root.children) == 1
    art = root.children[0]
    assert art.node_type == "ARTICLE"
    assert art.title == "Phạm vi điều chỉnh"
    assert "Nghị định này quy định về hành vi vi phạm" in art.raw_text


def test_ast_parser_timestamp_lead_sentence_preservation() -> None:
    """Verifies that clauses with time ranges preserve complete timestamp without truncation."""
    text_timestamp = """
Điều 5. Xử phạt ô tô
5. Phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng khi lưu thông trong khung giờ từ 22:00 ngày hôm trước đến 05:00 ngày hôm sau đối với các hành vi sau:
a) Đi vào đường cấm;
"""
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(text_timestamp, doc_title="Nghị định 100")

    art = root.children[0]
    cl5 = art.children[0]
    assert cl5.clause_kind == "CONTAINER_STEM"
    assert "22:00" in cl5.lead_sentence
    assert "05:00" in cl5.lead_sentence
    assert cl5.lead_sentence.endswith("đối với các hành vi sau")

    pt_a = cl5.children[0]
    assert "22:00" in pt_a.lead_sentence
    assert "05:00" in pt_a.lead_sentence


def test_ast_parser_citation_lead_sentence_preservation() -> None:
    """Verifies that clauses with internal citation colons preserve text after citation."""
    text_citation = """
Điều 6. Xử phạt mô tô
1. Căn cứ theo quy định tại Điều 12: Xử phạt hành vi vi phạm nồng độ cồn, người điều khiển phải chịu mức phạt từ 400.000 đồng đến 600.000 đồng đối với:
a) Có nồng độ cồn chưa vượt quá 50 mg/100 ml máu;
"""
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(text_citation, doc_title="Nghị định 100")

    art = root.children[0]
    cl1 = art.children[0]
    assert "Điều 12: Xử phạt hành vi" in cl1.lead_sentence
    assert "400.000 đồng đến 600.000 đồng" in cl1.lead_sentence


def test_ast_parser_clause_kind_classification() -> None:
    """Verifies clause kind is CONTAINER_STEM for clauses with points and STANDALONE_RULE for standalone."""
    text_mixed = """
Điều 7. Quy tắc chung
1. Người tham gia giao thông phải chấp hành hiệu lệnh của người điều khiển giao thông.
2. Phạt tiền từ 100.000 đồng đến 200.000 đồng đối với hành vi sau:
a) Bấm còi liên tục trong khu đô thị;
"""
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(text_mixed, doc_title="Nghị định 100")

    art = root.children[0]
    cl1 = art.children[0]
    assert cl1.clause_kind == "STANDALONE_RULE"
    assert len(cl1.children) == 0

    cl2 = art.children[1]
    assert cl2.clause_kind == "CONTAINER_STEM"
    assert len(cl2.children) == 1


def test_ast_parser_clause_with_multiple_internal_colons() -> None:
    """Verifies ratios 1:1 and time ranges 08:30 coexist without corruption."""
    text_complex = """
Điều 8. Tỷ lệ và thời gian
1. Áp dụng tỷ lệ 1:1 trong khung giờ từ 08:30 đến 17:30 đối với quy định sau:
a) Chạy đúng làn đường;
"""
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(text_complex, doc_title="Nghị định 100")

    art = root.children[0]
    cl1 = art.children[0]
    assert "1:1" in cl1.lead_sentence
    assert "08:30" in cl1.lead_sentence
    assert "17:30" in cl1.lead_sentence


def test_cphc_syntactic_prose_fusion() -> None:
    """Verifies CPHCEngine flattens leaf AST nodes into contextualized chunks with complete stem."""
    text_prose = """
Điều 5. Xử phạt người điều khiển xe ô tô
3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện hành vi sau:
a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;
"""
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(text_prose, doc_title="Nghị định 100/2019/NĐ-CP")

    cphc = CPHCEngine(
        document_id=uuid.uuid4(),
        doc_code="100/2019/NĐ-CP",
        doc_title="Nghị định 100/2019/NĐ-CP",
        effective_date=datetime.date(2020, 1, 15),
    )
    chunks = cphc.chunk_ast(root)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert "[Nghị định 100/2019/NĐ-CP] > [Điều 5: Xử phạt người điều khiển xe ô tô] > [Khoản 3: Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện hành vi sau]" in chunk.contextualized_text
    assert "Điểm a) Điều khiển xe chạy quá tốc độ" in chunk.contextualized_text
    assert chunk.verbatim_text == "Điểm a) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;"


def test_cphc_long_clause_without_points_zero_bloat() -> None:
    """Verifies standalone long clause produces single chunk without lead_sentence duplication."""
    long_text = """
Điều 1. Phạm vi
1. Luật này áp dụng đối với tất cả cơ quan, tổ chức và cá nhân tham gia giao thông trên toàn lãnh thổ Việt Nam.
"""
    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(long_text, doc_title="Nghị định 100/2019/NĐ-CP")

    cphc = CPHCEngine(
        document_id=uuid.uuid4(),
        doc_code="100/2019/NĐ-CP",
        doc_title="Nghị định 100/2019/NĐ-CP",
        effective_date=datetime.date(2020, 1, 15),
    )
    chunks = cphc.chunk_ast(root)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.metadata["node_type"] == "CLAUSE"
    assert chunk.metadata["clause_kind"] == "STANDALONE_RULE"
    assert "[Khoản 1]" in chunk.contextualized_text
    assert "Khoản 1. Luật này áp dụng" in chunk.verbatim_text


def test_layout_table_pipe_escaping() -> None:
    """Verifies PDFLayoutExtractor escapes pipes and flattens multi-line cells in Markdown tables."""
    extractor = PDFLayoutExtractor()
    raw_data = [
        ["Hành vi | Vi phạm", "Mức phạt\n(VNĐ)", "Ghi chú"],
        ["Vượt tốc độ | quá 10km/h", "800.000 -\n1.000.000", "Phạt tiền"],
    ]
    md = extractor._format_markdown_table(raw_data)
    assert "\\|" in md  # Pipe escaped
    assert "\n" not in md.splitlines()[0][1:-1]  # Header is single line
    assert "800.000 - 1.000.000" in md


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


def test_staging_atomic_write_crash_resilience(tmp_path: Path) -> None:
    """Verifies atomic write replaces destination session file cleanly."""
    mgr = StagingManager(staging_dir=tmp_path)
    session = mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )
    session_file = tmp_path / "100_2019_nd_cp.json"
    assert session_file.exists()

    # Re-save session atomically
    session.title = "Nghị định 100 (Updated Title)"
    saved_path = mgr.save_session(session)
    assert saved_path == session_file

    reloaded = mgr.load_session("100/2019/NĐ-CP")
    assert reloaded.title == "Nghị định 100 (Updated Title)"


def test_stg_patch_chunks(tmp_path: Path) -> None:
    """Verifies surgical chunk patching without modifying untouched chunks."""
    mgr = StagingManager(staging_dir=tmp_path)
    mgr.create_session_from_raw(
        doc_code="100/2019/NĐ-CP",
        title="Nghị định 100",
        raw_text=SAMPLE_DECREE_TEXT,
        effective_date=datetime.date(2020, 1, 15),
    )

    target_path = "100_2019_nd_cp.c_ii.a_5.c_3.p_a"
    updated_chunk = StagingChunk(
        path=target_path,
        verbatim_text="Điểm a) Sửa đổi: Phạt từ 1.000.000 đến 2.000.000",
        contextualized_text="[Nghị định 100] > [Điều 5]\nĐiểm a) Sửa đổi",
        metadata={"fines": {"min_vnd": 1000000, "max_vnd": 2000000}},
        effective_date=datetime.date(2020, 1, 15),
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
        source_path="100_2019_nd_cp.c_ii.a_5.c_3.p_a",
        target_path="100_2019_nd_cp.c_ii.a_5.c_11",
        relation_type="HAS_ADDITIONAL_SANCTION",
        citation_text="Tước GPLX",
    )
    edge2 = StagingEdge(
        source_path="100_2019_nd_cp.c_ii.a_5.c_3.p_a",
        target_path="100_2019_nd_cp.c_ii.a_5.c_11",
        relation_type="HAS_ADDITIONAL_SANCTION",
        citation_text="Tước GPLX (Updated)",
    )

    session = mgr.add_edges("100/2019/NĐ-CP", [edge1, edge2])
    assert len(session.edges) == 1
    assert session.edges[0].citation_text == "Tước GPLX (Updated)"


def test_unicode_nfd_normalization_in_ast_parsing() -> None:
    """Verifies decomposed NFD Unicode input is normalized to NFC and correctly parsed by AST parser."""
    import unicodedata

    nfd_text = unicodedata.normalize("NFD", SAMPLE_DECREE_TEXT)
    assert unicodedata.is_normalized("NFD", nfd_text)

    cleaned = clean_legal_text(nfd_text)
    assert unicodedata.is_normalized("NFC", cleaned)

    parser = LegalASTParser(doc_code="100/2019/NĐ-CP")
    root = parser.parse(cleaned, doc_title="Nghị định 100")
    assert len(root.children) == 1
    assert root.children[0].node_type == "CHAPTER"
    assert len(root.children[0].children) == 1
    assert root.children[0].children[0].node_type == "ARTICLE"


def test_load_legal_document(tmp_path: Path) -> None:
    """Verifies load_legal_document reads text files with proper normalization."""
    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("Điều 1.   Phạm vi điều chỉnh \r\n\n  Nội dung văn bản", encoding="utf-8")
    loaded = load_legal_document(sample_file)
    assert loaded == "Điều 1. Phạm vi điều chỉnh\n\nNội dung văn bản"
