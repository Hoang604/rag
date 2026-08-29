"""Tier 1: Feature Coverage tests for Requirement 5 (R5) - Multi-Hop Reasoning & Overrides."""

from __future__ import annotations

from typing import Any

from rag_eval.legal.reasoning.chain_of_custody import (
    ASTCitationValidator,
    ChainOfCustodyGenerator,
    ChainOfCustodyVerifier,
)
from rag_eval.legal.reasoning.overrides import (
    EmergencyVehicleTier,
    ScopeOverrideEngine,
)
from rag_eval.legal.reasoning.planner import QueryPlanner
from rag_eval.legal.schemas import (
    LegalIntent,
    PrecedenceResolutionAudit,
    SignalTier,
    Temporality,
    TrafficSignalCommand,
    VehicleCategory,
)


class TestR5ReasoningEngine:
    """Validates production reasoning classes directly (Zero-Mock in Tier 1)."""

    # --------------------------------------------------------------------------
    # 1. QueryPlanner & Entity Extraction
    # --------------------------------------------------------------------------
    def test_query_planner_decomposes_speeding_intent_and_slots(self) -> None:
        planner = QueryPlanner()
        plan = planner.plan("Tôi lái xe ô tô con chạy 68 km/h trong đô thị vượt quá tốc độ tối đa 50 km/h phạt bao nhiêu?")
        assert plan.primary_intent == LegalIntent.INTENT_PENALTY_LOOKUP
        assert plan.extracted_entities.vehicle_category == VehicleCategory.CAR_PASSENGER
        assert plan.extracted_entities.recorded_speed_kmh == 68.0
        assert plan.extracted_entities.speed_limit_kmh == 50.0
        assert plan.extracted_entities.location_context == "urban_residential"
        assert len(plan.sub_goals) >= 2
        assert plan.execution_order[0] == ["G1"]

    def test_query_planner_identifies_all_six_legal_intents(self) -> None:
        planner = QueryPlanner()

        # Priority Conflict
        plan_conflict = planner.plan("Cảnh sát giao thông ra hiệu đi tiếp nhưng đèn đỏ thì tuân theo ai?")
        assert plan_conflict.primary_intent == LegalIntent.INTENT_PRIORITY_CONFLICT
        assert plan_conflict.extracted_entities.has_conflicting_authority is True

        # Technical Standard
        plan_tech = planner.plan("Biển báo P.102 có ý nghĩa và quy chuẩn kích thước thế nào?")
        assert plan_tech.primary_intent == LegalIntent.INTENT_TECHNICAL_STANDARD
        assert "P.102" in plan_tech.extracted_entities.traffic_sign_codes

        # Behavior Validation
        plan_behavior = planner.plan("Hành vi chuyển làn không bật xi nhan trên cao tốc có đúng hay sai?")
        assert plan_behavior.primary_intent == LegalIntent.INTENT_BEHAVIOR_VALIDATION
        assert plan_behavior.extracted_entities.location_context == "expressway"

        # Procedural Timeline
        plan_timeline = planner.plan("Thời hạn nộp phạt vi phạm giao thông và tạm giữ xe bao lâu?")
        assert plan_timeline.primary_intent == LegalIntent.INTENT_PROCEDURAL_TIMELINE

        # Comparative Synthesis
        plan_comp = planner.plan("So sánh mức phạt nồng độ cồn giữa ô tô và xe máy?")
        assert plan_comp.primary_intent == LegalIntent.INTENT_COMPARATIVE_SYNTHESIS

        # Penalty Lookup
        plan_pen = planner.plan("Xe máy đi vào đường cấm phạt bao nhiêu tiền?")
        assert plan_pen.primary_intent == LegalIntent.INTENT_PENALTY_LOOKUP
        assert plan_pen.extracted_entities.vehicle_category == VehicleCategory.MOTORCYCLE

    def test_query_planner_numeric_slot_extraction(self) -> None:
        planner = QueryPlanner()
        plan = planner.plan("Xe tải 5 tấn có nồng độ cồn 0.55 mg/l và 80 mg/100ml vi phạm vạch 1.1")
        assert plan.extracted_entities.vehicle_category == VehicleCategory.CAR_TRUCK
        assert plan.extracted_entities.vehicle_weight_tons == 5.0
        assert plan.extracted_entities.alcohol_breath_mg_l == 0.55
        assert plan.extracted_entities.alcohol_blood_mg_100ml == 80.0
        assert "1.1" in plan.extracted_entities.road_marking_codes

    # --------------------------------------------------------------------------
    # 2. ScopeOverrideEngine Precedence Algebra
    # --------------------------------------------------------------------------
    def test_scope_override_police_officer_dominates_traffic_light(self) -> None:
        engine = ScopeOverrideEngine()
        signals = [
            TrafficSignalCommand(
                source_type=SignalTier.POLICE_OFFICER,
                temporality=Temporality.PERMANENT,
                command_directive="PROCEED",
                legal_citation="Điều 4 Khoản 4.1 QCVN 41:2019/BGTVT",
            ),
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_LIGHT,
                temporality=Temporality.PERMANENT,
                command_directive="STOP",
                legal_citation="Điều 4 Khoản 4.2 QCVN 41:2019/BGTVT",
            ),
        ]
        result = engine.resolve_signal_conflict(signals, driver_action="PROCEED")
        assert result.dominant_signal.source_type == SignalTier.POLICE_OFFICER
        assert result.is_driver_action_legal is True
        assert any("QCVN 41:2019/BGTVT" in b for b in result.legal_basis)

    def test_scope_override_traffic_light_dominates_traffic_sign(self) -> None:
        engine = ScopeOverrideEngine()
        signals = [
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_LIGHT,
                temporality=Temporality.PERMANENT,
                command_directive="STOP",
                legal_citation="Điều 4 Khoản 4.2 QCVN 41:2019/BGTVT",
            ),
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_SIGN,
                temporality=Temporality.PERMANENT,
                command_directive="PROCEED",
                legal_citation="Điều 4 Khoản 4.4 QCVN 41:2019/BGTVT",
            ),
        ]
        result = engine.resolve_signal_conflict(signals, driver_action="STOP")
        assert result.dominant_signal.source_type == SignalTier.TRAFFIC_LIGHT
        assert result.is_driver_action_legal is True

    def test_scope_override_temporary_sign_dominates_permanent_sign(self) -> None:
        engine = ScopeOverrideEngine()
        signals = [
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_SIGN,
                temporality=Temporality.TEMPORARY,
                command_directive="SPEED_LIMIT",
                speed_cap_kmh=40.0,
                legal_citation="QCVN 41:2019 Điều 4 Khoản 4.3 (Biển tạm)",
            ),
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_SIGN,
                temporality=Temporality.PERMANENT,
                command_directive="SPEED_LIMIT",
                speed_cap_kmh=60.0,
                legal_citation="QCVN 41:2019 Điều 4 Khoản 4.4 (Biển cố định)",
            ),
        ]
        result = engine.resolve_signal_conflict(signals, driver_speed_kmh=45.0)
        assert result.dominant_signal.temporality == Temporality.TEMPORARY
        # 45 km/h exceeds 40 km/h temporary limit
        assert result.is_driver_action_legal is False

        # Legal at 38 km/h
        result_legal = engine.resolve_signal_conflict(signals, driver_speed_kmh=38.0)
        assert result_legal.is_driver_action_legal is True

    def test_emergency_vehicle_exemption_evaluation(self) -> None:
        engine = ScopeOverrideEngine()
        res_on_duty = engine.evaluate_emergency_privilege(
            vehicle_type=VehicleCategory.PRIORITY_VEHICLE,
            is_on_duty=True,
            has_siren_beacon=True,
            emergency_tier=EmergencyVehicleTier.AMBULANCE,
        )
        assert res_on_duty["is_exempt"] is True
        assert res_on_duty["emergency_tier"] == "AMBULANCE"
        assert "Điều 22 Luật GTĐB 2008" in res_on_duty["legal_basis"][0]

        res_civilian = engine.evaluate_emergency_privilege(
            vehicle_type=VehicleCategory.CAR_PASSENGER,
            is_on_duty=False,
            has_siren_beacon=False,
        )
        assert res_civilian["is_exempt"] is False

    def test_emergency_vehicle_conflict_resolution_fire_vs_ambulance(self) -> None:
        engine = ScopeOverrideEngine()
        res = engine.resolve_emergency_vehicle_conflict(
            vehicle_a_tier=EmergencyVehicleTier.FIRE_FIGHTING,
            vehicle_b_tier=EmergencyVehicleTier.AMBULANCE,
        )
        assert res["dominant_vehicle"] == "Vehicle A"
        assert res["dominant_tier"] == "FIRE_FIGHTING"
        assert res["dominant_rank"] == 1.1

    def test_to_audit_trace_conversion(self) -> None:
        engine = ScopeOverrideEngine()
        signals = [
            TrafficSignalCommand(
                source_type=SignalTier.POLICE_OFFICER,
                temporality=Temporality.PERMANENT,
                command_directive="PROCEED",
                legal_citation="QCVN 41:2019 Điều 4.1",
            ),
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_LIGHT,
                temporality=Temporality.PERMANENT,
                command_directive="STOP",
                legal_citation="QCVN 41:2019 Điều 4.2",
            ),
        ]
        result = engine.resolve_signal_conflict(signals, driver_action="PROCEED")
        audit_trace = engine.to_audit_trace(result)
        assert isinstance(audit_trace, PrecedenceResolutionAudit)
        assert audit_trace.dominant_authority == "POLICE_OFFICER"
        assert audit_trace.overridden_authorities == ["TRAFFIC_LIGHT"]

    # --------------------------------------------------------------------------
    # 3. ChainOfCustody & True AST Grounding Validator
    # --------------------------------------------------------------------------
    def test_chain_of_custody_cryptographic_evidence_and_grounding(self) -> None:
        coc_gen = ChainOfCustodyGenerator()
        chunks: list[dict[str, Any]] = [
            {
                "chunk_id": "chk_nd100_art5",
                "doc_code": "100/2019/ND-CP",
                "path": "doc_nd100_2019.a5.c3.p_a",
                "raw_text": "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe: a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
                "rrf_score": 0.96,
            }
        ]
        advisory = "Căn cứ theo Điều 5 Khoản 3 Điểm a Nghị định 100/2019/NĐ-CP phạt tiền từ 800.000đ đến 1.000.000đ."
        coc = coc_gen.generate("vượt đèn đỏ ô tô", chunks, advisory)

        assert coc.trace_id.startswith("coc-")
        assert len(coc.query_fingerprint_sha256) == 64
        assert len(coc.retrieval_steps) == 1
        assert len(coc.retrieval_steps[0].node_sha256) == 64
        assert len(coc.evidence_hashes) == 1
        assert coc.anti_hallucination_audit.is_grounded is True
        assert coc.anti_hallucination_audit.citation_coverage_pct == 100.0
        assert ChainOfCustodyVerifier.verify_hash_chain(coc, "vượt đèn đỏ ô tô") is True
        assert ChainOfCustodyVerifier.verify_evidence_digests(coc) is True

    def test_ast_citation_validator_detects_hallucination(self) -> None:
        validator = ASTCitationValidator()
        chunks: list[dict[str, Any]] = [
            {
                "chunk_id": "chk_nd100_art5",
                "doc_code": "100/2019/ND-CP",
                "hierarchy_path": "doc_nd100_2019.a5.c3.p_a",
                "verbatim_text": "Điều 5 Khoản 3 Điểm a quy định xử phạt vi phạm giao thông",
            }
        ]
        # Advisory fabricates Article 999
        hallucinated_text = "Căn cứ theo Điều 999 Nghị định 100/2019/NĐ-CP mức phạt là 50 triệu đồng."
        audit = validator.validate(hallucinated_text, chunks)

        assert audit.is_grounded is False
        assert len(audit.unmatched_citations) >= 1
        assert audit.hallucination_score > 0.0
        assert audit.citation_coverage_pct < 100.0

    def test_chain_of_custody_verifier_tamper_detection(self) -> None:
        coc_gen = ChainOfCustodyGenerator()
        chunks: list[dict[str, Any]] = [
            {
                "chunk_id": "chk_nd100_art5",
                "doc_code": "100/2019/ND-CP",
                "path": "doc_nd100_2019.a5.c3.p_a",
                "raw_text": "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng",
            }
        ]
        query = "vượt đèn đỏ ô tô"
        coc = coc_gen.generate(query, chunks, "Căn cứ Điều 5 Nghị định 100/2019/NĐ-CP")

        # True query matches
        assert ChainOfCustodyVerifier.verify_hash_chain(coc, query) is True

        # Tampered query fails
        assert ChainOfCustodyVerifier.verify_hash_chain(coc, "câu hỏi giả mạo") is False

        # Canonical JSON and fingerprint
        canon_json = ChainOfCustodyVerifier.to_canonical_json(coc)
        assert isinstance(canon_json, str)
        fingerprint = ChainOfCustodyVerifier.calculate_coc_fingerprint(coc)
        assert len(fingerprint) == 64
