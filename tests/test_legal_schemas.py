"""Unit tests for Vietnamese Traffic Law domain taxonomy and Pydantic v2 schemas."""

import json

import pytest
from pydantic import ValidationError

from rag_eval.legal.schemas import (
    LTREE_PATH_PATTERN,
    ActorCategory,
    AdditionalSanctions,
    AntiHallucinationAudit,
    CacheValidationStatus,
    CanonicalFullyQualifiedChunk,
    ChainOfCustody,
    ChainOfCustodyPlanSummary,
    ChainOfCustodyStep,
    ConflictEvaluationResult,
    DemeritPointDeduction,
    EvidenceChunkHash,
    ExceptionMetadata,
    ExecutionPlanDAG,
    ExtractedEntities,
    FineBounds,
    GraphRelationType,
    LegalIntent,
    LegalNormExtraction,
    NormRole,
    PrecedenceResolutionAudit,
    ReferencedEntity,
    SignalTier,
    SignCategoryEnum,
    SubGoalNode,
    SubGoalType,
    Temporality,
    TemporalValidationAudit,
    TrafficSignalCommand,
    VehicleCategory,
    ViolationCategory,
    ViolationType,
    expand_vehicle_category,
    hash_evidence_node,
    remove_vietnamese_diacritics,
)

# ==============================================================================
# Enum Definitions & Hierarchy Expansion Tests
# ==============================================================================


def test_vehicle_category_enumeration() -> None:
    """Verifies all 11 controlled vehicle categories exist and map correctly."""
    categories = list(VehicleCategory)
    assert len(categories) == 11
    assert VehicleCategory.CAR_PASSENGER == "CAR_PASSENGER"
    assert VehicleCategory.CAR_TRUCK == "CAR_TRUCK"
    assert VehicleCategory.CAR_BUS == "CAR_BUS"
    assert VehicleCategory.CAR_TRACTOR == "CAR_TRACTOR"
    assert VehicleCategory.MOTORCYCLE == "MOTORCYCLE"
    assert VehicleCategory.MOPED == "MOPED"
    assert VehicleCategory.E_MOPED == "E_MOPED"
    assert VehicleCategory.E_BICYCLE == "E_BICYCLE"
    assert VehicleCategory.BICYCLE_PRIMITIVE == "BICYCLE_PRIMITIVE"
    assert VehicleCategory.SPECIALIZED_MACHINE == "SPECIALIZED_MACHINE"
    assert VehicleCategory.PRIORITY_VEHICLE == "PRIORITY_VEHICLE"


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


def test_expand_vehicle_category_accented_vietnamese() -> None:
    """Verifies vehicle taxonomy expansion for natural accented Vietnamese strings."""
    assert expand_vehicle_category("xe ô tô") == [
        VehicleCategory.CAR_PASSENGER,
        VehicleCategory.CAR_TRUCK,
        VehicleCategory.CAR_BUS,
        VehicleCategory.CAR_TRACTOR,
    ]
    assert expand_vehicle_category("xe máy") == [VehicleCategory.MOTORCYCLE]
    assert expand_vehicle_category("xe tải") == [VehicleCategory.CAR_TRUCK]
    assert expand_vehicle_category("xe buýt") == [VehicleCategory.CAR_BUS]
    assert expand_vehicle_category("mô tô") == [VehicleCategory.MOTORCYCLE]
    assert expand_vehicle_category("xe gắn máy") == [VehicleCategory.MOPED]
    assert expand_vehicle_category("xe đạp") == [VehicleCategory.BICYCLE_PRIMITIVE]
    assert expand_vehicle_category("xe ô tô con") == [VehicleCategory.CAR_PASSENGER]
    assert expand_vehicle_category("ô tô tải") == [VehicleCategory.CAR_TRUCK]
    assert expand_vehicle_category("ô tô khách") == [VehicleCategory.CAR_BUS]
    assert expand_vehicle_category("xe đầu kéo") == [VehicleCategory.CAR_TRACTOR]
    assert expand_vehicle_category("xe máy điện") == [VehicleCategory.E_MOPED]
    assert expand_vehicle_category("xe đạp điện") == [VehicleCategory.E_BICYCLE]
    assert expand_vehicle_category("xe chuyên dùng") == [
        VehicleCategory.SPECIALIZED_MACHINE
    ]
    assert expand_vehicle_category("xe ưu tiên") == [VehicleCategory.PRIORITY_VEHICLE]


def test_expand_vehicle_category_groups() -> None:
    """Verifies vehicle taxonomy expansion for broad umbrella groups and specific aliases."""
    # CAR expansion
    cars = expand_vehicle_category("CAR")
    assert len(cars) == 4
    assert VehicleCategory.CAR_PASSENGER in cars
    assert VehicleCategory.CAR_TRUCK in cars
    assert VehicleCategory.CAR_BUS in cars
    assert VehicleCategory.CAR_TRACTOR in cars

    # Vietnamese alias for CAR
    oto_cars = expand_vehicle_category("xe_o_to")
    assert oto_cars == cars

    # Motor vehicles
    motor_all = expand_vehicle_category("XE_CO_GIOI")
    assert len(motor_all) == 7
    assert VehicleCategory.MOTORCYCLE in motor_all
    assert VehicleCategory.MOPED in motor_all
    assert VehicleCategory.E_MOPED in motor_all

    # Two-wheelers
    two_wheelers = expand_vehicle_category("TWO_WHEELER")
    assert len(two_wheelers) == 5
    assert VehicleCategory.E_BICYCLE in two_wheelers

    # Specific category as enum instance
    assert expand_vehicle_category(VehicleCategory.MOTORCYCLE) == [
        VehicleCategory.MOTORCYCLE
    ]
    assert expand_vehicle_category("xe_may") == [VehicleCategory.MOTORCYCLE]
    assert expand_vehicle_category("xe_may_dien") == [VehicleCategory.E_MOPED]
    assert expand_vehicle_category("xe_dap_dien") == [VehicleCategory.E_BICYCLE]
    assert expand_vehicle_category("xe_uu_tien") == [VehicleCategory.PRIORITY_VEHICLE]


def test_expand_vehicle_category_invalid() -> None:
    """Verifies invalid vehicle category raises ValueError."""
    with pytest.raises(ValueError, match="Unknown vehicle category"):
        expand_vehicle_category("SPACESHIP_INVALID")


def test_violation_category_enumeration() -> None:
    """Verifies 8 violation categories exist."""
    categories = list(ViolationCategory)
    assert len(categories) == 8
    expected = {
        "ALCOHOL_DRUGS",
        "SPEED_DISTANCE",
        "LANE_DIRECTION",
        "SIGNAL_COMPLIANCE",
        "STOP_PARK",
        "EQUIPMENT_SAFETY",
        "LOAD_PASSENGER",
        "DOCUMENTATION_VNEID",
    }
    assert {c.value for c in categories} == expected


def test_violation_types_coverage() -> None:
    """Verifies all statutory violation types exist in ViolationType enum."""
    types = list(ViolationType)
    assert len(types) == 38
    assert ViolationType.ALC_BRACKET_1 == "ALC_BRACKET_1"
    assert ViolationType.SPEED_OVER_10_20 == "SPEED_OVER_10_20"
    assert ViolationType.RED_LIGHT == "RED_LIGHT"
    assert ViolationType.WRONG_LANE == "WRONG_LANE"
    assert ViolationType.VNEID_INTEGRATION == "VNEID_INTEGRATION"


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


def test_sign_category_and_signal_tiers() -> None:
    """Verifies sign categories, tiers, and temporality enums."""
    assert len(SignCategoryEnum) == 8
    assert len(CacheValidationStatus) == 4
    assert len(LegalIntent) == 6

    # Signal precedence tiers
    assert SignalTier.POLICE_OFFICER == 1
    assert SignalTier.TRAFFIC_LIGHT == 2
    assert SignalTier.TRAFFIC_SIGN == 3
    assert SignalTier.ROAD_MARKING == 4
    assert (
        SignalTier.POLICE_OFFICER
        < SignalTier.TRAFFIC_LIGHT
        < SignalTier.TRAFFIC_SIGN
        < SignalTier.ROAD_MARKING
    )

    # Temporality
    assert Temporality.TEMPORARY == 1
    assert Temporality.PERMANENT == 2
    assert Temporality.TEMPORARY < Temporality.PERMANENT


# ==============================================================================
# Model Validation Tests
# ==============================================================================


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
    """Verifies FineBounds extraction from raw statutory and conversational text."""
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

    # Invalid demerit points step (must be in Literal[0, 2, 3, 4, 6, 8, 10, 12])
    with pytest.raises(ValidationError):
        AdditionalSanctions.model_validate({"demerit_points": 5})


def test_demerit_points_deduction() -> None:
    """Verifies DemeritPointDeduction accepts only valid point steps."""
    valid_pt = DemeritPointDeduction(is_demerit_applicable=True, points_deducted=6)
    assert valid_pt.points_deducted == 6

    with pytest.raises(ValidationError):
        DemeritPointDeduction.model_validate(
            {"is_demerit_applicable": True, "points_deducted": 5}
        )  # 5 is not in literal (0, 2, 3, 4, 6, 8, 10, 12)


def test_exception_metadata_and_referenced_entity() -> None:
    """Verifies ExceptionMetadata and ReferencedEntity defaults and structures."""
    exc = ExceptionMetadata(
        has_exception=True,
        exception_type="EMERGENCY_VEHICLE",
        exception_clause_text="Trừ các xe ưu tiên đang đi làm nhiệm vụ",
        overridden_by=["POLICE_COMMAND", "EMERGENCY_MISSION"],
        exempt_vehicle_categories=[VehicleCategory.PRIORITY_VEHICLE],
    )
    assert exc.has_exception is True
    assert exc.exempt_vehicle_categories == [VehicleCategory.PRIORITY_VEHICLE]

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
        primary_actor=ActorCategory.DRIVER,
        vehicle_types=[VehicleCategory.CAR_PASSENGER, VehicleCategory.CAR_TRUCK],
        violation_categories=[ViolationCategory.SIGNAL_COMPLIANCE],
        violation_types=[ViolationType.RED_LIGHT],
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
            exempt_vehicle_categories=[VehicleCategory.PRIORITY_VEHICLE],
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

    # Valid paths
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

    # Invalid paths
    invalid_paths = [
        "INVALID PATH WITH SPACES",
        "doc_nd100/2019.a5",
        "doc-nd100-2019.a5",
        "nd100_2019.a5",  # missing doc_ prefix
        "doc_nd100_2019..a5",  # double dot
        "doc_ND100_2019.a5",  # uppercase
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
        primary_actor=ActorCategory.DRIVER,
        vehicle_types=[VehicleCategory.CAR_PASSENGER],
        violation_categories=[ViolationCategory.SIGNAL_COMPLIANCE],
        violation_types=[ViolationType.RED_LIGHT],
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


def test_extracted_entities_and_classifiers() -> None:
    """Verifies ExtractedEntities helper classifiers for alcohol and speed violations."""
    # Alcohol classifiers
    e_clean = ExtractedEntities(alcohol_breath_mg_l=0.0, alcohol_blood_mg_100ml=0.0)
    assert e_clean.classify_alcohol_violation() is None

    e_alc1 = ExtractedEntities(alcohol_breath_mg_l=0.20)
    assert e_alc1.classify_alcohol_violation() == ViolationType.ALC_BRACKET_1

    e_alc2 = ExtractedEntities(alcohol_breath_mg_l=0.35)
    assert e_alc2.classify_alcohol_violation() == ViolationType.ALC_BRACKET_2

    e_alc3 = ExtractedEntities(alcohol_breath_mg_l=0.45)
    assert e_alc3.classify_alcohol_violation() == ViolationType.ALC_BRACKET_3

    # Speed classifiers
    e_speed_ok = ExtractedEntities(recorded_speed_kmh=53.0, speed_limit_kmh=50.0)
    assert e_speed_ok.calculate_speed_delta() == 3.0
    assert e_speed_ok.classify_speed_violation() is None

    e_speed_1 = ExtractedEntities(recorded_speed_kmh=58.0, speed_limit_kmh=50.0)
    assert e_speed_1.calculate_speed_delta() == 8.0
    assert e_speed_1.classify_speed_violation() == ViolationType.SPEED_OVER_5_10

    e_speed_2 = ExtractedEntities(recorded_speed_kmh=65.0, speed_limit_kmh=50.0)
    assert e_speed_2.calculate_speed_delta() == 15.0
    assert e_speed_2.classify_speed_violation() == ViolationType.SPEED_OVER_10_20

    e_speed_3 = ExtractedEntities(recorded_speed_kmh=75.0, speed_limit_kmh=50.0)
    assert e_speed_3.calculate_speed_delta() == 25.0
    assert e_speed_3.classify_speed_violation() == ViolationType.SPEED_OVER_20_35

    e_speed_4 = ExtractedEntities(recorded_speed_kmh=90.0, speed_limit_kmh=50.0)
    assert e_speed_4.calculate_speed_delta() == 40.0
    assert e_speed_4.classify_speed_violation() == ViolationType.SPEED_OVER_35_PLUS


def test_extracted_entities_and_execution_dag() -> None:
    """Verifies ExtractedEntities, SubGoalNode, and ExecutionPlanDAG modeling."""
    entities = ExtractedEntities(
        vehicle_category=VehicleCategory.CAR_TRUCK,
        vehicle_weight_tons=5.0,
        recorded_speed_kmh=68.0,
        speed_limit_kmh=50.0,
        traffic_sign_codes=["P.106a"],
        location_context="urban_residential",
    )
    assert entities.vehicle_weight_tons == 5.0

    g1 = SubGoalNode(
        goal_id="G1",
        goal_type=SubGoalType.LOOKUP_TECHNICAL_SPEC,
        mcp_tool_name="lookup_traffic_sign",
        tool_arguments={"sign_code": "P.106a"},
        dependencies=[],
        can_execute_parallel=True,
    )
    g2 = SubGoalNode(
        goal_id="G2",
        goal_type=SubGoalType.SEARCH_PRIMARY_SANCTION,
        mcp_tool_name="search_legal_clauses",
        tool_arguments={"vehicle": "CAR_TRUCK", "behavior": "prohibited_road"},
        dependencies=["G1"],
        can_execute_parallel=False,
    )

    dag = ExecutionPlanDAG(
        query_id="query-001",
        original_query="Tôi lái xe tải 5 tấn vào đường có biển P.106a phạt bao nhiêu?",
        primary_intent=LegalIntent.INTENT_PENALTY_LOOKUP,
        extracted_entities=entities,
        sub_goals=[g1, g2],
        execution_order=[["G1"], ["G2"]],
    )

    assert dag.primary_intent == LegalIntent.INTENT_PENALTY_LOOKUP
    assert len(dag.sub_goals) == 2
    assert dag.execution_order == [["G1"], ["G2"]]


def test_conflict_evaluation_and_traffic_signal_command() -> None:
    """Verifies TrafficSignalCommand and ConflictEvaluationResult models."""
    police_cmd = TrafficSignalCommand(
        source_type=SignalTier.POLICE_OFFICER,
        temporality=Temporality.TEMPORARY,
        command_directive="PROCEED",
        legal_citation="QCVN 41:2019/BGTVT Điều 4.1",
    )
    red_light_cmd = TrafficSignalCommand(
        source_type=SignalTier.TRAFFIC_LIGHT,
        temporality=Temporality.PERMANENT,
        command_directive="STOP",
        legal_citation="QCVN 41:2019/BGTVT Điều 10.3",
    )

    result = ConflictEvaluationResult(
        dominant_signal=police_cmd,
        suppressed_signals=[red_light_cmd],
        is_driver_action_legal=True,
        ruling_rationale="Hiệu lệnh CSGT có giá trị cao nhất, được phép đi qua đèn đỏ.",
        legal_basis=["QCVN 41:2019/BGTVT Điều 4.1", "Luật GTĐB 2008 Điều 11.2"],
    )

    assert result.dominant_signal.source_type == SignalTier.POLICE_OFFICER
    assert result.is_driver_action_legal is True
    assert len(result.suppressed_signals) == 1


def test_evidence_chunk_hash_and_immutability() -> None:
    """Verifies EvidenceChunkHash generation and cryptographic immutability."""
    text = "Điều 5 Khoản 3 Điểm a Nghị định 100/2019/NĐ-CP"
    ev = EvidenceChunkHash.from_text(
        chunk_id="chk_001",
        hierarchy_path="doc_nd100_2019.a5.c3.p_a",
        document_code="100/2019/NĐ-CP",
        text=text,
    )
    assert ev.sha256_digest == hash_evidence_node(text)
    assert ev.byte_length == len(text.encode("utf-8"))

    # Assert immutability via dynamic attribute mutation
    target_attr = "chunk_id"
    with pytest.raises(ValidationError):
        setattr(ev, target_attr, "mutated_id")


def test_chain_of_custody_and_cryptographic_hashing() -> None:
    """Verifies ChainOfCustody cryptographic step hashing, anti-hallucination model, and immutability."""
    sample_text = "Điều 5 Khoản 3 Điểm a Nghị định 100/2019/NĐ-CP"
    computed_hash = hash_evidence_node(sample_text)
    assert len(computed_hash) == 64  # SHA-256 hex string

    step = ChainOfCustodyStep(
        step_index=0,
        action="RETRIEVE_PRIMARY_SANCTION",
        tool_invoked="mcp_traffic_hybrid_search",
        target_node_id="chunk-100-2019-art5-cl3-pt-a",
        node_sha256=computed_hash,
        document_code="100/2019/NĐ-CP",
        hierarchy_path="doc_nd100_2019.art_5.cl_3.pt_a",
        exact_statutory_text=sample_text,
        relevance_score=0.96,
    )

    # Immutability on step
    target_attr_step = "exact_statutory_text"
    with pytest.raises(ValidationError):
        setattr(step, target_attr_step, "Mutated text")

    coc = ChainOfCustody(
        trace_id="coc-trace-20260829-001",
        session_id="session-user-123",
        query_fingerprint_sha256=hash_evidence_node("Vượt đèn đỏ ô tô phạt bao nhiêu?"),
        execution_timestamp="2026-08-29T16:45:00Z",
        plan_summary=ChainOfCustodyPlanSummary(
            primary_intent=LegalIntent.INTENT_PENALTY_LOOKUP,
            total_subgoals=2,
            execution_path=["G1", "G2"],
        ),
        retrieval_steps=[step],
        precedence_resolutions=[
            PrecedenceResolutionAudit(
                conflict_type="POLICE_VS_LIGHT",
                dominant_authority="POLICE_OFFICER",
                overridden_authorities=["TRAFFIC_LIGHT"],
                statutory_rule_applied="QCVN 41:2019/BGTVT Điều 4.1",
            )
        ],
        temporal_validation=TemporalValidationAudit(
            base_document="100/2019/NĐ-CP",
            active_amending_document="123/2021/NĐ-CP",
            is_amended=True,
            effective_date_evaluated="2026-01-01",
        ),
        anti_hallucination_audit=AntiHallucinationAudit(
            is_grounded=True,
            unmatched_citations=[],
            citation_coverage_pct=100.0,
            hallucination_score=0.0,
        ),
    )

    assert coc.anti_hallucination_audit.is_grounded is True
    assert coc.anti_hallucination_audit.hallucination_score == 0.0
    assert len(coc.retrieval_steps) == 1
    assert coc.retrieval_steps[0].node_sha256 == computed_hash

    # Immutability on master CoC
    target_attr_coc = "trace_id"
    with pytest.raises(ValidationError):
        setattr(coc, target_attr_coc, "tampered_trace")

    # Validate JSON serialization
    serialized = coc.model_dump_json()
    assert "coc-trace-20260829-001" in serialized
