"""Chunk granularity: the two drafting styles that used to swallow statute.

A chunk longer than the embedding model's 512-token window is truncated
silently. The sparse half indexes the full text, so the tail stays reachable by
keyword -- but only for someone who already guessed a word from the part they
cannot see. These tests pin the structures whose absence produced 18,000- to
21,000-character chunks, and the last-resort window split that guarantees no
statute is ever outside the window.
"""

from __future__ import annotations

import datetime
import uuid

from rag_eval.legal.ingestion.cphc import (
    EMBEDDING_CHAR_BUDGET,
    CPHCEngine,
    split_for_embedding,
)
from rag_eval.legal.ingestion.parser import LegalASTParser


def chunks_of(text: str, doc_code: str = "QCVN41/2024/BGTVT") -> list[tuple[str, str]]:
    ast = LegalASTParser(doc_code=doc_code).parse(text, doc_code)
    engine = CPHCEngine(
        document_id=uuid.uuid4(),
        doc_code=doc_code,
        doc_title=doc_code,
        effective_date=datetime.date(2025, 1, 1),
    )
    return [(c.path, c.verbatim_text) for c in engine.chunk_ast(ast)]


APPENDIX = """Phụ lục B
Ý NGHĨA - SỬ DỤNG BIỂN BÁO CẤM
B.1 Biển số P.101 "Đường cấm"
Để báo đường cấm tất cả các loại xe đi lại cả hai hướng, đặt biển số P.101.
B.2 Biển số P.102 "Cấm đi ngược chiều"
Để báo đường cấm các loại xe đi vào theo chiều đặt biển, đặt biển số P.102.
B.3 Biển số P.103a "Cấm xe ô tô"
Để báo đường cấm các loại xe cơ giới kể cả xe máy 3 bánh, đặt biển số P.103a.
"""


def test_appendix_item_becomes_its_own_chunk() -> None:
    """One sign per chunk is the granularity "biển P.102 là gì" needs."""
    paths = [p for p, _ in chunks_of(APPENDIX)]
    assert len(paths) == 3, f"appendix did not split into items: {paths}"
    assert all(".i_" in p for p in paths)


def test_appendix_item_text_stays_with_its_item() -> None:
    """Prose after an item heading belongs to that item, not back to the appendix."""
    by_path = dict(chunks_of(APPENDIX))
    second = next(text for path, text in by_path.items() if path.endswith(".i_2"))
    assert "P.102" in second
    assert "P.101" not in second, "item 2 absorbed item 1's text"


def test_appendix_item_carries_its_appendix_in_context() -> None:
    """Phụ lục B means prohibitory; without it two signs read alike."""
    ast = LegalASTParser(doc_code="QCVN41/2024/BGTVT").parse(APPENDIX, "QCVN 41")
    engine = CPHCEngine(
        document_id=uuid.uuid4(),
        doc_code="QCVN41/2024/BGTVT",
        doc_title="QCVN 41",
        effective_date=datetime.date(2025, 1, 1),
    )
    item = engine.chunk_ast(ast)[0]
    assert "Phụ lục B" in item.contextualized_text
    assert "B.1" in item.contextualized_text


def test_citation_shaped_line_is_not_an_appendix_item() -> None:
    """A line opening "P.124 (a,b)" is a sign reference, not an item of Phụ lục P."""
    text = """Phụ lục B
BIỂN BÁO CẤM
B.1 Biển số P.101 "Đường cấm"
P.124 (a,b) “Cấm quay đầu xe” được đặt ở nơi đường giao nhau.
"""
    paths = [p for p, _ in chunks_of(text)]
    assert len(paths) == 1, f"a sign reference was promoted to an item: {paths}"


TECHNICAL_STANDARD = """Điều 3. Giải thích từ ngữ
3.1. Đường đô thị là đường trong phạm vi địa giới hành chính nội thành.
3.2. Đường qua khu đông dân cư là đoạn đường bộ nằm trong khu đông dân cư.
3.3. Đường dành riêng cho một số loại phương tiện là tuyến đường có biển báo.
"""


def test_technical_standard_clause_style_is_recognised() -> None:
    """"3.1." inside Điều 3 is khoản 1, not body text absorbed by the article."""
    paths = [p for p, _ in chunks_of(TECHNICAL_STANDARD)]
    assert len(paths) == 3, f"N.M clauses were not split: {paths}"
    assert {p.rsplit(".", 1)[-1] for p in paths} == {"c_1", "c_2", "c_3"}


def test_mismatched_clause_prefix_is_not_a_clause() -> None:
    """"83.1." inside Điều 3 cites another article; only a match is a clause."""
    text = """Điều 3. Giải thích từ ngữ
3.1. Đường đô thị là đường trong nội thành.
83.1. Báo hiệu đường bộ phải được thay thế ngay theo quy định.
"""
    chunks = chunks_of(text)
    assert len(chunks) == 1, f"a foreign clause number was accepted: {chunks}"
    assert "83.1." in chunks[0][1], "the cited line was dropped instead of kept as text"


CONSOLIDATED = """Điều 125. Tạm giữ tang vật
7. Cá nhân, tổ chức vi phạm hành chính thuộc trường hợp bị áp dụng hình thức
xử phạt tước quyền sử dụng giấy phép thì có thể bị tạm giữ giấy phép.
8.240 Thời hạn tạm giữ tang vật, phương tiện vi phạm hành chính là 07 ngày.
"""


def test_footnote_marked_clause_is_not_absorbed() -> None:
    """A consolidated law glues its footnote id to the clause number.

    Unrecognised, "8.240 Thời hạn..." appended khoản 8 to khoản 7's text, so a
    real provision had no chunk of its own to retrieve or cite.
    """
    by_path = dict(chunks_of(CONSOLIDATED, doc_code="90/VBHN-VPQH"))
    tails = {p.rsplit(".", 1)[-1] for p in by_path}
    assert "c_8" in tails, f"footnote-marked khoản 8 was absorbed: {sorted(tails)}"
    seven = next(t for p, t in by_path.items() if p.endswith(".c_7"))
    assert "07 ngày" not in seven, "khoản 8 text leaked into khoản 7"


def test_split_for_embedding_keeps_every_character() -> None:
    body = " ".join(f"Câu số {i} nói về một quy định cụ thể." for i in range(200))
    parts = split_for_embedding(body, 300)
    assert len(parts) > 1
    assert "".join(parts.copy()).replace(" ", "") == body.replace(" ", "")


def test_split_for_embedding_never_breaks_a_figure() -> None:
    """A monetary amount cut across parts would read as a different number."""
    body = ". ".join(
        f"Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng đối với hành vi thứ {i}"
        for i in range(40)
    )
    parts = split_for_embedding(body, 200)
    assert len(parts) > 1
    # Every occurrence must survive whole. A figure severed across two parts
    # would leave one part stating "18.000" -- a real amount, and the wrong one.
    for figure in ("18.000.000", "20.000.000"):
        assert sum(part.count(figure) for part in parts) == body.count(figure)


def test_split_for_embedding_leaves_short_text_alone() -> None:
    assert split_for_embedding("Ngắn gọn.", 500) == ["Ngắn gọn."]


def test_oversize_provision_is_windowed_under_its_own_path() -> None:
    """Each window keeps the provision's address, so citations still resolve."""
    long_clause = " ".join(
        f"Nội dung quy định chi tiết thứ {i} của khoản này được áp dụng."
        for i in range(120)
    )
    text = f"Điều 9. Quy định dài\n1. {long_clause}\n"
    paths = [p for p, _ in chunks_of(text, doc_code="TEST/2026/ND-CP")]
    assert len(paths) > 1, "an oversize clause was left as one chunk"
    assert all(".c_1.w_" in p for p in paths)


def test_every_chunk_fits_the_embedding_budget() -> None:
    text = f"Điều 9. Quy định dài\n1. {'rất dài ' * 900}\n"
    ast = LegalASTParser(doc_code="TEST/2026/ND-CP").parse(text, "Thử")
    engine = CPHCEngine(
        document_id=uuid.uuid4(),
        doc_code="TEST/2026/ND-CP",
        doc_title="Thử",
        effective_date=datetime.date(2026, 1, 1),
    )
    for chunk in engine.chunk_ast(ast):
        assert len("passage: " + chunk.contextualized_text) <= EMBEDDING_CHAR_BUDGET
