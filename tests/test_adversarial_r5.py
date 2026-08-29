"""Adversarial stress-testing suite for Milestone R5 (Reasoning Engine & Anti-Hallucination Gate).

Covers:
1. ASTCitationValidator:
   - Fabricated citations (Điều 999 Nghị định 100, Khoản 99 Điều 5, Điểm z Khoản 1, Biển P.999, Vạch 99.99).
   - Diacritic variations, uppercase/lowercase, unaccented matching, compound formatting.
   - Empty text, empty chunks, partial hallucination scoring.
2. ChainOfCustodyVerifier:
   - Cryptographic SHA-256 Merkle hash chain verification.
   - Query tampering, intermediate step mutation, payload corruption, step reordering, step omission.
   - Evidence digest verification against verbatim statutory texts.
   - RFC 8785 canonical JSON serialization and master fingerprint sensitivity.
3. ScopeOverrideEngine & Precedence Algebra:
   - Strict 6-tier statutory priority inequality ordering.
   - 5-tier emergency vehicle privilege hierarchy and equal-priority resolution.
   - Temporary speed sign vs permanent sign conflict resolution.
4. DeterministicTriadTraverser & QueryPlanner:
   - Cycle elimination, self-loop prevention, parallel fan-out stability.
   - 6 Legal Intents classification under adversarial phrasing and numerical slot boundary parsing.
"""

from __future__ import annotations

from typing import Any

import pytest

from rag_eval.legal.reasoning.chain_of_custody import (
    ASTCitationValidator,
    ChainOfCustodyGenerator,
    ChainOfCustodyVerifier,
    ParsedStatutoryCitation,
)
from rag_eval.legal.reasoning.overrides import (
    EmergencyVehicleTier,
    ScopeOverrideEngine,
    StatutoryPrecedenceRank,
)
from rag_eval.legal.reasoning.planner import QueryPlanner
from rag_eval.legal.schemas import (
    AntiHallucinationAudit,
    ChainOfCustody,
    SignalTier,
    Temporality,
    VehicleCategory,
)

# ==============================================================================
# 1. ASTCitationValidator Adversarial Stress Tests
# ==============================================================================


class TestAdversarialASTCitationValidator:
    """Stress tests statutory citation parsing and anti-hallucination grounding."""

    @pytest.fixture
    def validator(self) -> ASTCitationValidator:
        return ASTCitationValidator()

    @pytest.fixture
    def valid_chunks(self) -> list[dict[str, Any]]:
        return [
            {
                "chunk_id": "chk_nd100_art5_cl3_pa",
                "document_code": "100/2019/ND-CP",
                "hierarchy_path": "doc_nd100_2019.a5.c3.p_a",
                "article_number": "5",
                "verbatim_text": (
                    "Điều 5. Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông đường bộ\n"
                    "3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:\n"
                    "a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;"
                ),
            },
            {
                "chunk_id": "chk_nd100_art6_cl3_pb",
                "document_code": "100/2019/ND-CP",
                "hierarchy_path": "doc_nd100_2019.a6.c3.p_b",
                "article_number": "6",
                "verbatim_text": (
                    "Điều 6. Xử phạt người điều khiển xe mô tô, xe gắn máy\n"
                    "3. Phạt tiền từ 600.000 đồng đến 1.000.000 đồng:\n"
                    "b) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;"
                ),
            },
            {
                "chunk_id": "chk_qcvn41_art4",
                "document_code": "QCVN 41:2019/BGTVT",
                "hierarchy_path": "doc_qcvn41_2019.a4",
                "article_number": "4",
                "verbatim_text": (
                    "Điều 4. Thứ tự hiệu lực của hệ thống báo hiệu đường bộ\n"
                    "4.1. Hiệu lệnh của người điều khiển giao thông;\n"
                    "4.2. Tín hiệu đèn giao thông;\n"
                    "4.3. Biển báo hiệu tạm thời;\n"
                    "4.4. Biển báo hiệu cố định;\n"
                    "4.5. Vạch kẻ đường và các dấu hiệu khác trên mặt đường."
                ),
                "referenced_entities": {
                    "qcvn_signs": ["P.102", "P.103a", "W.201a"],
                    "law_articles": ["Điều 11 Luật GTĐB 2008"],
                },
            },
        ]

    def test_fabricated_article_triggers_hallucination(
        self, validator: ASTCitationValidator, valid_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that non-existent Article 999 is detected as ungrounded."""
        advisory = "Theo quy định tại Điều 999 Nghị định 100/2019/NĐ-CP, hành vi này bị phạt 50.000.000 đồng."
        audit: AntiHallucinationAudit = validator.validate(advisory, valid_chunks)

        assert audit.is_grounded is False
        assert audit.hallucination_score > 0.0
        assert audit.citation_coverage_pct < 100.0
        assert any("999" in c for c in audit.unmatched_citations)

    def test_fabricated_clause_article_first_triggers_hallucination(
        self, validator: ASTCitationValidator, valid_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that Article-first non-existent Clause 99 of Article 5 is detected."""
        advisory = "Căn cứ Điều 5 Khoản 99 Nghị định 100/2019/NĐ-CP, người vi phạm bị phạt tiền 10 triệu."
        audit: AntiHallucinationAudit = validator.validate(advisory, valid_chunks)

        assert audit.is_grounded is False
        assert audit.hallucination_score > 0.0
        assert len(audit.unmatched_citations) >= 1

    def test_fabricated_clause_point_first_adversarial_vulnerability(
        self, validator: ASTCitationValidator, valid_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that Point/Clause-first fabricated clause (Khoản 99 Điều 5) is rejected."""
        advisory = "Căn cứ Khoản 99 Điều 5 Nghị định 100/2019/NĐ-CP, người vi phạm bị phạt tiền 10 triệu."
        citations = validator.extract_citations(advisory)
        # Verify Khoản 99 was extracted and not masked by coarse Điều 5
        has_clause_99 = any(c.clause_num == "99" for c in citations)
        assert has_clause_99 is True

        audit = validator.validate(advisory, valid_chunks)
        assert audit.is_grounded is False
        assert audit.hallucination_score > 0.0
        assert len(audit.unmatched_citations) >= 1
        assert any("99" in c for c in audit.unmatched_citations)

    def test_fabricated_point_adversarial_vulnerability(
        self, validator: ASTCitationValidator, valid_chunks: list[dict[str, Any]]
    ) -> None:
        """Verifies that point-level validation correctly catches fabricated points.

        When formatted as 'Điều 5 Khoản 3 Điểm z', point_letter='z' does not exist in chunk (only 'a' exists),
        and validator strictly sets is_grounded to False.
        """
        advisory = "Căn cứ Điều 5 Khoản 3 Điểm z Nghị định 100/2019/NĐ-CP, hành vi bị phạt tiền."
        citations = validator.extract_citations(advisory)
        assert len(citations) >= 1
        cit = citations[0]
        assert cit.point_letter == "z"

        audit = validator.validate(advisory, valid_chunks)
        assert isinstance(audit, AntiHallucinationAudit)
        assert audit.is_grounded is False
        assert audit.hallucination_score > 0.0
        assert len(audit.unmatched_citations) >= 1

    def test_fabricated_traffic_sign_triggers_hallucination(
        self, validator: ASTCitationValidator, valid_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that non-existent sign P.999 is detected as ungrounded."""
        advisory = "Người tham gia giao thông không chấp hành biển báo số P.999 sẽ bị xử phạt."
        audit: AntiHallucinationAudit = validator.validate(advisory, valid_chunks)

        assert audit.is_grounded is False
        assert audit.hallucination_score > 0.0
        assert any("P.999" in c for c in audit.unmatched_citations)

    def test_fabricated_road_marking_triggers_hallucination(
        self, validator: ASTCitationValidator, valid_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that non-existent marking 99.99 is detected as ungrounded."""
        advisory = "Hành vi đè vạch kẻ đường số 99.99 bị xử phạt theo quy định."
        audit: AntiHallucinationAudit = validator.validate(advisory, valid_chunks)

        assert audit.is_grounded is False
        assert audit.hallucination_score > 0.0
        assert any("99.99" in c for c in audit.unmatched_citations)

    def test_valid_citations_with_diacritics_and_case_variations(
        self, validator: ASTCitationValidator, valid_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that valid citations match across casing and diacritic formats."""
        test_advisories = [
            # Standard lowercase
            "Căn cứ điểm a khoản 3 điều 5 Nghị định 100/2019/NĐ-CP phạt từ 800.000 đến 1.000.000đ.",
            # Uppercase
            "CĂN CỨ ĐIỀU 5 KHOẢN 3 ĐIỂM A NGHỊ ĐỊNH 100/2019/NĐ-CP.",
            # Article first
            "Áp dụng Điều 5 Khoản 3 Điểm a Nghị định 100/2019/NĐ-CP và Điều 4 QCVN 41:2019/BGTVT.",
            # Referenced sign in QCVN
            "Tuân thủ biển báo P.102 theo quy định tại Điều 4 QCVN 41:2019/BGTVT.",
        ]
        for adv in test_advisories:
            audit = validator.validate(adv, valid_chunks)
            assert audit.is_grounded is True, f"Failed on advisory: {adv} with unmatched: {audit.unmatched_citations}"
            assert audit.hallucination_score == 0.0
            assert audit.citation_coverage_pct == 100.0

    def test_mixed_valid_and_fabricated_citations_computes_partial_score(
        self, validator: ASTCitationValidator, valid_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that 1 valid citation + 1 fabricated citation yields exactly 50% score."""
        advisory = (
            "Căn cứ Điều 5 Khoản 3 Điểm a Nghị định 100/2019/NĐ-CP (hợp lệ) "
            "và Điều 999 Nghị định 100/2019/NĐ-CP (bịa đặt)."
        )
        audit = validator.validate(advisory, valid_chunks)

        assert audit.is_grounded is False
        assert audit.hallucination_score == pytest.approx(0.5, 0.05)
        assert audit.citation_coverage_pct == pytest.approx(50.0, 5.0)
        assert len(audit.unmatched_citations) == 1
        assert "999" in audit.unmatched_citations[0]

    def test_empty_advisory_text_behavior(
        self, validator: ASTCitationValidator, valid_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that empty text with valid chunks does not crash and returns grounded."""
        audit = validator.validate("", valid_chunks)
        assert audit.is_grounded is True
        assert audit.hallucination_score == 0.0
        assert audit.citation_coverage_pct == 100.0
        assert audit.unmatched_citations == []

    def test_empty_retrieved_chunks_behavior(
        self, validator: ASTCitationValidator
    ) -> None:
        """Asserts that cited advisory with zero retrieved chunks is 100% ungrounded."""
        advisory = "Căn cứ Điều 5 Nghị định 100/2019/NĐ-CP."
        audit = validator.validate(advisory, [])
        assert audit.is_grounded is False
        assert audit.hallucination_score == 1.0
        assert audit.citation_coverage_pct == 0.0
        assert len(audit.unmatched_citations) >= 1

    def test_empty_text_and_empty_chunks_behavior(
        self, validator: ASTCitationValidator
    ) -> None:
        """Asserts that empty text and empty chunks cleanly returns ungrounded with 0 hallucination."""
        audit = validator.validate("", [])
        assert audit.is_grounded is False
        assert audit.hallucination_score == 0.0
        assert audit.unmatched_citations == []

    def test_parsed_statutory_citation_canonical_key(self) -> None:
        """Verifies canonical key synthesis for all citation dimensions."""
        c1 = ParsedStatutoryCitation(
            raw_text="Điều 5 Khoản 3 Điểm a",
            doc_code="100/2019/NĐ-CP",
            article_num="5",
            clause_num="3",
            point_letter="a",
        )
        assert "doc_100_2019_nđ_cp" in c1.canonical_key
        assert "a5" in c1.canonical_key
        assert "c3" in c1.canonical_key
        assert "p_a" in c1.canonical_key


# ==============================================================================
# 2. ChainOfCustodyVerifier Cryptographic & Tamper Detection Tests
# ==============================================================================


class TestAdversarialChainOfCustodyVerifier:
    """Stress tests cryptographic Merkle chaining and tamper detection."""

    @pytest.fixture
    def generator(self) -> ChainOfCustodyGenerator:
        return ChainOfCustodyGenerator()

    @pytest.fixture
    def multi_step_chunks(self) -> list[dict[str, Any]]:
        return [
            {
                "chunk_id": "chk_nd100_a5_c3_pa",
                "doc_code": "100/2019/ND-CP",
                "path": "doc_nd100_2019.a5.c3.p_a",
                "raw_text": "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với ô tô vượt đèn đỏ",
                "rrf_score": 0.95,
            },
            {
                "chunk_id": "chk_nd100_a5_c11_pb",
                "doc_code": "100/2019/ND-CP",
                "path": "doc_nd100_2019.a5.c11.p_b",
                "raw_text": "Tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng",
                "rrf_score": 0.88,
            },
            {
                "chunk_id": "chk_qcvn41_a4",
                "doc_code": "QCVN 41:2019/BGTVT",
                "path": "doc_qcvn41_2019.a4",
                "raw_text": "Điều 4. Thứ tự hiệu lực của hệ thống báo hiệu đường bộ",
                "rrf_score": 0.80,
            },
        ]

    def test_clean_chain_verifies_successfully(
        self, generator: ChainOfCustodyGenerator, multi_step_chunks: list[dict[str, Any]]
    ) -> None:
        """Verifies that an untouched CoC package passes all verifier checks."""
        query = "Ô tô vượt đèn đỏ phạt bao nhiêu tiền và bị tước bằng mấy tháng?"
        advisory = (
            "Căn cứ Điều 5 Khoản 3 Điểm a và Điều 5 Khoản 11 Điểm b Nghị định 100/2019/NĐ-CP, "
            "Điều 4 QCVN 41:2019/BGTVT."
        )
        coc: ChainOfCustody = generator.generate(query, multi_step_chunks, advisory)

        assert ChainOfCustodyVerifier.verify_hash_chain(coc, query) is True
        assert ChainOfCustodyVerifier.verify_evidence_digests(coc) is True
        assert coc.anti_hallucination_audit.is_grounded is True

    def test_tampered_query_string_fails_verification(
        self, generator: ChainOfCustodyGenerator, multi_step_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that verifying against a tampered query string fails."""
        query = "Ô tô vượt đèn đỏ phạt bao nhiêu?"
        coc = generator.generate(query, multi_step_chunks, "Điều 5 Nghị định 100/2019/NĐ-CP")

        assert ChainOfCustodyVerifier.verify_hash_chain(coc, "Xe máy vượt đèn đỏ phạt bao nhiêu?") is False

    def test_tampered_query_fingerprint_fails_verification(
        self, generator: ChainOfCustodyGenerator, multi_step_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that modifying the query fingerprint fails verification."""
        query = "Ô tô vượt đèn đỏ phạt bao nhiêu?"
        coc = generator.generate(query, multi_step_chunks, "Điều 5 Nghị định 100/2019/NĐ-CP")

        # Mutate query_fingerprint_sha256
        data = coc.model_dump()
        data["query_fingerprint_sha256"] = "0" * 64
        tampered_coc = ChainOfCustody(**data)

        assert ChainOfCustodyVerifier.verify_hash_chain(tampered_coc, query) is False

    def test_tampered_step_node_hash_fails_verification(
        self, generator: ChainOfCustodyGenerator, multi_step_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that mutating any intermediate step hash invalidates the Merkle chain."""
        query = "Ô tô vượt đèn đỏ phạt bao nhiêu?"
        coc = generator.generate(query, multi_step_chunks, "Điều 5 Nghị định 100/2019/NĐ-CP")

        # Mutate step 2 hash
        data = coc.model_dump()
        data["retrieval_steps"][1]["node_sha256"] = "f" * 64
        tampered_coc = ChainOfCustody(**data)

        assert ChainOfCustodyVerifier.verify_hash_chain(tampered_coc, query) is False

    def test_tampered_step_exact_text_fails_hash_chain_and_evidence_digests(
        self, generator: ChainOfCustodyGenerator, multi_step_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that altering verbatim text payload breaks both hash chain and evidence digest."""
        query = "Ô tô vượt đèn đỏ phạt bao nhiêu?"
        coc = generator.generate(query, multi_step_chunks, "Điều 5 Nghị định 100/2019/NĐ-CP")

        data = coc.model_dump()
        # Subtly alter fine amount text in step 1
        data["retrieval_steps"][0]["exact_statutory_text"] = "Phạt tiền từ 10.000.000 đồng đến 20.000.000 đồng"
        tampered_coc = ChainOfCustody(**data)

        # Hash chain detects discrepancy between step_payload hash and recorded node_sha256
        assert ChainOfCustodyVerifier.verify_hash_chain(tampered_coc, query) is False
        # Evidence digest detects discrepancy between recorded digest and modified text
        assert ChainOfCustodyVerifier.verify_evidence_digests(tampered_coc) is False

    def test_tampered_step_target_node_id_fails_verification(
        self, generator: ChainOfCustodyGenerator, multi_step_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that modifying target_node_id invalidates the step payload hash."""
        query = "Ô tô vượt đèn đỏ phạt bao nhiêu?"
        coc = generator.generate(query, multi_step_chunks, "Điều 5 Nghị định 100/2019/NĐ-CP")

        data = coc.model_dump()
        data["retrieval_steps"][0]["target_node_id"] = "chk_forged_id"
        tampered_coc = ChainOfCustody(**data)

        assert ChainOfCustodyVerifier.verify_hash_chain(tampered_coc, query) is False

    def test_reordered_retrieval_steps_fails_verification(
        self, generator: ChainOfCustodyGenerator, multi_step_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that swapping step order breaks Merkle state chaining."""
        query = "Ô tô vượt đèn đỏ phạt bao nhiêu?"
        coc = generator.generate(query, multi_step_chunks, "Điều 5 Nghị định 100/2019/NĐ-CP")

        data = coc.model_dump()
        # Swap step 1 and step 2
        data["retrieval_steps"][0], data["retrieval_steps"][1] = (
            data["retrieval_steps"][1],
            data["retrieval_steps"][0],
        )
        tampered_coc = ChainOfCustody(**data)

        assert ChainOfCustodyVerifier.verify_hash_chain(tampered_coc, query) is False

    def test_omitted_step_fails_verification(
        self, generator: ChainOfCustodyGenerator, multi_step_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that deleting a step from the middle causes next step hash check to fail."""
        query = "Ô tô vượt đèn đỏ phạt bao nhiêu?"
        coc = generator.generate(query, multi_step_chunks, "Điều 5 Nghị định 100/2019/NĐ-CP")

        data = coc.model_dump()
        # Delete step 2
        del data["retrieval_steps"][1]
        tampered_coc = ChainOfCustody(**data)

        assert ChainOfCustodyVerifier.verify_hash_chain(tampered_coc, query) is False

    def test_tampered_evidence_chunk_hash_fails_digest_check(
        self, generator: ChainOfCustodyGenerator, multi_step_chunks: list[dict[str, Any]]
    ) -> None:
        """Asserts that modifying an evidence digest hash is caught by verify_evidence_digests."""
        query = "Ô tô vượt đèn đỏ phạt bao nhiêu?"
        coc = generator.generate(query, multi_step_chunks, "Điều 5 Nghị định 100/2019/NĐ-CP")

        data = coc.model_dump()
        data["evidence_hashes"][0]["sha256_digest"] = "e" * 64
        tampered_coc = ChainOfCustody(**data)

        assert ChainOfCustodyVerifier.verify_evidence_digests(tampered_coc) is False

    def test_canonical_json_and_fingerprint_sensitivity(
        self, generator: ChainOfCustodyGenerator, multi_step_chunks: list[dict[str, Any]]
    ) -> None:
        """Verifies RFC 8785 canonical serialization and master SHA-256 fingerprint."""
        query = "Ô tô vượt đèn đỏ phạt bao nhiêu?"
        coc = generator.generate(query, multi_step_chunks, "Điều 5 Nghị định 100/2019/NĐ-CP")

        canon1 = ChainOfCustodyVerifier.to_canonical_json(coc)
        fp1 = ChainOfCustodyVerifier.calculate_coc_fingerprint(coc)

        assert isinstance(canon1, str)
        assert len(fp1) == 64

        # Deterministic: computing again gives exact same fingerprint
        assert ChainOfCustodyVerifier.calculate_coc_fingerprint(coc) == fp1

        # Changing session_id modifies the master fingerprint
        data = coc.model_dump()
        data["session_id"] = "different_session_999"
        coc2 = ChainOfCustody(**data)
        fp2 = ChainOfCustodyVerifier.calculate_coc_fingerprint(coc2)

        assert fp1 != fp2


# ==============================================================================
# 3. ScopeOverrideEngine Precedence Algebra Adversarial Tests
# ==============================================================================


class TestAdversarialScopeOverrideEngine:
    """Stress tests 6-tier precedence ordering, emergency vehicle privilege, and boundaries."""

    @pytest.fixture
    def engine(self) -> ScopeOverrideEngine:
        return ScopeOverrideEngine()

    def test_strict_six_tier_precedence_inequality(self, engine: ScopeOverrideEngine) -> None:
        """Asserts strict ranking: Police (1.0) < Light (2.0) < TempSign (3.1) < PermSign (3.2) < Marking (4.0) < General (5.0)."""
        r_police = engine.get_statutory_rank(SignalTier.POLICE_OFFICER)
        r_light = engine.get_statutory_rank(SignalTier.TRAFFIC_LIGHT)
        r_temp = engine.get_statutory_rank(SignalTier.TRAFFIC_SIGN, Temporality.TEMPORARY)
        r_perm = engine.get_statutory_rank(SignalTier.TRAFFIC_SIGN, Temporality.PERMANENT)
        r_marking = engine.get_statutory_rank(SignalTier.ROAD_MARKING)
        r_general = StatutoryPrecedenceRank.GENERAL_RULE.value

        assert r_police == StatutoryPrecedenceRank.TRAFFIC_POLICE.value == 1.0
        assert r_light == StatutoryPrecedenceRank.TRAFFIC_LIGHT.value == 2.0
        assert r_temp == StatutoryPrecedenceRank.ROAD_SIGN_TEMPORARY.value == 3.1
        assert r_perm == StatutoryPrecedenceRank.ROAD_SIGN_PERMANENT.value == 3.2
        assert r_marking == StatutoryPrecedenceRank.ROAD_MARKING.value == 4.0
        assert r_general == 5.0

        assert r_police < r_light < r_temp < r_perm < r_marking < r_general

    def test_emergency_vehicle_five_subtier_hierarchy(self, engine: ScopeOverrideEngine) -> None:
        """Asserts Law 2008 Art 22 emergency vehicle ranking."""
        # 1. Fire (1.1) vs Military/Police (1.2)
        res1 = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.FIRE_FIGHTING, EmergencyVehicleTier.MILITARY_POLICE
        )
        assert res1["dominant_vehicle"] == "Vehicle A"
        assert res1["dominant_tier"] == "FIRE_FIGHTING"

        # 2. Military/Police (1.2) vs Ambulance (1.3)
        res2 = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.MILITARY_POLICE, EmergencyVehicleTier.AMBULANCE
        )
        assert res2["dominant_vehicle"] == "Vehicle A"
        assert res2["dominant_tier"] == "MILITARY_POLICE"

        # 3. Ambulance (1.3) vs Dike (1.4)
        res3 = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.AMBULANCE, EmergencyVehicleTier.DIKE_DISASTER_RELIEF
        )
        assert res3["dominant_vehicle"] == "Vehicle A"
        assert res3["dominant_tier"] == "AMBULANCE"

        # 4. Dike (1.4) vs Funeral (1.5)
        res4 = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.DIKE_DISASTER_RELIEF, EmergencyVehicleTier.FUNERAL_CORTEGE
        )
        assert res4["dominant_vehicle"] == "Vehicle A"
        assert res4["dominant_tier"] == "DIKE_DISASTER_RELIEF"

        # 5. Reverse comparison: Funeral vs Fire
        res5 = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.FUNERAL_CORTEGE, EmergencyVehicleTier.FIRE_FIGHTING
        )
        assert res5["dominant_vehicle"] == "Vehicle B"
        assert res5["dominant_tier"] == "FIRE_FIGHTING"

        # 6. Equal Priority Collision
        res_eq = engine.resolve_emergency_vehicle_conflict(
            EmergencyVehicleTier.AMBULANCE, EmergencyVehicleTier.AMBULANCE
        )
        assert res_eq["dominant_vehicle"] == "EQUAL_PRIORITY"

    def test_emergency_vehicle_exemption_conditions(self, engine: ScopeOverrideEngine) -> None:
        """Asserts that exemption requires PRIORITY_VEHICLE + on_duty + siren_beacon."""
        # Valid on-duty ambulance
        res_valid = engine.evaluate_emergency_privilege(
            vehicle_type=VehicleCategory.PRIORITY_VEHICLE,
            is_on_duty=True,
            has_siren_beacon=True,
            emergency_tier=EmergencyVehicleTier.AMBULANCE,
        )
        assert res_valid["is_exempt"] is True

        # Priority vehicle but off-duty -> NO exemption
        res_off_duty = engine.evaluate_emergency_privilege(
            vehicle_type=VehicleCategory.PRIORITY_VEHICLE,
            is_on_duty=False,
            has_siren_beacon=True,
            emergency_tier=EmergencyVehicleTier.AMBULANCE,
        )
        assert res_off_duty["is_exempt"] is False

        # Priority vehicle on-duty but no siren/beacon -> NO exemption
        res_no_siren = engine.evaluate_emergency_privilege(
            vehicle_type=VehicleCategory.PRIORITY_VEHICLE,
            is_on_duty=True,
            has_siren_beacon=False,
            emergency_tier=EmergencyVehicleTier.AMBULANCE,
        )
        assert res_no_siren["is_exempt"] is False

    def test_empty_signals_raises_value_error(self, engine: ScopeOverrideEngine) -> None:
        """Asserts that resolving empty signals list raises ValueError."""
        with pytest.raises(ValueError, match="at least one active signal"):
            engine.resolve_signal_conflict([])


# ==============================================================================
# 4. QueryPlanner Intent Classification & Slot Extraction Adversarial Tests
# ==============================================================================


class TestAdversarialQueryPlanner:
    """Stress tests query intent classification and entity slot extraction under edge cases."""

    @pytest.fixture
    def planner(self) -> QueryPlanner:
        return QueryPlanner()

    def test_planner_boundary_numeric_extractions(self, planner: QueryPlanner) -> None:
        """Verifies unit conversions and fractional parsing for speeds, BAC, BrAC, and weights."""
        # 1. Decimal speed
        p1 = planner.plan("Xe con chạy 75.5 km/h trong khu dân cư tốc độ tối đa 50 km/h")
        assert p1.extracted_entities.recorded_speed_kmh == 75.5
        assert p1.extracted_entities.speed_limit_kmh == 50.0

        # 2. BrAC and BAC fractions
        p2 = planner.plan("Tài xế ô tô có nồng độ cồn 0.35 mg/l khí thở và 65.5 mg/100ml máu")
        assert p2.extracted_entities.alcohol_breath_mg_l == 0.35
        assert p2.extracted_entities.alcohol_blood_mg_100ml == 65.5

        # 3. Weight conversion from kg to tons
        p3 = planner.plan("Xe tải 3500 kg chở hàng quá tải")
        assert p3.extracted_entities.vehicle_weight_tons == 3.5

    def test_planner_short_query_fallback_prompt(self, planner: QueryPlanner) -> None:
        """Verifies fallback clarification prompt on single-word ambiguous query."""
        plan = planner.plan("Phạt")
        assert plan.fallback_clarification_prompt is not None
        assert "quá ngắn" in plan.fallback_clarification_prompt
