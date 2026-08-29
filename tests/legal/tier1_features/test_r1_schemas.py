"""Tier 1: Feature Coverage tests for Requirement 1 (R1) - Domain Models & Strict Schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag_eval.legal.schemas import (
    ActorCategory,
    AdditionalSanctions,
    AntiHallucinationAudit,
    CanonicalFullyQualifiedChunk,
    ChainOfCustody,
    ChainOfCustodyPlanSummary,
    ChainOfCustodyStep,
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
    ReferencedEntity,
    SignCategoryEnum,
    SubGoalNode,
    SubGoalType,
    VehicleCategory,
    ViolationCategory,
    expand_vehicle_category,
    hash_evidence_node,
    remove_vietnamese_diacritics,
)


class TestR1DomainTaxonomies:
    """Validate all controlled domain taxonomies and enumeration invariants."""

    def test_vehicle_category_has_11_controlled_classes(self) -> None:
        expected_classes = {
            "CAR_PASSENGER",
            "CAR_TRUCK",
            "CAR_BUS",
            "CAR_TRACTOR",
            "MOTORCYCLE",
            "MOPED",
            "E_MOPED",
            "E_BICYCLE",
            "BICYCLE_PRIMITIVE",
            "SPECIALIZED_MACHINE",
            "PRIORITY_VEHICLE",
        }
        actual_classes = {item.value for item in VehicleCategory}
        assert actual_classes == expected_classes
        assert len(VehicleCategory) == 11

    def test_violation_category_has_8_core_categories(self) -> None:
        expected_categories = {
            "ALCOHOL_DRUGS",
            "SPEED_DISTANCE",
            "LANE_DIRECTION",
            "SIGNAL_COMPLIANCE",
            "STOP_PARK",
            "EQUIPMENT_SAFETY",
            "LOAD_PASSENGER",
            "DOCUMENTATION_VNEID",
        }
        actual_categories = {item.value for item in ViolationCategory}
        assert actual_categories == expected_categories
        assert len(ViolationCategory) == 8

    def test_norm_role_has_8_functional_roles(self) -> None:
        assert len(NormRole) == 8
        assert NormRole.HYPOTHESIS_CONDITION.value == "HYPOTHESIS_CONDITION"
        assert NormRole.PRESCRIPTION_DUTY.value == "PRESCRIPTION_DUTY"
        assert NormRole.PRESCRIPTION_PROHIBITION.value == "PRESCRIPTION_PROHIBITION"
        assert NormRole.PRESCRIPTION_PERMISSION.value == "PRESCRIPTION_PERMISSION"
        assert NormRole.SANCTION_PRINCIPAL.value == "SANCTION_PRINCIPAL"
        assert NormRole.SANCTION_SUPPLEMENTARY.value == "SANCTION_SUPPLEMENTARY"
        assert NormRole.SANCTION_POINT_DEDUCTION.value == "SANCTION_POINT_DEDUCTION"
        assert NormRole.REMEDIAL_MEASURE.value == "REMEDIAL_MEASURE"

    def test_actor_category_coverage(self) -> None:
        assert len(ActorCategory) == 7
        assert ActorCategory.DRIVER.value == "DRIVER"
        assert ActorCategory.VEHICLE_OWNER.value == "VEHICLE_OWNER"

    def test_graph_relation_type_has_9_statutory_relations(self) -> None:
        expected = {
            "DEFINES_SANCTION_FOR",
            "HAS_ADDITIONAL_SANCTION",
            "REFERENCES_TECHNICAL_STANDARD",
            "MODIFIES_AND_REPLACES",
            "REPEALS",
            "OVERRIDES_PRIORITY",
            "EXEMPTS_CONDITION",
            "GUIDES",
            "DEFINES_TERM",
        }
        assert {item.value for item in GraphRelationType} == expected
        assert len(GraphRelationType) == 9

    def test_sign_category_coverage(self) -> None:
        assert len(SignCategoryEnum) == 8
        assert SignCategoryEnum.PROHIBITORY.value == "PROHIBITORY"
        assert SignCategoryEnum.POLICE_SIGNAL.value == "POLICE_SIGNAL"

    def test_vehicle_category_expansion_accented_and_groups(self) -> None:
        assert remove_vietnamese_diacritics("xe ô tô") == "XE_O_TO"
        assert remove_vietnamese_diacritics("xe   ô-tô   con") == "XE_O_TO_CON"
        assert expand_vehicle_category("xe ô tô") == [
            VehicleCategory.CAR_PASSENGER,
            VehicleCategory.CAR_TRUCK,
            VehicleCategory.CAR_BUS,
            VehicleCategory.CAR_TRACTOR,
        ]
        assert expand_vehicle_category("xe máy") == [VehicleCategory.MOTORCYCLE]
        assert expand_vehicle_category("xe gắn máy") == [VehicleCategory.MOPED]
        assert expand_vehicle_category("xe đạp điện") == [VehicleCategory.E_BICYCLE]


class TestR1ExtractionModels:
    """Validate Pydantic v2 extraction models and field validators."""

    def test_fine_bounds_valid_range_calculates_midpoint(self) -> None:
        bounds = FineBounds(min_fine_vnd=4000000, max_fine_vnd=6000000)
        assert bounds.min_fine_vnd == 4000000
        assert bounds.max_fine_vnd == 6000000
        assert bounds.average_fine_vnd == 5000000

    def test_fine_bounds_min_exceeding_max_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="cannot exceed max_fine_vnd"):
            FineBounds(min_fine_vnd=6000000, max_fine_vnd=4000000)

    def test_fine_bounds_negative_fine_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            FineBounds(min_fine_vnd=-100000, max_fine_vnd=500000)

    def test_fine_bounds_currency_parsing_and_from_text(self) -> None:
        fb = FineBounds.from_statutory_text("Phạt tiền từ 800.000 đồng đến 1.000.000 đồng")
        assert fb.min_fine_vnd == 800000
        assert fb.max_fine_vnd == 1000000
        assert fb.average_fine_vnd == 900000

    def test_additional_sanctions_valid_ranges(self) -> None:
        sanctions = AdditionalSanctions(
            license_suspension_months_min=1,
            license_suspension_months_max=3,
            vehicle_impoundment_days=7,
            demerit_points=2,
        )
        assert sanctions.license_suspension_months_min == 1
        assert sanctions.license_suspension_months_max == 3
        assert sanctions.demerit_points == 2

    def test_additional_sanctions_invalid_suspension_order_raises_error(self) -> None:
        with pytest.raises(ValidationError, match="cannot exceed max"):
            AdditionalSanctions(
                license_suspension_months_min=12, license_suspension_months_max=6
            )

        with pytest.raises(ValidationError):
            AdditionalSanctions.model_validate({"demerit_points": 5})

    def test_demerit_points_deduction_steps(self) -> None:
        demerit = DemeritPointDeduction(is_demerit_applicable=True, points_deducted=4)
        assert demerit.points_deducted == 4
        with pytest.raises(ValidationError):
            DemeritPointDeduction.model_validate(
                {"is_demerit_applicable": True, "points_deducted": 5}
            )

    def test_exception_metadata_model(self) -> None:
        meta = ExceptionMetadata(
            has_exception=True,
            exception_type="EMERGENCY_VEHICLE",
            exception_clause_text="Trừ các xe ưu tiên",
            overridden_by=["POLICE_COMMAND"],
            exempt_vehicle_categories=[VehicleCategory.PRIORITY_VEHICLE],
        )
        assert meta.has_exception is True
        assert VehicleCategory.PRIORITY_VEHICLE in meta.exempt_vehicle_categories

    def test_legal_norm_extraction_valid_cfqc(self) -> None:
        extraction = LegalNormExtraction(
            chunk_id="chk_001",
            hierarchy_path="doc_nd100_2019.c2.s1.a5.c3.p_a",
            document_code="100/2019/ND-CP",
            document_type="NGHI_DINH",
            article_number=5,
            article_index="Điều 5",
            clause_number=3,
            point_letter="a",
            norm_role=NormRole.SANCTION_PRINCIPAL,
            primary_actor=ActorCategory.DRIVER,
            vehicle_types=[VehicleCategory.CAR_PASSENGER],
            violation_categories=[ViolationCategory.SIGNAL_COMPLIANCE],
            behavior_summary="Không chấp hành hiệu lệnh đèn tín hiệu",
            fine_bounds=FineBounds(min_fine_vnd=800000, max_fine_vnd=1000000),
            additional_sanctions=AdditionalSanctions(
                license_suspension_months_min=1, license_suspension_months_max=3
            ),
            remedial_measures=[],
            exceptions_and_overrides=ExceptionMetadata(has_exception=False),
            referenced_entities=ReferencedEntity(),
            contextualized_text="Nghị định 100 Điều 5 Khoản 3 Điểm a",
        )
        assert extraction.article_number == 5
        assert extraction.fine_bounds.average_fine_vnd == 900000

    def test_canonical_fully_qualified_chunk_full_citation_label(self) -> None:
        cfqc = CanonicalFullyQualifiedChunk(
            chunk_id="cfqc-001",
            document_id="doc-001",
            document_code="100/2019/NĐ-CP",
            hierarchy_path="doc_nd100_2019.a5.c3.p_a",
            article_number=5,
            article_index="Điều 5",
            clause_number=3,
            point_letter="a",
            synthesized_prefix="prefix",
            verbatim_text="verbatim",
            contextualized_text="context",
            norm_role=NormRole.SANCTION_PRINCIPAL,
            primary_actor=ActorCategory.DRIVER,
        )
        assert cfqc.full_citation_label == "Điểm a Khoản 3 Điều 5 100/2019/NĐ-CP"

    def test_legal_norm_extraction_invalid_ltree_path_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            LegalNormExtraction(
                chunk_id="chk_001",
                hierarchy_path="INVALID PATH WITH SPACES",
                document_code="100/2019/ND-CP",
                document_type="NGHI_DINH",
                article_number=5,
                norm_role=NormRole.SANCTION_PRINCIPAL,
                vehicle_types=[VehicleCategory.CAR_PASSENGER],
                violation_categories=[ViolationCategory.SIGNAL_COMPLIANCE],
                behavior_summary="Test invalid path",
                contextualized_text="Context",
            )


class TestR1ReasoningModels:
    """Validate reasoning schemas (ExecutionPlanDAG, ChainOfCustody, EvidenceChunkHash)."""

    def test_execution_plan_dag_creation(self) -> None:
        sub_goal1 = SubGoalNode(
            goal_id="G1",
            goal_type=SubGoalType.SEARCH_PRIMARY_SANCTION,
            mcp_tool_name="mcp_traffic_hybrid_search",
            tool_arguments={"query": "vượt đèn đỏ ô tô"},
        )
        plan = ExecutionPlanDAG(
            query_id="q_123",
            original_query="vượt đèn đỏ ô tô phạt bao nhiêu",
            primary_intent=LegalIntent.INTENT_PENALTY_LOOKUP,
            extracted_entities=ExtractedEntities(
                vehicle_category=VehicleCategory.CAR_PASSENGER
            ),
            sub_goals=[sub_goal1],
            execution_order=[["G1"]],
        )
        assert plan.query_id == "q_123"
        assert plan.primary_intent == LegalIntent.INTENT_PENALTY_LOOKUP
        assert plan.sub_goals[0].goal_id == "G1"

    def test_evidence_chunk_hash_and_immutability(self) -> None:
        text = "Điều 5 Nghị định 100/2019/NĐ-CP"
        ev = EvidenceChunkHash.from_text(
            chunk_id="chk_001",
            hierarchy_path="doc_nd100_2019.a5",
            document_code="100/2019/NĐ-CP",
            text=text,
        )
        assert ev.sha256_digest == hash_evidence_node(text)
        target_attr = "chunk_id"
        with pytest.raises(ValidationError):
            setattr(ev, target_attr, "mutated")

    def test_chain_of_custody_validation(self) -> None:
        step = ChainOfCustodyStep(
            step_index=1,
            action="HYBRID_SEARCH",
            tool_invoked="mcp_traffic_hybrid_search",
            target_node_id="chk_nd100_art5",
            node_sha256="abc123sha",
            document_code="100/2019/ND-CP",
            hierarchy_path="doc_nd100.art5",
            exact_statutory_text="Phạt tiền từ 800.000đ đến 1.000.000đ",
            relevance_score=0.98,
        )
        coc = ChainOfCustody(
            trace_id="coc-001",
            session_id="sess-001",
            query_fingerprint_sha256="sha256fingerprint",
            execution_timestamp="2026-08-29T10:00:00Z",
            plan_summary=ChainOfCustodyPlanSummary(
                primary_intent=LegalIntent.INTENT_PENALTY_LOOKUP,
                total_subgoals=1,
                execution_path=["G1"],
            ),
            retrieval_steps=[step],
            anti_hallucination_audit=AntiHallucinationAudit(
                is_grounded=True,
                unmatched_citations=[],
                citation_coverage_pct=100.0,
            ),
        )
        assert coc.trace_id == "coc-001"
        assert coc.anti_hallucination_audit.is_grounded is True
        assert coc.retrieval_steps[0].relevance_score == 0.98

        # Master CoC is immutable
        target_attr = "trace_id"
        with pytest.raises(ValidationError):
            setattr(coc, target_attr, "coc-002")
