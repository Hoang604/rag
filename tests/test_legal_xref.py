"""Cross-reference extraction: the citation shapes real statutes actually use.

Every input below is copied from the fetched corpus rather than invented, so a
passing suite means the extractor handles the drafting conventions present in
Nghị định 168/2024, Luật 36/2024 and the 2026 amending decrees -- not a
simplified grammar.
"""

from __future__ import annotations

from rag_eval.legal.ingestion.xref import (
    RELATION_EXEMPTS,
    RELATION_MODIFIES,
    RELATION_REFERENCES,
    Address,
    address_of_path,
    build_path_index,
    extract_citations,
    extract_document_citations,
)

DOC = "168_2024_nd_cp"
PATHS = [
    f"{DOC}.c_i.a_6.c_1.p_a",
    f"{DOC}.c_i.a_6.c_2.p_a",
    f"{DOC}.c_i.a_6.c_2.p_c",
    f"{DOC}.c_i.a_6.c_5",
    f"{DOC}.c_i.a_7.c_1.p_a",
    f"{DOC}.c_ii.a_13.c_8.p_b",
]


def index() -> dict[Address, str]:
    return build_path_index(PATHS)


def test_address_of_path_reads_all_three_levels() -> None:
    assert address_of_path(f"{DOC}.c_i.a_6.c_2.p_c") == Address(
        dieu="6", khoan="2", diem="c"
    )


def test_address_of_path_ignores_chapter_c_prefix() -> None:
    """`c_` labels both Chương and Khoản; only position after `a_` disambiguates."""
    assert address_of_path(f"{DOC}.c_i.a_6") == Address(dieu="6")
    assert address_of_path(f"{DOC}.c_i.a_6").khoan is None


def test_path_index_resolves_clause_without_its_own_chunk() -> None:
    """A stem clause is not chunked, but citations to it must still land."""
    assert Address(dieu="6", khoan="2") in index()
    assert Address(dieu="6") in index()


def test_exemption_is_distinguished_from_plain_reference() -> None:
    """An exemption changes the answer, so it must not read as a bare citation."""
    citations = extract_citations(
        f"{DOC}.c_i.a_7.c_1.p_a",
        "Phạt tiền từ 400.000 đồng đến 600.000 đồng, trừ các hành vi vi phạm "
        "quy định tại điểm a, điểm c khoản 2 Điều 6 của Nghị định này",
        path_index=index(),
    )
    assert citations, "no citation extracted from an explicit exemption"
    assert {c.relation_type for c in citations} == {RELATION_EXEMPTS}
    assert {c.target_path for c in citations} == {
        f"{DOC}.c_i.a_6.c_2.p_a",
        f"{DOC}.c_i.a_6.c_2.p_c",
    }


def test_point_list_expands_to_one_edge_per_point() -> None:
    citations = extract_citations(
        f"{DOC}.c_i.a_7.c_1.p_a",
        "theo quy định tại điểm a, điểm c khoản 2 Điều 6",
        path_index=index(),
    )
    assert len(citations) == 2


def test_amendment_targets_the_amended_document() -> None:
    """An amending decree's unqualified citations point outside itself.

    Resolving them against the amending decree would attach every amendment to
    the wrong statute -- and its own Điều 13 usually does not exist.
    """
    citations = extract_citations(
        "238_2026_nd_cp.c_i.a_3",
        'Sửa đổi, bổ sung điểm b khoản 8 Điều 13 "b) Điều khiển xe không có '
        'giấy phép lái xe"',
        path_index=index(),
        default_external_doc="168/2024/ND-CP",
    )
    assert citations
    assert citations[0].relation_type == RELATION_MODIFIES
    assert citations[0].target_path is None
    assert citations[0].target_external_ref is not None
    assert "168/2024/ND-CP" in citations[0].target_external_ref
    assert "Điều 13" in citations[0].target_external_ref


def test_relative_reference_inherits_the_citing_article() -> None:
    """"khoản 5 Điều này" is only meaningful relative to where it is written."""
    citations = extract_citations(
        f"{DOC}.c_i.a_6.c_1.p_a",
        "trừ trường hợp quy định tại khoản 5 Điều này",
        path_index=index(),
    )
    assert [c.target_path for c in citations] == [f"{DOC}.c_i.a_6.c_5"]
    assert citations[0].relation_type == RELATION_EXEMPTS


def test_self_reference_is_not_emitted() -> None:
    """A chunk citing its own path would create a useless self-loop."""
    citations = extract_citations(
        f"{DOC}.c_i.a_6.c_2.p_a",
        "quy định tại điểm a khoản 2 Điều 6",
        path_index=index(),
    )
    assert citations == []


def test_external_document_is_recorded_not_dropped() -> None:
    """A citation out of the corpus is information the agent needs."""
    citations = extract_citations(
        f"{DOC}.c_i.a_6.c_1.p_a",
        "theo quy định tại khoản 2 Điều 10 của Luật Trật tự, an toàn giao thông "
        "đường bộ",
        path_index=index(),
    )
    assert citations
    assert citations[0].target_path is None
    ref = citations[0].target_external_ref
    assert ref is not None and "Luật Trật tự" in ref


def test_diem_letter_uses_the_injective_encoding() -> None:
    """Điểm đ must resolve to p_dd, never collide onto điểm d."""
    paths = [f"{DOC}.c_i.a_9.c_1.p_d", f"{DOC}.c_i.a_9.c_1.p_dd"]
    citations = extract_citations(
        f"{DOC}.c_i.a_1.c_1",
        "quy định tại điểm đ khoản 1 Điều 9",
        path_index=build_path_index(paths),
    )
    assert [c.target_path for c in citations] == [f"{DOC}.c_i.a_9.c_1.p_dd"]


def test_prose_without_a_citation_yields_nothing() -> None:
    """The bare preposition "tại" must not manufacture edges from plain text."""
    citations = extract_citations(
        f"{DOC}.c_i.a_6.c_1.p_a",
        "Không chấp hành hiệu lệnh của người điều khiển giao thông tại nơi "
        "đường giao nhau",
        path_index=index(),
    )
    assert citations == []


def test_document_level_extraction_covers_every_chunk() -> None:
    citations = extract_document_citations(
        {
            f"{DOC}.c_i.a_7.c_1.p_a": "trừ trường hợp quy định tại khoản 5 Điều 6",
            f"{DOC}.c_i.a_13.c_8.p_b": "theo quy định tại điểm a khoản 1 Điều 7",
        }
    )
    assert len(citations) == 2
    assert {c.relation_type for c in citations} == {
        RELATION_EXEMPTS,
        RELATION_REFERENCES,
    }
