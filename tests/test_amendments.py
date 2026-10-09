from __future__ import annotations

import datetime

from rag_eval.legal.retrieval.amendments import AmendmentIndex, target_articles
from rag_eval.legal.schemas.retrieval import SearchHit

ROWS = [
    {
        "target_doc": "168/2024/ND-CP",
        "doc_code": "238/2026/ND-CP",
        "effective_date": datetime.date(2026, 8, 15),
        "path": "238_2026_nd_cp.c_i.a_2.c_1",
        "label": "Điều 2",
        "title": "Sửa đổi, bổ sung một số điểm, khoản của Điều 6",
    },
    {
        "target_doc": "151/2024/ND-CP",
        "doc_code": "236/2026/ND-CP",
        "effective_date": datetime.date(2026, 8, 15),
        "path": "236_2026_nd_cp.c_i.a_12.c_1",
        "label": "Điều 12",
        "title": "Bổ sung Điều 25a vào sau Điều 25",
    },
    {
        "target_doc": "168/2024/ND-CP",
        "doc_code": "238/2026/ND-CP",
        "effective_date": datetime.date(2026, 8, 15),
        "path": "238_2026_nd_cp.c_i.a_19",
        "label": "Điều 19",
        "title": "Bổ sung, bãi bỏ, thay thế một số cụm từ",
    },
]


def hit(doc_code: str, path: str) -> SearchHit:
    return SearchHit(
        doc_code=doc_code,
        doc_title="",
        path=path,
        start_line=1,
        end_line=1,
        verbatim_text="",
        contextualized_text="",
        effective_date=datetime.date(2025, 1, 1),
    )


def test_target_articles_reads_every_article_named_in_the_title() -> None:
    assert target_articles("Sửa đổi, bổ sung điểm b khoản 8 Điều 13") == ["13"]
    assert target_articles("Bổ sung Điều 25a vào sau Điều 25") == ["25a", "25"]
    assert target_articles("Bổ sung, bãi bỏ, thay thế một số cụm từ") == []


def test_hit_in_an_amended_article_gets_a_note_once_the_amendment_is_in_force() -> None:
    index = AmendmentIndex.from_rows(ROWS)
    original = hit("168/2024/ND-CP", "168_2024_nd_cp.c_ii.s_1.a_6.c_3.p_m")

    before = index.annotate([original], datetime.date(2026, 8, 14))
    after = index.annotate([original], datetime.date(2026, 8, 15))

    assert before[0].amended_by == []
    assert [note.label for note in after[0].amended_by] == ["Điều 2"]
    assert after[0].amended_by[0].doc_code == "238/2026/ND-CP"


def test_hit_in_another_document_or_article_is_untouched() -> None:
    index = AmendmentIndex.from_rows(ROWS)
    other_article = hit("168/2024/ND-CP", "168_2024_nd_cp.c_ii.s_1.a_7.c_2.p_h")
    other_document = hit("100/2019/ND-CP", "100_2019_nd_cp.c_ii.a_6.c_3")

    annotated = index.annotate([other_article, other_document], datetime.date(2026, 10, 1))

    assert [h.amended_by for h in annotated] == [[], []]


def test_amendment_naming_a_clause_leaves_other_clauses_of_the_article_alone() -> None:
    rows = [
        {
            "target_doc": "168/2024/ND-CP",
            "doc_code": "238/2026/ND-CP",
            "effective_date": datetime.date(2026, 8, 15),
            "path": "238_2026_nd_cp.c_i.a_4",
            "label": "Điều 4",
            "title": "Sửa đổi, bổ sung điểm b khoản 3 Điều 14",
        }
    ]
    index = AmendmentIndex.from_rows(rows)
    on_date = datetime.date(2026, 10, 1)

    same_clause = hit("168/2024/ND-CP", "168_2024_nd_cp.c_ii.s_2.a_14.c_3.p_b")
    other_clause = hit("168/2024/ND-CP", "168_2024_nd_cp.c_ii.s_2.a_14.c_1.p_a")
    whole_article = hit("168/2024/ND-CP", "168_2024_nd_cp.c_ii.s_2.a_14")

    annotated = index.annotate([same_clause, other_clause, whole_article], on_date)

    assert [len(h.amended_by) for h in annotated] == [1, 0, 1]


def test_inserted_article_is_attributed_to_both_numbers() -> None:
    index = AmendmentIndex.from_rows(ROWS)
    inserted = hit("151/2024/ND-CP", "151_2024_nd_cp.c_iv.a_25a.c_1")

    annotated = index.annotate([inserted], datetime.date(2026, 10, 1))

    assert [note.label for note in annotated[0].amended_by] == ["Điều 12"]
