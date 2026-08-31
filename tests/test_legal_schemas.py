"""Unit tests for Vietnamese Traffic Law domain taxonomy and Pydantic v2 schemas."""

import json

import pytest
from pydantic import ValidationError

from rag_eval.legal.schemas import (
    LTREE_PATH_PATTERN,
    AdditionalSanctions,
    CacheValidationStatus,
    CanonicalFullyQualifiedChunk,
    DemeritPointDeduction,
    ExceptionMetadata,
    FineBounds,
    GraphRelationType,
    LegalNormExtraction,
    NormRole,
    ReferencedEntity,
    remove_vietnamese_diacritics,
)


def test_remove_vietnamese_diacritics() -> None:
    """Verifies Unicode NFKD normalization and conversion of Vietnamese diacritics."""
    assert remove_vietnamese_diacritics("xe ô tô") == "XE_O_TO"
    assert remove_vietnamese_diacritics("xe máy") == "XE_MAY"
    assert remove_vietnamese_diacritics("xe tải") == "XE_TAI"
    assert remove_vietnamese_diacritics("xe buýt") == "XE_BUYT"
    assert remove_vietnamese_diacritics("mô tô") == "MO_TO"
    assert remove_vietnamese_diacritics("xe gắn máy") == "XE_GAN_MAY"
    assert remove_vietnamese_diacritics("xe đạp") == "XE_DAP"
    assert remove_vietnamese_diacritics("xe đầu kéo") == "XE_DAU_KEO"
    assert remove_vietnamese_diacritics("xe chuyên dùng") == "XE_CHUYEN_DUNG"
    assert remove_vietnamese_diacritics("Đường Cao Tốc") == "DUONG_CAO_TOC"
    assert remove_vietnamese_diacritics("xe   ô-tô   con") == "XE_O_TO_CON"
    assert remove_vietnamese_diacritics("  xe   máy  ") == "XE_MAY"


def test_norm_roles_enumeration() -> None:
    """Verifies 8 canonical norm roles under formal jurisprudential triad."""
    roles = list(NormRole)
    assert len(roles) == 8
    assert NormRole.HYPOTHESIS_CONDITION == "HYPOTHESIS_CONDITION"
    assert NormRole.PRESCRIPTION_DUTY == "PRESCRIPTION_DUTY"
    assert NormRole.PRESCRIPTION_PROHIBITION == "PRESCRIPTION_PROHIBITION"
    assert NormRole.PRESCRIPTION_PERMISSION == "PRESCRIPTION_PERMISSION"
    assert NormRole.SANCTION_PRINCIPAL == "SANCTION_PRINCIPAL"
    assert NormRole.SANCTION_SUPPLEMENTARY == "SANCTION_SUPPLEMENTARY"
    assert NormRole.SANCTION_POINT_DEDUCTION == "SANCTION_POINT_DEDUCTION"
    assert NormRole.REMEDIAL_MEASURE == "REMEDIAL_MEASURE"


def test_graph_relation_types() -> None:
    """Verifies 9 graph edge relation types."""
    relations = list(GraphRelationType)
    assert len(relations) == 9
    assert GraphRelationType.DEFINES_SANCTION_FOR == "DEFINES_SANCTION_FOR"
    assert GraphRelationType.HAS_ADDITIONAL_SANCTION == "HAS_ADDITIONAL_SANCTION"
    assert (
        GraphRelationType.REFERENCES_TECHNICAL_STANDARD
        == "REFERENCES_TECHNICAL_STANDARD"
    )
    assert GraphRelationType.MODIFIES_AND_REPLACES == "MODIFIES_AND_REPLACES"
    assert GraphRelationType.REPEALS == "REPEALS"
    assert GraphRelationType.OVERRIDES_PRIORITY == "OVERRIDES_PRIORITY"
    assert GraphRelationType.EXEMPTS_CONDITION == "EXEMPTS_CONDITION"
    assert GraphRelationType.GUIDES == "GUIDES"
    assert GraphRelationType.DEFINES_TERM == "DEFINES_TERM"


def test_cache_validation_status() -> None:
    """Verifies cache validation status enum."""
    assert len(CacheValidationStatus) == 4


def test_fine_bounds_auto_calculation() -> None:
    """Verifies FineBounds calculates average_fine_vnd when omitted."""
    bounds = FineBounds(min_fine_vnd=800_000, max_fine_vnd=1_000_000)
    assert bounds.average_fine_vnd == 900_000

    # Explicit average retained
    bounds_explicit = FineBounds(
        min_fine_vnd=800_000, max_fine_vnd=1_000_000, average_fine_vnd=950_000
    )
    assert bounds_explicit.average_fine_vnd == 950_000

    # Single bound
    single_min = FineBounds(min_fine_vnd=500_000)
    assert single_min.average_fine_vnd == 500_000


def test_fine_bounds_invalid_range() -> None:
    """Verifies FineBounds raises ValidationError when min > max."""
    with pytest.raises(
        ValidationError, match="min_fine_vnd .* cannot exceed max_fine_vnd"
    ):
        FineBounds(min_fine_vnd=2_000_000, max_fine_vnd=1_000_000)


def test_fine_bounds_currency_parsing() -> None:
    """Verifies deterministic Vietnamese currency parsing without naive heuristics."""
    assert FineBounds.parse_currency_amount("800.000", "đồng") == 800_000
    assert FineBounds.parse_currency_amount("1.000.000", "đồng") == 1_000_000
    assert FineBounds.parse_currency_amount("10.000", "nghìn đồng") == 10_000_000
    assert FineBounds.parse_currency_amount("2,5", "triệu đồng") == 2_500_000
    assert FineBounds.parse_currency_amount("2.5", "triệu") == 2_500_000
    assert FineBounds.parse_currency_amount("500", "nghìn") == 500_000
    assert FineBounds.parse_currency_amount("1", "tỷ") == 1_000_000_000


def test_fine_bounds_from_statutory_text() -> None:
    """Extracts FineBounds from statutory or conversational Vietnamese text."""
    fb1 = FineBounds.from_statutory_text(
        "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe..."
    )
    assert fb1.min_fine_vnd == 800_000
    assert fb1.max_fine_vnd == 1_000_000
    assert fb1.average_fine_vnd == 900_000

    fb2 = FineBounds.from_statutory_text("Phạt tiền từ 4 đến 6 triệu đồng")
    assert fb2.min_fine_vnd == 4_000_000
    assert fb2.max_fine_vnd == 6_000_000
    assert fb2.average_fine_vnd == 5_000_000

    fb3 = FineBounds.from_statutory_text("Phạt tiền từ 500 nghìn đến 1 triệu đồng")
    assert fb3.min_fine_vnd == 500_000
    assert fb3.max_fine_vnd == 1_000_000
    assert fb3.average_fine_vnd == 750_000


def test_additional_sanctions_validation() -> None:
    """Verifies AdditionalSanctions bounds and validators."""
    sanctions = AdditionalSanctions(
        license_suspension_months_min=1,
        license_suspension_months_max=3,
        vehicle_impoundment_days=7,
        demerit_points=2,
    )
    assert sanctions.license_suspension_months_min == 1
    assert sanctions.license_suspension_months_max == 3
    assert sanctions.vehicle_impoundment_days == 7
    assert sanctions.demerit_points == 2

    # Invalid suspension range
    with pytest.raises(
        ValidationError, match="license_suspension_months_min .* cannot exceed max"
    ):
        AdditionalSanctions(
            license_suspension_months_min=5, license_suspension_months_max=2
        )


def test_demerit_points_deduction() -> None:
    """Verifies DemeritPointDeduction accepts valid points."""
    valid_pt = DemeritPointDeduction(is_demerit_applicable=True, points_deducted=6)
    assert valid_pt.points_deducted == 6


def test_exception_metadata_and_referenced_entity() -> None:
    """Verifies ExceptionMetadata and ReferencedEntity defaults and structures."""
    exc = ExceptionMetadata(
        has_exception=True,
        exception_type="EMERGENCY_VEHICLE",
        exception_clause_text="Trừ các xe ưu tiên đang đi làm nhiệm vụ",
        overridden_by=["POLICE_COMMAND", "EMERGENCY_MISSION"],
    )
    assert exc.has_exception is True
    assert "POLICE_COMMAND" in exc.overridden_by

    ref = ReferencedEntity(
        law_articles=["Luật GTĐB 2008 Điều 10 Khoản 3"],
        qcvn_signs=["P.102"],
        qcvn_markings=["1.1"],
        amending_decrees=["123/2021/NĐ-CP"],
    )
    assert len(ref.law_articles) == 1
    assert ref.qcvn_signs == ["P.102"]


def test_legal_norm_extraction_model() -> None:
    """Verifies LegalNormExtraction full model instantiation and serialization."""
    norm = LegalNormExtraction(
        chunk_id="chunk-test-100-2019-art5-cl3-pt-a",
        hierarchy_path="doc_nd100_2019.art_5.cl_3.pt_a",
        document_code="100/2019/NĐ-CP",
        document_type="NGHI_DINH",
        article_number=5,
        article_index="Điều 5",
        clause_number=3,
        point_letter="a",
        norm_role=NormRole.SANCTION_PRINCIPAL,
        behavior_summary="Không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
        fine_bounds=FineBounds(min_fine_vnd=800_000, max_fine_vnd=1_000_000),
        additional_sanctions=AdditionalSanctions(
            license_suspension_months_min=1,
            license_suspension_months_max=3,
            demerit_points=2,
        ),
        remedial_measures=[],
        exceptions_and_overrides=ExceptionMetadata(
            has_exception=True,
            exception_type="EMERGENCY_VEHICLE",
            overridden_by=["POLICE_COMMAND"],
        ),
        referenced_entities=ReferencedEntity(
            law_articles=["Luật GTĐB 2008: Điều 10"],
        ),
        contextualized_text="[ĐIỀU 5] Ô tô vi phạm [KHOẢN 3] Phạt 800k-1tr [ĐIỂM a] Vượt đèn đỏ",
        verbatim_text="a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;",
    )

    assert norm.fine_bounds.average_fine_vnd == 900_000
    assert norm.additional_sanctions.demerit_points == 2

    # JSON Roundtrip serialization
    json_data = norm.model_dump_json()
    parsed = json.loads(json_data)
    assert parsed["chunk_id"] == "chunk-test-100-2019-art5-cl3-pt-a"
    assert parsed["fine_bounds"]["average_fine_vnd"] == 900_000

    recovered = LegalNormExtraction.model_validate_json(json_data)
    assert recovered.chunk_id == norm.chunk_id
    assert recovered.fine_bounds == norm.fine_bounds


def test_ltree_path_pattern_validation() -> None:
    """Verifies strict ltree regex validation on hierarchy_path."""
    assert LTREE_PATH_PATTERN == r"^doc_[a-z0-9_]+(?:\.[a-z0-9_]+)*$"

    valid_paths = [
        "doc_nd100_2019.a5.c3.p_a",
        "doc_luat_gt_2024.d10",
        "doc_qcvn41_2019.b1.s1",
    ]
    for path in valid_paths:
        extraction = LegalNormExtraction(
            chunk_id="test_chk",
            hierarchy_path=path,
            document_code="100/2019/ND-CP",
            document_type="NGHI_DINH",
            article_number=5,
            norm_role=NormRole.SANCTION_PRINCIPAL,
        )
        assert extraction.hierarchy_path == path

    invalid_paths = [
        "INVALID PATH WITH SPACES",
        "doc_nd100/2019.a5",
        "doc-nd100-2019.a5",
        "nd100_2019.a5",
        "doc_nd100_2019..a5",
        "doc_ND100_2019.a5",
    ]
    for path in invalid_paths:
        with pytest.raises(ValidationError):
            LegalNormExtraction(
                chunk_id="test_chk",
                hierarchy_path=path,
                document_code="100/2019/ND-CP",
                document_type="NGHI_DINH",
                article_number=5,
                norm_role=NormRole.SANCTION_PRINCIPAL,
            )


def test_canonical_fully_qualified_chunk() -> None:
    """Verifies CanonicalFullyQualifiedChunk model."""
    cfqc = CanonicalFullyQualifiedChunk(
        chunk_id="cfqc-uuid-001",
        document_id="doc-nd100-2019",
        document_code="100/2019/NĐ-CP",
        hierarchy_path="doc_nd100_2019.art_5.cl_3.pt_a",
        article_number=5,
        article_index="Điều 5",
        clause_number=3,
        point_letter="a",
        synthesized_prefix="[VĂN BẢN]: NĐ 100/2019\n[ĐIỀU 5]: Ô tô...",
        verbatim_text="a) Không chấp hành hiệu lệnh của đèn tín hiệu...",
        contextualized_text="[VĂN BẢN]: NĐ 100/2019...\n[ĐIỂM a]: Không chấp hành...",
        norm_role=NormRole.SANCTION_PRINCIPAL,
        fine_bounds=FineBounds(min_fine_vnd=800_000, max_fine_vnd=1_000_000),
        additional_sanctions=AdditionalSanctions(
            license_suspension_months_min=1, license_suspension_months_max=3
        ),
        embedding_vector=[0.123] * 384,
        is_active=True,
    )
    assert cfqc.is_active is True
    assert cfqc.embedding_vector is not None
    assert len(cfqc.embedding_vector) == 384
    assert (
        cfqc.full_citation_label
        == "Điểm a Khoản 3 Điều 5 100/2019/NĐ-CP"
    )
