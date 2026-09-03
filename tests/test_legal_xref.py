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
    match_document,
    normalize_doc_code,
    normalize_title,
    parse_external_ref,
    resolve_across_documents,
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


# --- Cross-document resolution -------------------------------------------------
#
# Extraction runs per document, so a citation out of the document can only be
# recorded as text at that point. These pin the pass that turns those into real
# edges, which is the whole content of an amending decree.

TARGET_PATHS = [
    "168_2024_nd_cp.c_ii.a_13.c_8.p_b",
    "168_2024_nd_cp.c_ii.a_14.c_3.p_b",
]


def target_index() -> dict[Address, str]:
    return build_path_index(TARGET_PATHS)


def test_doc_code_matches_every_shape_in_the_corpus() -> None:
    """Statute codes end in digits; an earlier pattern required letters only.

    That excluded 35/2024/QH15 and 36/2024/QH15 -- the two laws this corpus is
    built around -- so no citation to either could ever link.
    """
    for code in (
        "168/2024/NĐ-CP",
        "36/2024/QH15",
        "88/2025/QH15",
        "12/2025/TT-BCA",
        "QCVN41/2024/BGTVT",
        "90/VBHN-VPQH",
    ):
        assert match_document(f"Điều 1 — {code}", {normalize_doc_code(code): "X"}) == "X"


def test_dates_and_ratios_are_not_document_codes() -> None:
    known = {normalize_doc_code("168/2024/NĐ-CP"): "X"}
    for text in ("ngày 15/11/2024", "tỷ lệ L1/L2=1:2", "khoản 2/3"):
        assert match_document(f"Điều 1 — {text}", known) is None


def test_doc_code_matching_ignores_d_spelling() -> None:
    """One decree is written NĐ-CP in a statute and ND-CP in the registry."""
    known = {normalize_doc_code("168/2024/ND-CP"): "168/2024/ND-CP"}
    assert match_document("Điều 13 — 168/2024/NĐ-CP", known) == "168/2024/ND-CP"


def test_amendment_edge_lands_on_the_provision_it_replaces() -> None:
    hit = resolve_across_documents(
        "điểm b khoản 8 Điều 13 — 168/2024/ND-CP",
        {normalize_doc_code("168/2024/ND-CP"): "168/2024/ND-CP"},
        {"168/2024/ND-CP": target_index()},
    )
    assert hit == ("168/2024/ND-CP", "168_2024_nd_cp.c_ii.a_13.c_8.p_b")


def test_address_absent_from_the_target_stays_unresolved() -> None:
    """An amendment that *adds* a point cites one that does not exist yet."""
    assert (
        resolve_across_documents(
            "điểm e khoản 8 Điều 13 — 168/2024/ND-CP",
            {normalize_doc_code("168/2024/ND-CP"): "168/2024/ND-CP"},
            {"168/2024/ND-CP": target_index()},
        )
        is None
    )


def test_title_match_requires_a_unique_prefix() -> None:
    titles = {
        normalize_title("Luật Đường bộ (văn bản hợp nhất)"): "49/VBHN-VPQH",
        normalize_title(
            "Luật Trật tự, an toàn giao thông đường bộ (văn bản hợp nhất)"
        ): "55/VBHN-VPQH",
    }
    assert (
        match_document("Điều 64 — Luật Trật tự, an toàn giao thông đường bộ", {}, titles)
        == "55/VBHN-VPQH"
    )
    assert match_document("Điều 10 — Luật Đường bộ", {}, titles) == "49/VBHN-VPQH"


def test_repealed_2008_law_is_not_matched_onto_its_successor() -> None:
    """"Luật Giao thông đường bộ" is the repealed 2008 law, still cited by
    100/2019/NĐ-CP. Matching it onto Luật Đường bộ would answer a question
    about the old law with the text of the new one."""
    titles = {normalize_title("Luật Đường bộ (văn bản hợp nhất)"): "49/VBHN-VPQH"}
    assert match_document("Điều 8 — Luật Giao thông đường bộ", {}, titles) is None


def test_short_or_ambiguous_title_is_refused() -> None:
    titles = {
        normalize_title("Luật Đường bộ"): "A",
        normalize_title("Luật Đường sắt"): "B",
    }
    assert match_document("Điều 1 — Luật", {}, titles) is None
    assert match_document("Điều 1 — Luật Đường", {}, titles) is None


def test_parse_external_ref_round_trips_an_address() -> None:
    assert parse_external_ref("điểm b khoản 8 Điều 13 — 168/2024/ND-CP") == Address(
        dieu="13", khoan="8", diem="b"
    )


def test_truncated_footnote_reference_is_refused_not_guessed() -> None:
    """A consolidated law's footnotes are cut mid-sentence by the gazette.

    Once windowing turns those newlines into spaces, a naive capture produced
    "Luật số 13 Điểm này được bãi bỏ theo quy định tại khoản 10 Điều 54 của".
    """
    citations = extract_citations(
        f"{DOC}.c_i.a_1.c_1",
        "theo quy định tại khoản 2 Điều 1 của Luật số 13 Điểm này được bãi bỏ "
        "theo quy định tại khoản 10 Điều 54 của",
        path_index=index(),
    )
    for citation in citations:
        ref = citation.target_external_ref or ""
        assert "Điểm này" not in ref, f"footnote text leaked into a name: {ref!r}"
        assert ref.strip() not in ("Luật số", "Luật")


def test_document_title_with_a_comma_survives() -> None:
    """"Luật Phòng, chống ma túy" was truncated at its own comma."""
    citations = extract_citations(
        f"{DOC}.c_i.a_1.c_1",
        "theo quy định tại khoản 8 Điều 54 của Luật Phòng, chống ma túy số "
        "120/2025/QH15",
        path_index=index(),
    )
    assert citations
    ref = citations[0].target_external_ref or ""
    assert "120/2025/QH15" in ref
