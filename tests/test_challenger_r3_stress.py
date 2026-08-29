"""Adversarial stress-testing suite for Milestone R3 Ingestion Pipeline, AST-CPHC Path Alignment & Graph Linker."""

from __future__ import annotations

import re
import time

import pytest

from rag_eval.legal.ingestion.cphc import (
    CPHCEngine,
    SupplementarySanctionParser,
)
from rag_eval.legal.ingestion.grammar import (
    VietnameseLegalGrammar,
    parse_vnd_amount,
)
from rag_eval.legal.ingestion.graph_linker import DeterministicGraphLinker
from rag_eval.legal.ingestion.parser import LegalASTParser
from rag_eval.legal.schemas import (
    GraphRelationType,
    NormRole,
)

# ==============================================================================
# 1. Adversarial Grammar Stress Testing & ReDoS Verification (< 0.01s Execution)
# ==============================================================================


class TestAdversarialGrammarReDoS:
    """Stress-tests VietnameseLegalGrammar regex patterns against catastrophic backtracking triggers."""

    def test_doc_header_redos_resistance_large_string(self) -> None:
        """Verifies DOC_HEADER scans a 50KB+ unclosed/pathological string in < 0.01s."""
        payload = (
            "LUẬT\nSố: 100/2019/NĐ-CP\n"
            + ("Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam\n" * 800)
            + ("A" * 20000)
        )
        assert len(payload.encode("utf-8")) > 50 * 1024

        t0 = time.perf_counter()
        match = VietnameseLegalGrammar.DOC_HEADER.search(payload)
        elapsed = time.perf_counter() - t0

        assert elapsed < 0.01, f"DOC_HEADER ReDoS detected: took {elapsed:.5f}s (> 0.01s)"
        assert match is not None

    def test_clause_point_redos_resistance_unclosed_nesting(self) -> None:
        """Verifies CLAUSE and POINT patterns on 50KB+ unclosed multi-line text execute in < 0.01s."""
        adversarial_lines = [
            f"{i} Không phải khoản nhưng có số ở đầu dòng\n"
            f"  {i}. Thụt lề không khớp regex\n"
            f"Điểm {chr(97 + (i % 26))} nhưng không có dấu đóng ngoặc\n"
            f"đ) dòng điểm hợp lệ với nội dung siêu dài: " + ("từ " * 50) + "\n"
            for i in range(250)
        ]
        payload = "".join(adversarial_lines)
        assert len(payload.encode("utf-8")) > 50 * 1024

        # Test CLAUSE regex
        t0 = time.perf_counter()
        _clause_matches = list(VietnameseLegalGrammar.CLAUSE.finditer(payload))
        elapsed_clause = time.perf_counter() - t0
        assert elapsed_clause < 0.01, f"CLAUSE ReDoS detected: took {elapsed_clause:.5f}s (> 0.01s)"

        # Test POINT regex
        t0 = time.perf_counter()
        point_matches = list(VietnameseLegalGrammar.POINT.finditer(payload))
        elapsed_point = time.perf_counter() - t0
        assert elapsed_point < 0.01, f"POINT ReDoS detected: took {elapsed_point:.5f}s (> 0.01s)"
        assert len(point_matches) > 0

    def test_sign_and_marking_spec_redos_resistance_large_string(self) -> None:
        """Verifies SIGN_SPEC and MARKING_SPEC on 50KB+ adversarial technical text execute in < 0.01s."""
        lines = []
        for i in range(300):
            lines.append(f"Biển số P.{i}: Biển cấm số {i}\n" + ("Nội dung mô tả biển báo chi tiết... " * 10) + "\n")
            lines.append(f"Vạch số {i}.{i % 10}: Vạch kẻ đường số {i}\n" + ("Quy cách vạch nét đứt nét liền... " * 10) + "\n")
        payload = "".join(lines)
        assert len(payload.encode("utf-8")) > 50 * 1024

        t0 = time.perf_counter()
        sign_matches = list(VietnameseLegalGrammar.SIGN_SPEC.finditer(payload))
        elapsed_sign = time.perf_counter() - t0
        assert elapsed_sign < 0.01, f"SIGN_SPEC ReDoS detected: took {elapsed_sign:.5f}s (> 0.01s)"
        assert len(sign_matches) > 0

        t0 = time.perf_counter()
        marking_matches = list(VietnameseLegalGrammar.MARKING_SPEC.finditer(payload))
        elapsed_marking = time.perf_counter() - t0
        assert elapsed_marking < 0.01, f"MARKING_SPEC ReDoS detected: took {elapsed_marking:.5f}s (> 0.01s)"
        assert len(marking_matches) > 0

    def test_cross_reference_compound_regex_linear_scan(self) -> None:
        """Verifies compound cross-reference regex on pathological comma-separated point lists."""
        points_list = ", ".join([f"điểm {chr(97 + (i % 26))}" for i in range(200)])
        text = f"theo quy định tại các {points_list}, khoản 5, Điều 123 Nghị định 100/2019/NĐ-CP"

        t0 = time.perf_counter()
        m = VietnameseLegalGrammar.ARTICLE_REF_COMPOUND.search(text)
        elapsed = time.perf_counter() - t0

        assert elapsed < 0.01, f"ARTICLE_REF_COMPOUND ReDoS detected: took {elapsed:.5f}s"
        assert m is not None
        assert m.group("clause") == "5"
        assert m.group("article") == "123"

    @pytest.mark.parametrize(
        ("val_str", "unit_str", "expected_vnd"),
        [
            ("800.000", "đồng", 800_000),
            ("1.000.000", "đồng", 1_000_000),
            ("4", "triệu đồng", 4_000_000),
            ("0,4", "triệu đồng", 400_000),
            ("1,5", "tỷ đồng", 1_500_000_000),
            ("500", "nghìn đồng", 500_000),
            ("500", "k", 500_000),
            ("30.000.000", "đồng", 30_000_000),
            ("  100.000  ", "  đồng  ", 100_000),
            ("", "đồng", None),
            ("invalid", "đồng", None),
        ],
    )
    def test_parse_vnd_amount_bounds(
        self, val_str: str, unit_str: str | None, expected_vnd: int | None
    ) -> None:
        assert parse_vnd_amount(val_str, unit_str) == expected_vnd


# ==============================================================================
# 2. Adversarial QCVN 41 Road Markings Extraction (MARKING_SPEC Nodes)
# ==============================================================================

SAMPLE_QCVN_41_MARKINGS_TEXT = """
QUY CHUẨN KỸ THUẬT QUỐC GIA
QCVN 41:2019/BGTVT
Báo hiệu đường bộ

PHỤ LỤC G
VẠCH KẺ ĐƯỜNG

Vạch số 1.1: Vạch đơn nét liền màu trắng
Dùng để phân chia các làn xe cùng chiều; các xe không được phép chuyển làn hoặc đè lên vạch.

Vạch số 2.2: Vạch đơn nét đứt màu vàng
Dùng để phân chia hai chiều xe chạy ngược chiều nhau trên các đoạn đường có 2 hoặc 3 làn xe; xe được phép đè lên vạch khi cần thiết.

Vạch số 3.1: Vạch giới hạn mép phần xe chạy
Vạch đơn nét liền màu trắng dùng để xác định mép ngoài của phần đường dành cho xe cơ giới chạy.

Vạch số 1.2: Vạch đứt nét màu trắng
Dùng để phân chia làn xe cùng chiều cho phép chuyển làn.

Vạch 9.1: Vạch đỗ xe buýt
Quy định vị trí dừng đón trả khách của xe buýt tuyến cố định.
"""


class TestAdversarialRoadMarkingsExtraction:
    """Stress-tests LegalASTParser on diverse QCVN 41 road marking specifications."""

    def test_qcvn_41_road_markings_diverse_specs(self) -> None:
        parser = LegalASTParser()
        root = parser.parse_document(
            doc_code="QCVN 41:2019/BGTVT",
            raw_text=SAMPLE_QCVN_41_MARKINGS_TEXT,
            doc_title="Quy chuẩn báo hiệu đường bộ",
            doc_type="QUY_CHUAN_KY_THUAT",
        )

        assert root.level == "DOCUMENT"
        assert "qcvn_41_2019" in root.full_path

        # Verify Appendix G
        appendices = root.find_nodes_by_level("APPENDIX")
        assert len(appendices) == 1
        app_g = appendices[0]
        assert "Phụ lục G" in app_g.index_label
        assert app_g.full_path == "doc_qcvn_41_2019.app_g"

        # Verify MARKING_SPEC extraction
        markings = root.find_nodes_by_level("MARKING_SPEC")
        assert len(markings) == 5, f"Expected 5 road markings, found {len(markings)}"

        marking_codes = [m.index_label for m in markings]
        assert "1.1" in marking_codes
        assert "2.2" in marking_codes
        assert "3.1" in marking_codes
        assert "1.2" in marking_codes
        assert "9.1" in marking_codes

        # Inspect specific nodes
        m1_1 = next(m for m in markings if m.index_label == "1.1")
        assert m1_1.title == "Vạch đơn nét liền màu trắng"
        assert "Dùng để phân chia các làn xe cùng chiều" in m1_1.raw_text
        assert m1_1.full_path == "doc_qcvn_41_2019.app_g.1_1"
        assert m1_1.metadata["marking_code"] == "1.1"
        assert m1_1.lead_sentence == "Quy chuẩn kỹ thuật vạch kẻ đường 1.1: Vạch đơn nét liền màu trắng"

        m2_2 = next(m for m in markings if m.index_label == "2.2")
        assert m2_2.title == "Vạch đơn nét đứt màu vàng"
        assert m2_2.full_path == "doc_qcvn_41_2019.app_g.2_2"

        m3_1 = next(m for m in markings if m.index_label == "3.1")
        assert m3_1.title == "Vạch giới hạn mép phần xe chạy"
        assert m3_1.full_path == "doc_qcvn_41_2019.app_g.3_1"

    def test_cphc_chunking_on_marking_specs(self) -> None:
        """Verifies CPHCEngine generates valid CFQC chunks for road markings."""
        parser = LegalASTParser()
        root = parser.parse_document(
            doc_code="QCVN 41:2019/BGTVT",
            raw_text=SAMPLE_QCVN_41_MARKINGS_TEXT,
        )

        cphc = CPHCEngine()
        chunks, _norms = cphc.process_ast(root=root)

        assert len(chunks) == 5
        for chunk in chunks:
            assert chunk.hierarchy_path.startswith("doc_qcvn_41_2019.app_g.")
            assert chunk.norm_role == NormRole.HYPOTHESIS_CONDITION
            assert "Vạch" in chunk.verbatim_text
            assert "QCVN 41:2019/BGTVT" in chunk.contextualized_text

        # Verify marking 1.1 specifically
        m1_1_chunk = next(c for c in chunks if "1_1" in c.hierarchy_path)
        assert "Vạch số 1.1: Vạch đơn nét liền màu trắng" in m1_1_chunk.contextualized_text
        assert "Dùng để phân chia các làn xe cùng chiều" in m1_1_chunk.verbatim_text


# ==============================================================================
# 3. Adversarial AST-CPHC Path Alignment & Graph Linker Non-Loop Invariants
# ==============================================================================

SAMPLE_COMPLEX_DECREE = """
NGHỊ ĐỊNH
Số: 100/2019/NĐ-CP
Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ

Chương II
HÀNH VI VI PHẠM, HÌNH THỨC, MỨC XỬ PHẠT

Điều 5. Xử phạt người điều khiển xe ô tô vi phạm quy tắc giao thông
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng:
a) Không chấp hành hiệu lệnh của vạch kẻ đường số 1.1 hoặc biển số P.102, trừ trường hợp xe ưu tiên;
b) Dừng xe nơi có biển cấm dừng.
5. Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng:
a) Chạy quá tốc độ quy định từ 10 km/h đến 20 km/h;
b) Đi ngược chiều trên đường một chiều.
11. Hình thức xử phạt bổ sung:
a) Thực hiện hành vi quy định tại điểm b khoản 5 Điều này bị tước quyền sử dụng Giấy phép lái xe từ 02 tháng đến 04 tháng;
b) Thực hiện hành vi quy định tại điểm a khoản 5 Điều này bị tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng.
"""


class TestAdversarialPathAlignmentAndGraphLinker:
    """Stress-tests 100% path alignment between AST and CPHC and graph linker invariants."""

    def test_strict_ast_cphc_path_symmetry(self) -> None:
        parser = LegalASTParser()
        ast_root = parser.parse_document(
            doc_code="100/2019/NĐ-CP",
            raw_text=SAMPLE_COMPLEX_DECREE,
        )

        cphc = CPHCEngine()
        chunks, extractions = cphc.process_ast(root=ast_root)

        # Collect all AST node paths
        ast_paths = {n.full_path for n in ast_root.flatten()}

        # Verify every chunk hierarchy_path is an exact member of AST paths
        for chunk in chunks:
            assert chunk.hierarchy_path in ast_paths, (
                f"Chunk path '{chunk.hierarchy_path}' has split-brain deviation from AST node paths!"
            )

        for norm in extractions:
            assert norm.hierarchy_path in ast_paths

    def test_supplementary_sanction_scoping_isolation(self) -> None:
        """Verifies point a and point b in clause 5 get exact distinct suspensions without bleeding to clause 1."""
        parser = LegalASTParser()
        ast_root = parser.parse_document(
            doc_code="100/2019/NĐ-CP",
            raw_text=SAMPLE_COMPLEX_DECREE,
        )
        cphc = CPHCEngine()
        chunks, _ = cphc.process_ast(root=ast_root)

        # Clause 1 Point a -> No suspension
        cl1_a = next(c for c in chunks if c.clause_number == 1 and c.point_letter == "a")
        assert cl1_a.additional_sanctions.license_suspension_months_min is None

        # Clause 5 Point a -> 1-3 months
        cl5_a = next(c for c in chunks if c.clause_number == 5 and c.point_letter == "a")
        assert cl5_a.additional_sanctions.license_suspension_months_min == 1
        assert cl5_a.additional_sanctions.license_suspension_months_max == 3

        # Clause 5 Point b -> 2-4 months
        cl5_b = next(c for c in chunks if c.clause_number == 5 and c.point_letter == "b")
        assert cl5_b.additional_sanctions.license_suspension_months_min == 2
        assert cl5_b.additional_sanctions.license_suspension_months_max == 4

    def test_graph_linker_eliminates_self_loops_and_links_technical_standards(self) -> None:
        """Verifies graph linker produces no self-loops and properly links signs & markings."""
        parser = LegalASTParser()
        ast_root = parser.parse_document(
            doc_code="100/2019/NĐ-CP",
            raw_text=SAMPLE_COMPLEX_DECREE,
        )
        cphc = CPHCEngine()
        chunks, norms = cphc.process_ast(root=ast_root)

        linker = DeterministicGraphLinker()
        edges = linker.extract_edges_from_chunks(chunks=chunks, norms=norms, ast_root=ast_root)

        assert len(edges) > 0

        # Invariant 1: Absolutely zero self-loops across ALL edge types
        for edge in edges:
            assert edge["source_path"] != edge["target_path"], (
                f"Self-loop edge found: source={edge['source_path']} == target={edge['target_path']}"
            )

        # Invariant 2: REFERENCES_TECHNICAL_STANDARD for Vạch 1.1 and Biển P.102
        tech_edges = [
            e for e in edges if e["relation_type"] == GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value
        ]
        assert len(tech_edges) >= 2
        target_paths = {e["target_path"] for e in tech_edges}
        assert "doc_qcvn_41_2019.app_g.1_1" in target_paths
        assert "doc_qcvn_41_2019.app_b.p_102" in target_paths

        # Invariant 3: HAS_ADDITIONAL_SANCTION edges exist and point to Khoản 11 / supp paths
        supp_edges = [
            e for e in edges if e["relation_type"] == GraphRelationType.HAS_ADDITIONAL_SANCTION.value
        ]
        assert len(supp_edges) >= 2
        for se in supp_edges:
            assert "doc_100_2019_nd_cp.c_ii.a5" in se["target_path"]
            assert se["source_path"] != se["target_path"]


# ==============================================================================
# 4. Multi-Clause, Multi-Point Adversarial Penalty Precision (Zero Penalty Bleed)
# ==============================================================================

COMPLEX_ADVERSARIAL_STATUTE = """
NGHỊ ĐỊNH
Số: 999/2026/NĐ-CP
Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ thử nghiệm

Chương II
HÀNH VI VI PHẠM VÀ HÌNH THỨC XỬ PHẠT

Điều 15. Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Không chấp hành hiệu lệnh của biển báo hiệu, vạch kẻ đường;
b) Không sử dụng đèn chiếu sáng khi trời tối;
c) Bấm còi trong đô thị từ 22 giờ ngày hôm trước đến 05 giờ ngày hôm sau;
d) Không thắt dây an toàn khi điều khiển xe chạy trên đường.

2. Phạt tiền từ 400.000 đồng đến 600.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Chuyển làn đường không có tín hiệu báo trước;
b) Dừng xe, đỗ xe không đúng quy định;
c) Quay đầu xe tại nơi có biển báo cấm quay đầu xe.

3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;
b) Không tuân thủ hiệu lệnh của người điều khiển giao thông;
c) Đi vào đường cấm, khu vực cấm;
d) Điều khiển xe chạy quá tốc độ quy định từ 10 km/h đến 20 km/h;
đ) Dùng tay sử dụng điện thoại di động khi đang điều khiển xe chạy trên đường;
e) Đi ngược chiều trên đường một chiều;
g) Không nhường đường cho xe xin vượt khi có đủ điều kiện an toàn.

4. Phạt tiền từ 2.000.000 đồng đến 3.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Dừng xe, đỗ xe trên đường cao tốc không đúng nơi quy định;
b) Quay đầu xe trên đường cao tốc;
c) Lùi xe trên đường cao tốc.

10. Ngoài việc bị phạt tiền, người điều khiển xe thực hiện hành vi vi phạm còn bị áp dụng các hình thức xử phạt bổ sung sau đây:
a) Thực hiện hành vi quy định tại điểm e khoản 3; điểm a khoản 4 Điều này bị tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng;
b) Thực hiện hành vi quy định tại điểm c khoản 3 Điều này bị tước quyền sử dụng Giấy phép lái xe từ 02 tháng đến 04 tháng và bị trừ 2 điểm trên Giấy phép lái xe;
c) Thực hiện hành vi quy định tại điểm d, đ khoản 3; điểm b, c khoản 4 Điều này bị tước quyền sử dụng Giấy phép lái xe từ 03 tháng đến 05 tháng, tạm giữ phương tiện 07 ngày và bị trừ 4 điểm trên Giấy phép lái xe;
d) Thực hiện hành vi quy định tại khoản 2 Điều này bị tước quyền sử dụng Giấy phép lái xe từ 10 tháng đến 12 tháng.
"""

MULTI_RELATION_TEST_STATUTE = """
NGHỊ ĐỊNH
Số: 888/2026/NĐ-CP
Quy định chi tiết và biện pháp thi hành một số điều của Luật Giao thông đường bộ

Chương I
QUY ĐỊNH CHUNG

Điều 3. Giải thích từ ngữ
1. Trong Nghị định này, các từ ngữ dưới đây được hiểu như sau:
a) “Làn đường” là một phần của phần đường xe chạy được chia theo chiều dọc của đường, có bề rộng đủ cho xe chạy an toàn.
b) “Đường ưu tiên” là đường mà trên đó phương tiện tham gia giao thông được các phương tiện đến từ hướng khác nhường đường khi qua nơi đường giao nhau.

Chương II
XỬ PHẠT VI PHẠM

Điều 8. Xử phạt hành vi vi phạm quy tắc giao thông
1. Phạt tiền từ 1.000.000 đồng đến 2.000.000 đồng đối với người điều khiển xe thực hiện hành vi:
a) Không chấp hành hiệu lệnh của biển báo P.102, biển P.130 hoặc biển R.301a theo QCVN 41:2019/BGTVT, trừ trường hợp xe ưu tiên đang làm nhiệm vụ khẩn cấp;
b) Đi không đúng làn đường quy định hoặc đè vạch kẻ đường 1.1 hoặc vạch 2.2 theo QCVN 41:2019/BGTVT;
c) Vi phạm quy tắc giao thông đường bộ quy định tại Điều 9, Điều 10 Luật Giao thông đường bộ.

2. Phạt tiền từ 3.000.000 đồng đến 5.000.000 đồng đối với người điều khiển xe thực hiện hành vi quy định tại Điều 22 Luật TTATGTĐB 2024.

3. Nghị định này sửa đổi, bổ sung khoản 1, Điều 5 Nghị định số 100/2019/NĐ-CP.
4. Bãi bỏ quy định tại điểm c, khoản 2, Điều 6 Nghị định số 100/2019/NĐ-CP.
5. Thông tư số 58/2020/TT-BCA hướng dẫn thi hành Điều 8 Nghị định số 888/2026/NĐ-CP.

6. Hình thức xử phạt bổ sung:
a) Thực hiện hành vi quy định tại điểm a khoản 1 Điều này bị tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 02 tháng.
"""


class TestCPHCPenaltyIsolationAdversarial:
    """Stress tests CPHCEngine for 100% penalty precision and zero penalty bleed."""

    def test_multi_clause_multi_point_strict_isolation(self) -> None:
        parser = LegalASTParser(VietnameseLegalGrammar)
        root = parser.parse_document("999/2026/NĐ-CP", COMPLEX_ADVERSARIAL_STATUTE)
        engine = CPHCEngine(VietnameseLegalGrammar)
        chunks, _norms = engine.process_ast(root)

        # Map chunks by (clause_number, point_letter)
        chunk_map: dict[tuple[int | None, str | None], list] = {}
        for c in chunks:
            chunk_map.setdefault((c.clause_number, c.point_letter), []).append(c)

        # 1. Clause 1 Points (a, b, c, d) MUST HAVE ZERO supplementary sanctions
        for pt in ["a", "b", "c", "d"]:
            cl1_pt = chunk_map.get((1, pt))
            assert cl1_pt is not None, f"Missing Khoản 1 Điểm {pt}"
            c = cl1_pt[0]
            assert c.additional_sanctions.license_suspension_months_min is None, (
                f"Bleed detected in Khoản 1 Điểm {pt}: min_months={c.additional_sanctions.license_suspension_months_min}"
            )
            assert c.additional_sanctions.license_suspension_months_max is None
            assert c.additional_sanctions.demerit_points is None
            assert c.additional_sanctions.vehicle_impoundment_days is None

        # 2. Clause 2 Points (a, b, c): whole Clause 2 was cited in 10.d -> ALL must have 10-12 months
        for pt in ["a", "b", "c"]:
            cl2_pt = chunk_map.get((2, pt))
            assert cl2_pt is not None, f"Missing Khoản 2 Điểm {pt}"
            c = cl2_pt[0]
            assert c.additional_sanctions.license_suspension_months_min == 10
            assert c.additional_sanctions.license_suspension_months_max == 12
            assert c.additional_sanctions.demerit_points is None

        # 3. Clause 3 Point c (Điểm c Khoản 3 -> 10.b: 2-4 months, 2 demerit points)
        cl3_c = chunk_map[(3, "c")][0]
        assert cl3_c.additional_sanctions.license_suspension_months_min == 2
        assert cl3_c.additional_sanctions.license_suspension_months_max == 4
        assert cl3_c.additional_sanctions.demerit_points == 2
        assert cl3_c.additional_sanctions.vehicle_impoundment_days is None

        # 4. Clause 3 Point d (Điểm d, đ Khoản 3 -> 10.c: 3-5 months, 7 days impound, 4 demerit points)
        cl3_d = chunk_map[(3, "d")][0]
        assert cl3_d.additional_sanctions.license_suspension_months_min == 3
        assert cl3_d.additional_sanctions.license_suspension_months_max == 5
        assert cl3_d.additional_sanctions.demerit_points == 4
        assert cl3_d.additional_sanctions.vehicle_impoundment_days == 7

        # 5. Clause 3 Point e (Điểm e Khoản 3 -> 10.a: 1-3 months)
        cl3_e = chunk_map[(3, "e")][0]
        assert cl3_e.additional_sanctions.license_suspension_months_min == 1
        assert cl3_e.additional_sanctions.license_suspension_months_max == 3
        assert cl3_e.additional_sanctions.demerit_points is None

        # 6. Clause 3 Point g (Điểm g is NOT mentioned in any sub-rule -> ZERO SANCTIONS)
        cl3_g = chunk_map[(3, "g")][0]
        assert cl3_g.additional_sanctions.license_suspension_months_min is None, (
            "Bleed detected in Khoản 3 Điểm g from neighboring points a,b,c,d,đ,e!"
        )
        assert cl3_g.additional_sanctions.license_suspension_months_max is None
        assert cl3_g.additional_sanctions.demerit_points is None
        assert cl3_g.additional_sanctions.vehicle_impoundment_days is None

        # 7. Clause 4 Point a (10.a: 1-3 months)
        cl4_a = chunk_map[(4, "a")][0]
        assert cl4_a.additional_sanctions.license_suspension_months_min == 1
        assert cl4_a.additional_sanctions.license_suspension_months_max == 3
        assert cl4_a.additional_sanctions.demerit_points is None

        # 8. Clause 4 Point b (10.c: 3-5 months, 7 days impound, 4 demerit points)
        cl4_b = chunk_map[(4, "b")][0]
        assert cl4_b.additional_sanctions.license_suspension_months_min == 3
        assert cl4_b.additional_sanctions.license_suspension_months_max == 5
        assert cl4_b.additional_sanctions.demerit_points == 4
        assert cl4_b.additional_sanctions.vehicle_impoundment_days == 7

    def test_supplementary_rule_indexer_direct(self) -> None:
        parser = LegalASTParser(VietnameseLegalGrammar)
        root = parser.parse_document("999/2026/NĐ-CP", COMPLEX_ADVERSARIAL_STATUTE)
        art_node = root.find_nodes_by_level("ARTICLE")[0]

        rules = SupplementarySanctionParser.index_article_supplementary_rules(art_node)
        assert len(rules) >= 4

        matched_3e = SupplementarySanctionParser.match_rules(rules, 3, "e")
        assert len(matched_3e) == 1
        assert "tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng" in matched_3e[0].raw_text

        matched_3g = SupplementarySanctionParser.match_rules(rules, 3, "g")
        assert len(matched_3g) == 0, "Điểm g must have zero matches!"

        matched_2a = SupplementarySanctionParser.match_rules(rules, 2, "a")
        assert len(matched_2a) == 1
        assert "10 tháng đến 12 tháng" in matched_2a[0].raw_text


class TestDeterministicGraphLinkerAdversarial:
    """Stress tests DeterministicGraphLinker to guarantee zero self-loops and relational precision."""

    def test_zero_self_loops_across_all_extracted_edges(self) -> None:
        parser = LegalASTParser(VietnameseLegalGrammar)
        root = parser.parse_document("888/2026/NĐ-CP", MULTI_RELATION_TEST_STATUTE)
        cphc = CPHCEngine(VietnameseLegalGrammar)
        chunks, norms = cphc.process_ast(root)

        linker = DeterministicGraphLinker(VietnameseLegalGrammar)
        edges = linker.extract_edges_from_chunks(chunks=chunks, norms=norms, ast_root=root)

        assert len(edges) > 0

        for idx, edge in enumerate(edges):
            source = edge["source_path"]
            target = edge["target_path"]
            rel_type = edge["relation_type"]

            # INVARIANT 1: Zero self-loops (source_path != target_path)
            assert source != target, (
                f"Self-loop detected on edge #{idx} ({rel_type}): source={source}, target={target}"
            )

            # INVARIANT 2: Valid non-empty ltree paths
            assert re.match(r"^[a-zA-Z0-9_.]+$", source), f"Invalid source ltree path: {source}"
            assert re.match(r"^[a-zA-Z0-9_.]+$", target), f"Invalid target ltree path: {target}"

            # INVARIANT 3: Confidence score valid
            assert 0.0 < edge["confidence_score"] <= 1.0

    def test_relation_type_distribution(self) -> None:
        parser = LegalASTParser(VietnameseLegalGrammar)
        root = parser.parse_document("888/2026/NĐ-CP", MULTI_RELATION_TEST_STATUTE)
        cphc = CPHCEngine(VietnameseLegalGrammar)
        chunks, norms = cphc.process_ast(root)

        linker = DeterministicGraphLinker(VietnameseLegalGrammar)
        edges = linker.extract_edges_from_chunks(chunks=chunks, norms=norms, ast_root=root)

        rel_types = {e["relation_type"] for e in edges}

        # Verify expected relation types extracted
        assert GraphRelationType.DEFINES_TERM.value in rel_types
        assert GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value in rel_types
        assert GraphRelationType.DEFINES_SANCTION_FOR.value in rel_types
        assert GraphRelationType.MODIFIES_AND_REPLACES.value in rel_types
        assert GraphRelationType.REPEALS.value in rel_types
        assert GraphRelationType.GUIDES.value in rel_types
        assert GraphRelationType.HAS_ADDITIONAL_SANCTION.value in rel_types
        assert GraphRelationType.OVERRIDES_PRIORITY.value in rel_types

        # Verify HAS_ADDITIONAL_SANCTION targets the supplementary clause or sub-point
        supp_edges = [e for e in edges if e["relation_type"] == GraphRelationType.HAS_ADDITIONAL_SANCTION.value]
        assert len(supp_edges) >= 1
        for se in supp_edges:
            assert se["source_path"] != se["target_path"]
            assert "p_a" in se["source_path"]
            assert "c6" in se["target_path"] or "c_supp" in se["target_path"]

    def test_edge_target_paths_consistency(self) -> None:
        parser = LegalASTParser(VietnameseLegalGrammar)
        root = parser.parse_document("888/2026/NĐ-CP", MULTI_RELATION_TEST_STATUTE)
        cphc = CPHCEngine(VietnameseLegalGrammar)
        chunks, norms = cphc.process_ast(root)

        linker = DeterministicGraphLinker(VietnameseLegalGrammar)
        edges = linker.extract_edges_from_chunks(chunks=chunks, norms=norms, ast_root=root)

        # Check technical standard targets
        qcvn_edges = [e for e in edges if e["relation_type"] == GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value]
        qcvn_targets = [e["target_path"] for e in qcvn_edges]
        assert any("doc_qcvn_41_2019.app_b.p_102" in t for t in qcvn_targets)
        assert any("doc_qcvn_41_2019.app_g.1_1" in t for t in qcvn_targets)

        # Check law targets
        law_edges = [e for e in edges if e["relation_type"] == GraphRelationType.DEFINES_SANCTION_FOR.value]
        law_targets = [e["target_path"] for e in law_edges]
        assert any("doc_luat_gtdb_2008.a9" in t for t in law_targets)
        assert any("doc_luat_ttatgtdb_2024.a22" in t for t in law_targets)
