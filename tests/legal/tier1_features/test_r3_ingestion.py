"""Tier 1: Feature Coverage tests for Requirement 3 (R3) - CPHC Ingestion Pipeline."""

from __future__ import annotations

from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar
from rag_eval.legal.ingestion.graph_linker import DeterministicGraphLinker
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.schemas import GraphRelationType
from tests.legal.fixtures.laws_data import (
    DECREE_100_ART5_CL3_PTA,
    DECREE_100_ART6_CL8_PTA,
)

SAMPLE_TIER1_TEXT = """
NGHỊ ĐỊNH
Số: 100/2019/NĐ-CP
Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ

Chương II
HÀNH VI VI PHẠM, HÌNH THỨC, MỨC XỬ PHẠT VÀ BIỆN PHÁP KHẮC PHỤC HẬU QUẢ

Điều 5. Xử phạt người điều khiển xe ô tô vi phạm quy tắc giao thông
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng:
a) Không chấp hành hiệu lệnh của biển báo;
3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng:
a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;
c) Không tuân thủ hiệu lệnh CSGT theo quy định tại Điều 10 Luật Giao thông đường bộ.
11. Hình thức xử phạt bổ sung:
b) Điểm a khoản 3 bị tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng;
c) Điểm c khoản 3 bị tước quyền sử dụng Giấy phép lái xe từ 02 tháng đến 04 tháng và bị trừ 2 điểm trên Giấy phép lái xe.
"""


class TestR3CPHCIngestion:
    """Validates Context-Preserving Hierarchical Chunking (CPHC), prefix synthesis, and graph linkers."""

    def test_cfqc_inherits_article_and_clause_lead_sentence(self) -> None:
        chunk = DECREE_100_ART5_CL3_PTA
        assert chunk.lead_sentence is not None
        assert "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng" in chunk.lead_sentence
        assert chunk.article_index is not None and "Điều 5" in chunk.article_index
        assert chunk.clause_index is not None and "Khoản 3" in chunk.clause_index
        assert chunk.point_index is not None and "Điểm a" in chunk.point_index

    def test_cfqc_contextualized_text_contains_complete_lineage(self) -> None:
        chunk = DECREE_100_ART5_CL3_PTA
        assert "100/2019/NĐ-CP" in chunk.contextualized_text or "doc_nd100_2019" in chunk.hierarchy_path
        assert "Điều 5" in chunk.contextualized_text
        assert "Khoản 3" in chunk.contextualized_text
        assert "Điểm a" in chunk.contextualized_text
        assert (
            "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông"
            in chunk.contextualized_text
        )

    def test_cfqc_resolves_dangling_subpoint_with_vehicle_context(self) -> None:
        chunk = DECREE_100_ART6_CL8_PTA
        assert chunk.vehicle_types[0].value == "MOTORCYCLE"
        assert "Đi ngược chiều" in chunk.verbatim_text

    def test_cfqc_additional_sanctions_are_linked(self) -> None:
        chunk = DECREE_100_ART6_CL8_PTA
        assert chunk.additional_sanctions.license_suspension_months_min == 2
        assert chunk.additional_sanctions.license_suspension_months_max == 4
        assert chunk.additional_sanctions.demerit_points == 3

    def test_cfqc_temporal_validity_metadata(self) -> None:
        chunk = DECREE_100_ART5_CL3_PTA
        assert chunk.effective_date == "2020-01-15"
        assert chunk.is_active is True

    def test_end_to_end_ast_cphc_graph_pipeline_invariants(self) -> None:
        parser = LegalASTParser(VietnameseLegalGrammar)
        cphc = CPHCEngine(VietnameseLegalGrammar)
        linker = DeterministicGraphLinker(VietnameseLegalGrammar)

        root = parser.parse_document("100/2019/NĐ-CP", SAMPLE_TIER1_TEXT)
        chunks, norms = cphc.process_ast(root)

        # 1. 100% path equality between AST and CPHC
        for chunk in chunks:
            assert chunk.hierarchy_path.startswith("doc_100_2019_nd_cp.c_ii.a5")

        # 2. Supplementary sanction isolation (no bleed)
        chk_cl1_a = next(c for c in chunks if c.clause_number == 1 and c.point_letter == "a")
        assert chk_cl1_a.additional_sanctions.license_suspension_months_min is None

        chk_cl3_a = next(c for c in chunks if c.clause_number == 3 and c.point_letter == "a")
        assert chk_cl3_a.additional_sanctions.license_suspension_months_min == 1
        assert chk_cl3_a.additional_sanctions.license_suspension_months_max == 3

        chk_cl3_c = next(c for c in chunks if c.clause_number == 3 and c.point_letter == "c")
        assert chk_cl3_c.additional_sanctions.license_suspension_months_min == 2
        assert chk_cl3_c.additional_sanctions.license_suspension_months_max == 4
        assert chk_cl3_c.additional_sanctions.demerit_points == 2

        # 3. Knowledge graph edges without self-loops
        edges = linker.extract_edges_from_chunks(chunks=chunks, norms=norms, ast_root=root)
        supp_edges = [e for e in edges if e["relation_type"] == GraphRelationType.HAS_ADDITIONAL_SANCTION.value]
        assert len(supp_edges) >= 2
        for e in supp_edges:
            assert e["source_path"] != e["target_path"]

    def test_stage_4_synthetic_benchmark_generator_three_tiers(self) -> None:
        """Requirement R3 Stage 4: Verifies 3-tier synthetic benchmark generation with gold citation paths."""
        from rag_eval.legal.ingestion.benchmark_gen import SyntheticBenchmarkGenerator
        from rag_eval.legal.schemas import LegalIntent

        parser = LegalASTParser(VietnameseLegalGrammar)
        cphc = CPHCEngine(VietnameseLegalGrammar)
        linker = DeterministicGraphLinker(VietnameseLegalGrammar)
        generator = SyntheticBenchmarkGenerator(VietnameseLegalGrammar)

        root = parser.parse_document("100/2019/NĐ-CP", SAMPLE_TIER1_TEXT)
        chunks, norms = cphc.process_ast(root)
        edges = linker.extract_edges_from_chunks(chunks=chunks, norms=norms, ast_root=root)

        benchmark_items = generator.generate_benchmark_suite(chunks=chunks, edges=edges)

        assert len(benchmark_items) > 0

        # Verify Tier 1: Single-hop factual queries
        tier1_items = [b for b in benchmark_items if b.tier == 1]
        assert len(tier1_items) >= 2
        for item in tier1_items:
            assert item.intent == LegalIntent.INTENT_PENALTY_LOOKUP
            assert len(item.gold_citation_paths) == 1
            assert item.gold_citation_paths[0].startswith("doc_100_2019_nd_cp.c_ii.a5")
            assert item.expected_fine_bounds.min_fine_vnd is not None

        # Verify Tier 2: Boundary / Multi-hop technical standard queries
        tier2_items = [b for b in benchmark_items if b.tier == 2]
        assert len(tier2_items) >= 1
        for item in tier2_items:
            assert len(item.gold_citation_paths) >= 1

        # Verify Tier 3: Priority overrides and conflict resolution
        tier3_items = [b for b in benchmark_items if b.tier == 3]
        assert len(tier3_items) >= 1
        police_items = [b for b in tier3_items if b.dominant_authority == "POLICE_OFFICER"]
        assert len(police_items) >= 1
        assert (
            "doc_qcvn_41_2019.a4" in police_items[0].gold_citation_paths
            or "doc_qcvn_41_2019_bgtvt.a4" in police_items[0].gold_citation_paths
        )
        assert police_items[0].is_exempt is True

    def test_canonical_doc_slug_standardization(self) -> None:
        """F-18: Verifies canonical_doc_slug returns standardized slugs across instruments."""
        from rag_eval.legal.schemas import canonical_doc_slug

        assert canonical_doc_slug("QCVN 41:2019/BGTVT") == "doc_qcvn_41_2019"
        assert canonical_doc_slug("QCVN 41:2019") == "doc_qcvn_41_2019"
        assert canonical_doc_slug("QCVN41:2019/BGTVT") == "doc_qcvn_41_2019"
        assert canonical_doc_slug("Luật GTĐB 2008") == "doc_luat_gtdb_2008"
        assert canonical_doc_slug("Luật TTATGTĐB 2024") == "doc_luat_ttatgtdb_2024"
        assert canonical_doc_slug("100/2019/NĐ-CP") == "doc_100_2019_nd_cp"
        assert canonical_doc_slug("123/2021/NĐ-CP") == "doc_123_2021_nd_cp"
        assert canonical_doc_slug("168/2024/NĐ-CP") == "doc_168_2024_nd_cp"
        assert canonical_doc_slug("doc_100_2019_nd_cp") == "doc_100_2019_nd_cp"

    def test_multi_letter_sign_prefix_classification(self) -> None:
        """F-16: Verifies multi-letter regex prefix parser for all QCVN 41:2019 sign classification families."""
        linker = DeterministicGraphLinker(VietnameseLegalGrammar)

        # Test classification families: DP, IE, RE, P, W, R, I, S, M/markings
        assert linker._resolve_qcvn_appendix_tag("DP.135") == "app_b"
        assert linker._resolve_qcvn_appendix_tag("P.102") == "app_b"
        assert linker._resolve_qcvn_appendix_tag("W.201a") == "app_c"
        assert linker._resolve_qcvn_appendix_tag("RE.301") == "app_d"
        assert linker._resolve_qcvn_appendix_tag("R.301a") == "app_d"
        assert linker._resolve_qcvn_appendix_tag("IE.450") == "app_e"
        assert linker._resolve_qcvn_appendix_tag("I.401") == "app_e"
        assert linker._resolve_qcvn_appendix_tag("S.501") == "app_f"
        assert linker._resolve_qcvn_appendix_tag("1.1") == "app_g"
        assert linker._resolve_qcvn_appendix_tag("M.1.1") == "app_g"

    def test_incremental_temporal_ast_diff_engine(self) -> None:
        """F-15: Verifies AST diffing engine updates target base chunks with is_amended=True and MODIFIES_AND_REPLACES edges."""
        from rag_eval.legal.ingestion.pipeline import TemporalASTDiffEngine

        parser = LegalASTParser(VietnameseLegalGrammar)
        cphc = CPHCEngine(VietnameseLegalGrammar)
        linker = DeterministicGraphLinker(VietnameseLegalGrammar)
        diff_engine = TemporalASTDiffEngine(
            grammar=VietnameseLegalGrammar,
            parser=parser,
            cphc=cphc,
            linker=linker,
        )

        root = parser.parse_document("100/2019/NĐ-CP", SAMPLE_TIER1_TEXT)
        base_chunks, _ = cphc.process_ast(root)

        sample_amendment = """
        NGHỊ ĐỊNH
        Số: 123/2021/NĐ-CP
        Sửa đổi, bổ sung một số điều của Nghị định số 100/2019/NĐ-CP

        Điều 2. Sửa đổi, bổ sung một số điều của Nghị định số 100/2019/NĐ-CP
        1. Sửa đổi, bổ sung điểm a khoản 3 Điều 5 như sau:
        a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông; phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng.
        """

        result = diff_engine.diff_and_apply_amendment(
            base_chunks=base_chunks,
            amending_doc_code="123/2021/NĐ-CP",
            amending_raw_text=sample_amendment,
            amending_effective_date="2022-01-01",
        )

        assert len(result.new_chunks) > 0
        assert len(result.amended_chunks) > 0
        # Verify base chunk a5.c3.p_a was marked as amended and inactive
        amended_chk = next(
            c for c in base_chunks if c.clause_number == 3 and c.point_letter == "a"
        )
        assert amended_chk.is_amended is True
        assert amended_chk.is_active is False
        assert amended_chk.expiry_date == "2022-01-01"
        assert amended_chk.amended_by == "123/2021/NĐ-CP"

        # Verify non-modified base chunk remains active and unamended
        non_amended_chk = next(
            c for c in base_chunks if c.clause_number == 1 and c.point_letter == "a"
        )
        assert non_amended_chk.is_amended is False
        assert non_amended_chk.is_active is True

        # Verify MODIFIES_AND_REPLACES edge was created
        mod_edges = [
            e
            for e in result.modifies_edges
            if e["relation_type"]
            == GraphRelationType.MODIFIES_AND_REPLACES.value
        ]
        assert len(mod_edges) > 0

    def test_f28_cleanse_vehicle_defaults_for_pedestrian_and_general_subjects(self) -> None:
        """F-28: Verifies general/pedestrian subjects without vehicle mentions default to empty vehicle list."""
        from rag_eval.legal.schemas import ActorCategory

        parser = LegalASTParser(VietnameseLegalGrammar)
        cphc = CPHCEngine(VietnameseLegalGrammar)

        pedestrian_text = """
        NGHỊ ĐỊNH
        Số: 100/2019/NĐ-CP
        Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ

        Điều 9. Xử phạt người đi bộ vi phạm quy tắc giao thông đường bộ
        1. Phạt tiền từ 60.000 đồng đến 100.000 đồng đối với người đi bộ thực hiện một trong các hành vi vi phạm sau đây:
        a) Không đi đúng phần đường quy định;
        b) Không chấp hành hiệu lệnh hoặc chỉ dẫn của đèn tín hiệu, biển báo hiệu, vạch kẻ đường.
        """

        root = parser.parse_document("100/2019/NĐ-CP", pedestrian_text)
        chunks, _ = cphc.process_ast(root)

        assert len(chunks) == 2
        for chunk in chunks:
            assert chunk.primary_actor == ActorCategory.PEDESTRIAN
            assert chunk.vehicle_types == [], (
                f"F-28 violation: pedestrian chunk injected vehicle defaults: {chunk.vehicle_types}"
            )

        # Direct test on _extract_vehicle_types with general text (no vehicles)
        extracted = cphc._extract_vehicle_types("Hành vi vứt rác ra đường bộ")
        assert extracted == []

        # Direct test with pedestrian actor override
        extracted_ped = cphc._extract_vehicle_types(
            "Người đi bộ vượt rào chắn đường cao tốc", actor=ActorCategory.PEDESTRIAN
        )
        assert extracted_ped == []

    def test_f29_multi_role_norms_in_multi_penalty_clauses(self) -> None:
        """F-29: Verifies multi-penalty clauses preserve both principal and supplementary sanction roles in metadata."""
        from rag_eval.legal.schemas import AdditionalSanctions, FineBounds, NormRole

        cphc = CPHCEngine(VietnameseLegalGrammar)
        parser = LegalASTParser(VietnameseLegalGrammar)

        root = parser.parse_document("100/2019/NĐ-CP", SAMPLE_TIER1_TEXT)
        chunks, _ = cphc.process_ast(root)

        # Khoản 3 Điểm a has fine (800k-1M) AND license suspension (1-3 months)
        chk_cl3_a = next(
            c for c in chunks if c.clause_number == 3 and c.point_letter == "a"
        )
        assert chk_cl3_a.norm_role == NormRole.SANCTION_PRINCIPAL

        # Test _infer_norm_roles directly
        fine_bounds = FineBounds(min_fine_vnd=800000, max_fine_vnd=1000000)
        supp = AdditionalSanctions(
            license_suspension_months_min=1,
            license_suspension_months_max=3,
        )
        roles = cphc._infer_norm_roles(
            node=root.flatten()[0],
            fine_bounds=fine_bounds,
            additional_sanctions=supp,
            text=chk_cl3_a.verbatim_text,
        )
        assert NormRole.SANCTION_PRINCIPAL in roles
        assert NormRole.SANCTION_SUPPLEMENTARY in roles

    def test_f31_strict_hierarchical_path_matching_from_root(self) -> None:
        """F-31: Enforces strict hierarchical path matching from root down to leaf in _resolve_node_id."""
        from rag_eval.legal.ingestion.loader import _resolve_node_id

        node_map = {
            "doc_100_2019_nd_cp.c_i.s1.a1.c1.p_a": "uuid-ch1-art1",
            "doc_100_2019_nd_cp.c_ii.s1.a5.c1.p_a": "uuid-ch2-art5-c1-pa",
            "doc_100_2019_nd_cp.c_ii.s1.a5.c3.p_a": "uuid-ch2-art5-c3-pa",
            "doc_100_2019_nd_cp.c_ii.s1.a5": "uuid-ch2-art5",
            "doc_100_2019_nd_cp": "uuid-root",
        }

        # 1. Exact match
        assert (
            _resolve_node_id(
                "doc_100_2019_nd_cp.c_ii.s1.a5.c3.p_a", node_map
            )
            == "uuid-ch2-art5-c3-pa"
        )

        # 2. Canonical-to-structural hierarchical path matching from root
        assert (
            _resolve_node_id("doc_100_2019_nd_cp.a5.c3.p_a", node_map)
            == "uuid-ch2-art5-c3-pa"
        )
        assert (
            _resolve_node_id("doc_100_2019_nd_cp.a5.c1.p_a", node_map)
            == "uuid-ch2-art5-c1-pa"
        )
        assert (
            _resolve_node_id("doc_100_2019_nd_cp.a5", node_map)
            == "uuid-ch2-art5"
        )

        # 3. Root document match
        assert _resolve_node_id("doc_100_2019_nd_cp", node_map) == "uuid-root"

        # 4. Strict failure on unmapped paths across non-existent articles
        import pytest

        with pytest.raises(
            ValueError, match="Strict AST Foreign Key Error: Path"
        ):
            _resolve_node_id("doc_100_2019_nd_cp.a99.c1", node_map)

        with pytest.raises(
            ValueError, match="Cannot resolve node UUID for empty hierarchy path"
        ):
            _resolve_node_id("", node_map)

    def test_f34_redos_resistant_bounds_in_target_ref_regex(self) -> None:
        """F-34: Verifies TARGET_REF_REGEX has bounded character classes and linear execution on large strings."""
        import time

        from rag_eval.legal.ingestion.cphc import SupplementarySanctionParser

        # 1. Compound repeated "điểm" keyword parsing
        text_repeated = "Thực hiện hành vi quy định tại điểm a, điểm b khoản 3 Điều này bị tước GPLX"
        matches = list(
            SupplementarySanctionParser.TARGET_REF_REGEX.finditer(text_repeated)
        )
        assert len(matches) == 1
        assert matches[0].group("cl") == "3"
        pts = matches[0].group("pts")
        assert pts is not None
        assert "a" in pts and "b" in pts

        # 2. Compound "các điểm a, b và c khoản 5"
        text_compound = "quy định tại các điểm a, b và c khoản 5 Điều này"
        m2 = list(
            SupplementarySanctionParser.TARGET_REF_REGEX.finditer(text_compound)
        )
        assert len(m2) == 1
        assert m2[0].group("cl") == "5"

        # 3. Standalone "khoản 2"
        text_clause = "quy định tại khoản 2 Điều này"
        m3 = list(
            SupplementarySanctionParser.TARGET_REF_REGEX.finditer(text_clause)
        )
        assert len(m3) == 1
        assert m3[0].group("cl") == "2"

        # 4. ReDoS linear performance test on 50KB+ unclosed string
        adversarial_payload = (
            "quy định tại điểm a, b, c nhưng không có khoản " * 1000
        )
        t0 = time.perf_counter()
        _ = list(
            SupplementarySanctionParser.TARGET_REF_REGEX.finditer(
                adversarial_payload
            )
        )
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.01, f"TARGET_REF_REGEX ReDoS: took {elapsed:.5f}s (> 0.01s)"

