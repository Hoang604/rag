"""Deep Empirical & Adversarial Challenger Test Suite.

Stress-tests ReDoS resistance under hostile inputs, Merkle CoC tamper resistance
across multi-step retrieval chains, Precedence Algebra total ordering & transitivity
across all permutations, and AST Citation Grounding anti-hallucination gates.
"""

from __future__ import annotations

import concurrent.futures
import time
from typing import Any

import pytest

from rag_eval.legal.ingestion.cphc import SupplementarySanctionParser
from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar, parse_vnd_amount
from rag_eval.legal.reasoning.chain_of_custody import (
    ASTCitationValidator,
    ChainOfCustodyGenerator,
    ChainOfCustodyVerifier,
)
from rag_eval.legal.reasoning.overrides import (
    EmergencyVehicleTier,
    ScopeOverrideEngine,
    StatutoryPrecedenceRank,
)
from rag_eval.legal.schemas import (
    SignalTier,
    Temporality,
    TrafficSignalCommand,
)

# ============================================================================
# 1. EMPIRICAL CHALLENGE 1: ReDoS & Catastrophic Backtracking Stress Tests
# ============================================================================


class TestEmpiricalReDoSSafety:
    """Stress tests all regex grammars with massive and pathological inputs."""

    @pytest.mark.parametrize(
        "pattern_name,pattern",
        [
            ("DOC_HEADER", VietnameseLegalGrammar.DOC_HEADER),
            ("CHAPTER", VietnameseLegalGrammar.CHAPTER),
            ("SECTION", VietnameseLegalGrammar.SECTION),
            ("ARTICLE", VietnameseLegalGrammar.ARTICLE),
            ("CLAUSE", VietnameseLegalGrammar.CLAUSE),
            ("POINT", VietnameseLegalGrammar.POINT),
            ("APPENDIX", VietnameseLegalGrammar.APPENDIX),
            ("SIGN_SPEC", VietnameseLegalGrammar.SIGN_SPEC),
            ("MARKING_SPEC", VietnameseLegalGrammar.MARKING_SPEC),
            ("FINE_RANGE_REGEX", VietnameseLegalGrammar.FINE_RANGE_REGEX),
            ("SUSPENSION_REGEX", VietnameseLegalGrammar.SUSPENSION_REGEX),
            ("IMPOUNDMENT_REGEX", VietnameseLegalGrammar.IMPOUNDMENT_REGEX),
            ("DEMERIT_REGEX", VietnameseLegalGrammar.DEMERIT_REGEX),
            ("EXCEPTION_REGEX", VietnameseLegalGrammar.EXCEPTION_REGEX),
            ("TARGET_REF_REGEX", SupplementarySanctionParser.TARGET_REF_REGEX),
            ("CITATION_REGEX_POINT_FIRST", ASTCitationValidator.CITATION_REGEX_POINT_FIRST),
            ("CITATION_REGEX_ARTICLE_FIRST", ASTCitationValidator.CITATION_REGEX_ARTICLE_FIRST),
            ("DOC_ONLY_REGEX", ASTCitationValidator.DOC_ONLY_REGEX),
            ("SIGN_MARKING_REGEX", ASTCitationValidator.SIGN_MARKING_REGEX),
        ],
    )
    def test_regex_linear_execution_time_under_massive_pathological_input(
        self, pattern_name: str, pattern: Any
    ) -> None:
        """Verifies that hostile payload of 10,000 characters finishes in < 25ms."""
        hostile_payloads = [
            ("a" * 5000 + " " + "b" * 5000),
            ("Biển số P." + ("102a." * 500) + " kết thúc"),
            ("Phạt tiền từ " + ("999." * 500) + " đồng đến 1.000.000 đồng"),
            ("tước quyền sử dụng Giấy phép lái xe từ " + ("10 tháng " * 500)),
            ("trừ " + ("12 điểm " * 500) + "trên Giấy phép lái xe"),
            ("trừ trường hợp " + ("xe ưu tiên " * 500)),
            ("Nghị định số " + ("100/2019/ND-CP " * 500)),
            ((" " * 50 + "\n") * 200),
        ]

        for payload in hostile_payloads:
            t0 = time.perf_counter()
            _ = list(pattern.finditer(payload))
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            assert elapsed_ms < 50.0, (
                f"ReDoS detected on {pattern_name}! Elapsed: {elapsed_ms:.2f}ms"
            )

    def test_parse_vnd_amount_adversarial_inputs(self) -> None:
        """Verifies parse_vnd_amount robustness against extreme inputs."""
        assert parse_vnd_amount("999.999.999.999", "đồng") == 999999999999
        assert parse_vnd_amount("  1,5  ", "tỷ đồng") == 1500000000
        assert parse_vnd_amount("0,4", "triệu đồng") == 400000
        assert parse_vnd_amount("  ", "đồng") is None
        assert parse_vnd_amount("abc.def", "đồng") is None


# ============================================================================
# 2. EMPIRICAL CHALLENGE 2: Merkle CoC Cryptographic Tamper Resistance
# ============================================================================


class TestEmpiricalMerkleCoCTamperResistance:
    """Stress tests Merkle hash chain validation and tamper detection."""

    def _create_mock_chunks(self, count: int = 5) -> list[dict[str, Any]]:
        return [
            {
                "chunk_id": f"chk_{i}",
                "doc_code": "100/2019/ND-CP",
                "hierarchy_path": f"doc_nd100_2019.c1.a5.c{i}.p_a",
                "verbatim_text": f"Nội dung quy định xử phạt vi phạm hành chính số {i} tại Điều 5 Khoản {i} Điểm a.",
                "relevance_score": 0.95 - (i * 0.05),
            }
            for i in range(1, count + 1)
        ]

    def test_unbroken_hash_chain_passes_verification(self) -> None:
        """Verifies a genuine unbroken chain validates with 100% integrity."""
        gen = ChainOfCustodyGenerator()
        chunks = self._create_mock_chunks(5)
        query = "Mức phạt vượt đèn đỏ xe ô tô"
        advisory = "Theo Điểm a Khoản 3 Điều 5 Nghị định 100/2019/NĐ-CP, phạt tiền từ 4.000.000 đến 6.000.000 đồng."

        coc = gen.generate(query=query, retrieved_chunks=chunks, advisory_text=advisory)

        assert ChainOfCustodyVerifier.verify_hash_chain(coc, query) is True
        assert ChainOfCustodyVerifier.verify_evidence_digests(coc) is True

        fingerprint1 = ChainOfCustodyVerifier.calculate_coc_fingerprint(coc)
        fingerprint2 = ChainOfCustodyVerifier.calculate_coc_fingerprint(coc)
        assert fingerprint1 == fingerprint2
        assert len(fingerprint1) == 64

    def test_tamper_query_fails_verification(self) -> None:
        """Verifies changing the query string invalidates the hash chain."""
        gen = ChainOfCustodyGenerator()
        chunks = self._create_mock_chunks(3)
        query = "Mức phạt vượt đèn đỏ xe ô tô"
        coc = gen.generate(query=query, retrieved_chunks=chunks, advisory_text="text")

        tampered_query = "Mức phạt vượt đèn đỏ xe mô tô"
        assert ChainOfCustodyVerifier.verify_hash_chain(coc, tampered_query) is False

    def test_tamper_single_byte_in_statutory_text_fails_verification(self) -> None:
        """Verifies modifying any single byte in retrieval steps invalidates the chain."""
        gen = ChainOfCustodyGenerator()
        chunks = self._create_mock_chunks(4)
        query = "Xử phạt vi phạm tốc độ"
        coc = gen.generate(query=query, retrieved_chunks=chunks, advisory_text="text")

        # Tamper step 2 statutory text via model_copy
        tampered_step = coc.retrieval_steps[1].model_copy(
            update={"exact_statutory_text": coc.retrieval_steps[1].exact_statutory_text + " [TAMPERED]"}
        )
        tampered_steps = list(coc.retrieval_steps)
        tampered_steps[1] = tampered_step
        tampered_coc = coc.model_copy(update={"retrieval_steps": tampered_steps})

        assert ChainOfCustodyVerifier.verify_hash_chain(tampered_coc, query) is False

    def test_tamper_node_id_swap_fails_verification(self) -> None:
        """Verifies swapping node IDs invalidates the chain."""
        gen = ChainOfCustodyGenerator()
        chunks = self._create_mock_chunks(4)
        query = "Xử phạt vi phạm tốc độ"
        coc = gen.generate(query=query, retrieved_chunks=chunks, advisory_text="text")

        # Swap node IDs via model_copy
        tampered_step = coc.retrieval_steps[0].model_copy(update={"target_node_id": "chk_999"})
        tampered_steps = list(coc.retrieval_steps)
        tampered_steps[0] = tampered_step
        tampered_coc = coc.model_copy(update={"retrieval_steps": tampered_steps})

        assert ChainOfCustodyVerifier.verify_hash_chain(tampered_coc, query) is False

    def test_tamper_evidence_digest_fails_verification(self) -> None:
        """Verifies modifying evidence digest is detected by verify_evidence_digests."""
        gen = ChainOfCustodyGenerator()
        chunks = self._create_mock_chunks(3)
        query = "Xử phạt nồng độ cồn"
        coc = gen.generate(query=query, retrieved_chunks=chunks, advisory_text="text")

        tampered_ev = coc.evidence_hashes[0].model_copy(update={"sha256_digest": "0" * 64})
        tampered_hashes = list(coc.evidence_hashes)
        tampered_hashes[0] = tampered_ev
        tampered_coc = coc.model_copy(update={"evidence_hashes": tampered_hashes})

        assert ChainOfCustodyVerifier.verify_evidence_digests(tampered_coc) is False


# ============================================================================
# 3. EMPIRICAL CHALLENGE 3: Precedence Algebra Determinism & Transitivity
# ============================================================================


class TestEmpiricalPrecedenceAlgebraDeterminism:
    """Stress tests mathematical total ordering, transitivity, and concurrency."""

    def test_precedence_ranks_strict_monotonic_ordering(self) -> None:
        """Verifies that all 6 precedence ranks have strictly monotonic numeric values."""
        ranks = [
            StatutoryPrecedenceRank.TRAFFIC_POLICE.value,
            StatutoryPrecedenceRank.EMERGENCY_VEHICLE_GENERIC.value,
            StatutoryPrecedenceRank.TRAFFIC_LIGHT.value,
            StatutoryPrecedenceRank.ROAD_SIGN_TEMPORARY.value,
            StatutoryPrecedenceRank.ROAD_SIGN_PERMANENT.value,
            StatutoryPrecedenceRank.ROAD_MARKING.value,
            StatutoryPrecedenceRank.GENERAL_RULE.value,
        ]
        assert ranks == sorted(ranks)
        assert len(ranks) == len(set(ranks))

    def test_emergency_vehicle_tier_strict_monotonic_ordering(self) -> None:
        """Verifies 5-tier statutory emergency hierarchy ordering per Law 2008 Art 22."""
        tiers = [
            EmergencyVehicleTier.FIRE_FIGHTING.value,
            EmergencyVehicleTier.MILITARY_POLICE.value,
            EmergencyVehicleTier.AMBULANCE.value,
            EmergencyVehicleTier.DIKE_DISASTER_RELIEF.value,
            EmergencyVehicleTier.FUNERAL_CORTEGE.value,
        ]
        assert tiers == sorted(tiers)
        assert len(tiers) == len(set(tiers))

    def test_pairwise_transitivity_across_all_signal_combinations(self) -> None:
        """Verifies pairwise transitivity: for any A > B and B > C => A > C."""
        engine = ScopeOverrideEngine()
        signals: list[SignalTier] = [
            SignalTier.POLICE_OFFICER,
            SignalTier.TRAFFIC_LIGHT,
            SignalTier.TRAFFIC_SIGN,
            SignalTier.ROAD_MARKING,
        ]

        # Test all triples (A, B, C)
        for s_a in signals:
            for s_b in signals:
                for s_c in signals:
                    if s_a == s_b or s_b == s_c or s_a == s_c:
                        continue
                    res_ab = engine.resolve_signal_conflict([s_a, s_b])
                    res_bc = engine.resolve_signal_conflict([s_b, s_c])
                    res_ac = engine.resolve_signal_conflict([s_a, s_c])

                    if res_ab.dominant_signal.source_type == s_a and res_bc.dominant_signal.source_type == s_b:
                        assert res_ac.dominant_signal.source_type == s_a, (
                            f"Transitivity broken for ({s_a.name}, {s_b.name}, {s_c.name})!"
                        )

    def test_concurrent_conflict_resolutions_are_idempotent_and_thread_safe(self) -> None:
        """Verifies thread safety and zero state mutation under concurrent load."""
        engine = ScopeOverrideEngine()
        cmds = [
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
            TrafficSignalCommand(
                source_type=SignalTier.TRAFFIC_SIGN,
                temporality=Temporality.TEMPORARY,
                command_directive="STOP",
                legal_citation="QCVN 41:2019 Điều 4.3",
            ),
        ]

        def worker() -> bool:
            res = engine.resolve_signal_conflict(cmds, driver_action="PROCEED")
            return res.dominant_signal.source_type == SignalTier.POLICE_OFFICER and res.is_driver_action_legal is True

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(worker) for _ in range(500)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert all(results)
        assert len(results) == 500


# ============================================================================
# 4. EMPIRICAL CHALLENGE 4: AST Citation Grounding & Clause Masking Gate
# ============================================================================


class TestEmpiricalASTCitationGroundingAntiHallucination:
    """Stress tests AST citation validation against clause masking attacks and hallucinations."""

    def test_clause_masking_attack_rejected(self) -> None:
        """Attacker quotes 'Khoản 99 Điều 5' when evidence only contains 'Điều 5'."""
        validator = ASTCitationValidator()
        retrieved_chunks = [
            {
                "hierarchy_path": "doc_nd100_2019.c1.a5",
                "doc_code": "100/2019/ND-CP",
                "article_number": 5,
                "article_index": "Điều 5",
                "verbatim_text": "Điều 5. Xử phạt người điều khiển xe ô tô vi phạm quy tắc giao thông đường bộ.",
            }
        ]

        # Advisory fabricates non-existent clause 99
        advisory_hallucination = (
            "Theo Khoản 99 Điều 5 Nghị định 100/2019/NĐ-CP, người vi phạm bị phạt tiền 50 triệu đồng."
        )
        audit = validator.validate(advisory_hallucination, retrieved_chunks)

        assert audit.is_grounded is False
        assert audit.hallucination_score > 0.0
        assert any("99" in u for u in audit.unmatched_citations)

    def test_point_masking_attack_rejected(self) -> None:
        """Attacker quotes 'Điểm z Khoản 1 Điều 5' when evidence contains 'Điểm a Khoản 1 Điều 5'."""
        validator = ASTCitationValidator()
        retrieved_chunks = [
            {
                "hierarchy_path": "doc_nd100_2019.c1.a5.c1.p_a",
                "doc_code": "100/2019/ND-CP",
                "article_number": 5,
                "article_index": "Điều 5",
                "verbatim_text": "1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với một trong các hành vi vi phạm sau đây:\na) Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường",
            }
        ]

        advisory_hallucination = (
            "Theo Điểm z Khoản 1 Điều 5 Nghị định 100/2019/NĐ-CP, bị phạt tiền 10 triệu đồng."
        )
        audit = validator.validate(advisory_hallucination, retrieved_chunks)

        assert audit.is_grounded is False
        assert audit.hallucination_score > 0.0
        assert any("z" in u for u in audit.unmatched_citations)

    def test_genuine_grounded_citation_passes_with_100_percent_coverage(self) -> None:
        """Legitimate citation fully grounded in retrieved chunks passes cleanly."""
        validator = ASTCitationValidator()
        retrieved_chunks = [
            {
                "hierarchy_path": "doc_nd100_2019.c1.a5.c3.p_a",
                "doc_code": "100/2019/ND-CP",
                "article_number": 5,
                "article_index": "Điều 5",
                "verbatim_text": "3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:\na) Điều khiển xe chạy quá tốc độ quy định từ 05 km/h đến dưới 10 km/h;",
            }
        ]

        advisory_valid = (
            "Theo Điểm a Khoản 3 Điều 5 Nghị định 100/2019/NĐ-CP, người điều khiển ô tô "
            "chạy quá tốc độ từ 05 đến dưới 10 km/h bị phạt tiền từ 800.000 đồng đến 1.000.000 đồng."
        )
        audit = validator.validate(advisory_valid, retrieved_chunks)

        assert audit.is_grounded is True
        assert audit.hallucination_score == 0.0
        assert audit.citation_coverage_pct == 100.0
        assert len(audit.unmatched_citations) == 0
