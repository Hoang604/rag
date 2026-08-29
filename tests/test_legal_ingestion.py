"""Comprehensive unit and mock tests for Vietnamese Traffic Law Ingestion Subsystem (M3).

Tests:
1. Regex grammar rules & currency parsers (VietnameseLegalGrammar, parse_vnd_amount).
2. AST parsing & hierarchy tree generation (LegalASTParser, ASTNode, lead sentence extraction).
3. Context-Preserving Hierarchical Chunking (synthesize_cphc_prefix, CPHCEngine, lineage inheritance).
4. Deterministic cross-reference graph linking across normative triad (DeterministicGraphLinker).
5. Idempotent PostgreSQL bulk loading (PostgresBulkLoader with mock asyncpg pool).
6. End-to-end legal ingestion pipeline execution (LegalIngestionPipeline, IngestionResult).
"""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from rag_eval.legal.ingestion.cphc import CPHCEngine, synthesize_cphc_prefix
from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar, parse_vnd_amount
from rag_eval.legal.ingestion.graph_linker import DeterministicGraphLinker
from rag_eval.legal.ingestion.loader import PostgresBulkLoader
from rag_eval.legal.ingestion.parser import (
    LegalASTParser,
    sanitize_ltree_label,
)
from rag_eval.legal.ingestion.pipeline import LegalIngestionPipeline
from rag_eval.legal.schemas import (
    GraphRelationType,
    VehicleCategory,
)

# Sample statutory fixture texts
SAMPLE_DECREE_100_TEXT = """
NGHỊ ĐỊNH
Số: 100/2019/NĐ-CP
Quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ và đường sắt

Chương II
HÀNH VI VI PHẠM, HÌNH THỨC, MỨC XỬ PHẠT VÀ BIỆN PHÁP KHẮC PHỤC HẬU QUẢ

Mục 1
VI PHẠM QUY TẮC GIAO THÔNG ĐƯỜNG BỘ

Điều 5. Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông đường bộ
1. Phạt tiền từ 200.000 đồng đến 400.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường, trừ các hành vi vi phạm quy định tại điểm a khoản 3 Điều 5;
b) Chuyển hướng không nhường đường cho các xe ưu tiên.
3. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;
b) Đi vào đường cấm, khu vực cấm, đi ngược chiều của đường một chiều;
c) Không tuân thủ hiệu lệnh của người điều khiển giao thông theo quy định tại Điều 10 Luật Giao thông đường bộ.
11. Ngoài việc bị phạt tiền, người điều khiển xe thực hiện hành vi vi phạm còn bị áp dụng các hình thức xử phạt bổ sung sau đây:
b) Thực hiện hành vi quy định tại điểm a, điểm b khoản 3 Điều này bị tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng;
c) Thực hiện hành vi quy định tại điểm c khoản 3 Điều này bị tước quyền sử dụng Giấy phép lái xe từ 02 tháng đến 04 tháng và bị trừ 2 điểm trên Giấy phép lái xe.
"""

SAMPLE_AMENDMENT_DECREE_123_TEXT = """
NGHỊ ĐỊNH
Số: 123/2021/NĐ-CP
Sửa đổi, bổ sung một số điều của các Nghị định quy định xử phạt vi phạm hành chính trong lĩnh vực hàng hải, giao thông đường bộ

Điều 2. Sửa đổi, bổ sung một số điều của Nghị định số 100/2019/NĐ-CP
3. Sửa đổi, bổ sung điểm i khoản 5 Điều 5 như sau:
i) Điều khiển xe chạy quá tốc độ quy định từ 10 km/h đến 20 km/h; phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng; tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng.
"""

SAMPLE_QCVN_41_TEXT = """
QUY CHUẨN KỸ THUẬT QUỐC GIA
QCVN 41:2019/BGTVT
Báo hiệu đường bộ

PHỤ LỤC B
BIỂN BÁO CẤM

Biển số P.102: Cấm đi ngược chiều
Biển có dạng hình tròn, nền đỏ, ở giữa có vạch trắng nằm ngang. Để báo đường cấm tất cả các loại xe (cơ giới và thô sơ) đi vào theo chiều đặt biển, trừ các xe ưu tiên theo quy định.

Biển số P.106a: Cấm xe ô tô tải
Biển có dạng hình tròn, viền đỏ, nền trắng, vẽ hình xe ô tô tải. Để báo đường cấm tất cả các loại xe ô tô tải trừ các xe ưu tiên theo quy định.

PHỤ LỤC G
VẠCH KẺ ĐƯỜNG

Vạch số 1.1: Vạch đơn nét liền màu trắng
Dùng để phân chia các làn xe cùng chiều; xe không được lấn làn hoặc đè lên vạch.

Vạch số 2.2: Vạch đơn nét đứt màu vàng
Dùng để phân chia hai chiều xe chạy ngược chiều nhau trên đường có 2 hoặc 3 làn xe.
"""


class TestVietnameseLegalGrammar:
    """Verifies statutory regex grammar rules and numeric currency converters."""

    def test_parse_vnd_amount_standards(self) -> None:
        assert parse_vnd_amount("800.000", "đồng") == 800000
        assert parse_vnd_amount("1.000.000", "đồng") == 1000000
        assert parse_vnd_amount("4", "triệu đồng") == 4000000
        assert parse_vnd_amount("30.000.000", "đồng") == 30000000
        assert parse_vnd_amount("40.000.000", "đồng") == 40000000
        assert parse_vnd_amount("500", "nghìn đồng") == 500000
        assert parse_vnd_amount("invalid", "đồng") is None

    def test_grammar_fine_range_regex(self) -> None:
        text = "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với hành vi..."
        match = VietnameseLegalGrammar.FINE_RANGE_REGEX.search(text)
        assert match is not None
        assert match.group("min_val") == "800.000"
        assert match.group("max_val") == "1.000.000"

    def test_grammar_suspension_and_demerit_regex(self) -> None:
        text1 = "tước quyền sử dụng Giấy phép lái xe từ 01 tháng đến 03 tháng"
        m1 = VietnameseLegalGrammar.SUSPENSION_REGEX.search(text1)
        assert m1 is not None
        assert m1.group("min_months") == "01"
        assert m1.group("max_months") == "03"

        text2 = "bị trừ 2 điểm trên Giấy phép lái xe"
        m2 = VietnameseLegalGrammar.DEMERIT_REGEX.search(text2)
        assert m2 is not None
        assert m2.group("points") == "2"

    def test_grammar_cross_reference_regex(self) -> None:
        text = "theo quy định tại điểm a, khoản 3, Điều 5 Nghị định 100/2019/NĐ-CP"
        m = VietnameseLegalGrammar.ARTICLE_REF_REGEX.search(text)
        assert m is not None
        assert m.group("point") == "a"
        assert m.group("clause") == "3"
        assert m.group("article") == "5"

    def test_grammar_sign_reference_regex(self) -> None:
        text = "đường có biển báo số P.102 hoặc biển 'Cấm đi ngược chiều'"
        matches = list(VietnameseLegalGrammar.SIGN_REF_REGEX.finditer(text))
        assert len(matches) == 2
        assert matches[0].group("sign_code") == "P.102"
        assert matches[1].group("sign_name") == "Cấm đi ngược chiều"

    def test_redos_safety_linear_time(self) -> None:
        long_string = "NGHỊ ĐỊNH\nSố: 999/2026/NĐ-CP\n" + "A" * 20000 + "\n"
        t0 = time.perf_counter()
        VietnameseLegalGrammar.DOC_HEADER.search(long_string)
        t1 = time.perf_counter()
        assert (t1 - t0) < 0.1, "ReDoS detected on large string scan"

    def test_single_line_chapter_and_section_regex(self) -> None:
        text = "Chương II. HÀNH VI VI PHẠM\nMục 1 - QUY TẮC GIAO THÔNG\nĐiều 5. Xử phạt"
        chap = VietnameseLegalGrammar.CHAPTER.search(text)
        assert chap is not None
        assert chap.group(1) == "II"
        assert chap.group(2).strip() == "HÀNH VI VI PHẠM"

        sec = VietnameseLegalGrammar.SECTION.search(text)
        assert sec is not None
        assert sec.group(1) == "1"
        assert sec.group(2).strip() == "QUY TẮC GIAO THÔNG"


class TestLegalASTParser:
    """Verifies syntactic AST hierarchical parsing on Vietnamese legislation."""

    def test_parse_decree_structure(self) -> None:
        parser = LegalASTParser()
        root = parser.parse_document(
            doc_code="100/2019/NĐ-CP",
            raw_text=SAMPLE_DECREE_100_TEXT,
            doc_title="Nghị định 100/2019/NĐ-CP",
            doc_type="NGHI_DINH",
        )

        assert root.level == "DOCUMENT"
        assert root.index_label == "100/2019/NĐ-CP"
        assert root.full_path == "doc_100_2019_nd_cp"

        # Check Chapter II
        chapters = root.find_nodes_by_level("CHAPTER")
        assert len(chapters) == 1
        assert "Chương II" in chapters[0].index_label
        assert "c_ii" in chapters[0].full_path

        # Check Article 5
        articles = root.find_nodes_by_level("ARTICLE")
        assert len(articles) == 1
        art5 = articles[0]
        assert art5.index_label == "Điều 5"
        assert "Xử phạt người điều khiển xe ô tô" in art5.title
        assert "a5" in art5.full_path

        # Check Clauses under Article 5
        clauses = art5.find_nodes_by_level("CLAUSE")
        assert len(clauses) >= 3  # Khoản 1, Khoản 3, Khoản 11
        cl3 = next(c for c in clauses if "Khoản 3" in c.index_label)
        assert cl3.lead_sentence is not None
        assert "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng" in cl3.lead_sentence

        # Check Points under Clause 3
        points = cl3.find_nodes_by_level("POINT")
        assert len(points) == 3  # Điểm a, b, c
        pt_a = points[0]
        assert pt_a.index_label == "Điểm a"
        assert "Không chấp hành hiệu lệnh của đèn tín hiệu" in pt_a.raw_text
        # Invariant: Lead sentence inherited from Khoản 3
        assert pt_a.lead_sentence == cl3.lead_sentence
        assert pt_a.full_path == "doc_100_2019_nd_cp.c_ii.a5.c3.p_a"

    def test_parse_technical_standard_qcvn_signs_and_markings(self) -> None:
        parser = LegalASTParser()
        root = parser.parse_document(
            doc_code="QCVN 41:2019/BGTVT",
            raw_text=SAMPLE_QCVN_41_TEXT,
            doc_title="Quy chuẩn báo hiệu đường bộ",
            doc_type="QUY_CHUAN_KY_THUAT",
        )

        assert root.level == "DOCUMENT"
        assert "qcvn_41_2019" in root.full_path

        appendices = root.find_nodes_by_level("APPENDIX")
        assert len(appendices) == 2

        signs = root.find_nodes_by_level("SIGN_SPEC")
        assert len(signs) == 2
        sign_codes = [s.index_label for s in signs]
        assert "P.102" in sign_codes
        assert "P.106a" in sign_codes
        assert signs[0].full_path == "doc_qcvn_41_2019.app_b.p_102"

        markings = root.find_nodes_by_level("MARKING_SPEC")
        assert len(markings) == 2
        marking_codes = [m.index_label for m in markings]
        assert "1.1" in marking_codes
        assert "2.2" in marking_codes
        assert markings[0].full_path == "doc_qcvn_41_2019.app_g.1_1"

    def test_sanitize_ltree_label_edge_cases(self) -> None:
        assert sanitize_ltree_label("100/2019/NĐ-CP") == "100_2019_nd_cp"
        assert sanitize_ltree_label("QCVN 41:2019/BGTVT") == "qcvn_41_2019_bgtvt"
        assert sanitize_ltree_label("Điều 5. Khoản 3") == "dieu_5_khoan_3"
        assert sanitize_ltree_label("") == "root"


class TestCPHCEngine:
    """Verifies Context-Preserving Hierarchical Chunking and lineage synthesis."""

    def test_synthesize_cphc_prefix_format(self) -> None:
        ltree_path, text = synthesize_cphc_prefix(
            doc_code="100/2019/NĐ-CP",
            doc_title="Nghị định 100/2019",
            chapter_title="Chương II - Xử phạt",
            article_num=5,
            article_title="Xử phạt xe ô tô",
            clause_num=3,
            clause_lead="Phạt tiền từ 800.000đ đến 1.000.000đ:",
            point_letter="a",
            point_body="Không chấp hành đèn tín hiệu",
            additional_sanctions_summary="Tước GPLX 1-3 tháng",
        )

        assert ltree_path == "doc_100_2019_nd_cp.a5.c3.p_a"
        assert "[VĂN BẢN]: Nghị định 100/2019" in text
        assert "[CHƯƠNG]: Chương II - Xử phạt" in text
        assert "[ĐIỀU 5]: Xử phạt xe ô tô" in text
        assert "[KHOẢN 3 - LỜI DẪN]: Phạt tiền từ 800.000đ đến 1.000.000đ:" in text
        assert "[ĐIỂM a]: Không chấp hành đèn tín hiệu" in text
        assert "[CHẾ TÀI BỔ SUNG & TRỪ ĐIỂM]: Tước GPLX 1-3 tháng" in text

    def test_cphc_engine_processes_ast_and_eliminates_dangling_points(self) -> None:
        parser = LegalASTParser()
        ast_root = parser.parse_document(
            doc_code="100/2019/NĐ-CP",
            raw_text=SAMPLE_DECREE_100_TEXT,
            doc_title="Nghị định 100/2019/NĐ-CP",
        )

        engine = CPHCEngine()
        chunks, extractions = engine.process_ast(root=ast_root)

        assert len(chunks) >= 5
        assert len(extractions) == len(chunks)

        # Invariant 1: Hierarchy path matches AST node full path 100%
        pt_a_cl1 = next(
            c for c in chunks if c.clause_number == 1 and c.point_letter == "a"
        )
        assert pt_a_cl1.hierarchy_path == "doc_100_2019_nd_cp.c_ii.a5.c1.p_a"
        # Khoản 1 Điểm a is not in Khoản 11 -> no suspension
        assert pt_a_cl1.additional_sanctions.license_suspension_months_min is None

        # Inspect Điểm b Khoản 3 Điều 5
        chk_b = next(
            c for c in chunks if c.clause_number == 3 and c.point_letter == "b"
        )
        assert chk_b.hierarchy_path == "doc_100_2019_nd_cp.c_ii.a5.c3.p_b"
        assert chk_b.additional_sanctions.license_suspension_months_min == 1
        assert chk_b.additional_sanctions.license_suspension_months_max == 3

        # Inspect Điểm c Khoản 3 Điều 5 (Point c has 2-4 months + 2 demerit points)
        chk_c = next(
            c for c in chunks if c.clause_number == 3 and c.point_letter == "c"
        )
        assert chk_c.hierarchy_path == "doc_100_2019_nd_cp.c_ii.a5.c3.p_c"
        assert chk_c.additional_sanctions.license_suspension_months_min == 2
        assert chk_c.additional_sanctions.license_suspension_months_max == 4
        assert chk_c.additional_sanctions.demerit_points == 2

        # Invariant 2: Vehicle types extracted from Article title
        assert VehicleCategory.CAR_PASSENGER in chk_b.vehicle_types
        assert VehicleCategory.CAR_TRUCK in chk_b.vehicle_types

        # Invariant 3: Fine bounds numerical precision
        assert chk_b.fine_bounds.min_fine_vnd == 800000
        assert chk_b.fine_bounds.max_fine_vnd == 1000000
        assert chk_b.fine_bounds.average_fine_vnd == 900000


class TestDeterministicGraphLinker:
    """Verifies statutory knowledge graph edge generation across 9 relationship types."""

    def test_extracts_all_statutory_relations(self) -> None:
        parser = LegalASTParser()
        ast_root = parser.parse_document(
            doc_code="100/2019/NĐ-CP",
            raw_text=SAMPLE_DECREE_100_TEXT,
            doc_title="Nghị định 100/2019/NĐ-CP",
        )
        engine = CPHCEngine()
        chunks, norms = engine.process_ast(root=ast_root)

        linker = DeterministicGraphLinker()
        edges = linker.extract_edges_from_chunks(
            chunks=chunks, norms=norms, ast_root=ast_root
        )

        assert len(edges) > 0

        relation_types = {e["relation_type"] for e in edges}

        # 1. Check DEFINES_SANCTION_FOR (Khoản 3 Điểm c references Điều 10 Luật GTĐB)
        assert GraphRelationType.DEFINES_SANCTION_FOR.value in relation_types
        law_edges = [
            e
            for e in edges
            if e["relation_type"] == GraphRelationType.DEFINES_SANCTION_FOR.value
        ]
        assert len(law_edges) > 0
        assert any("doc_luat_gtdb_2008.a10" in e["target_path"] for e in law_edges)

        # 2. Check HAS_ADDITIONAL_SANCTION (Eliminates self-loops!)
        assert GraphRelationType.HAS_ADDITIONAL_SANCTION.value in relation_types
        supp_edges = [
            e
            for e in edges
            if e["relation_type"] == GraphRelationType.HAS_ADDITIONAL_SANCTION.value
        ]
        assert len(supp_edges) > 0
        for se in supp_edges:
            assert se["source_path"] != se["target_path"], "Self-loop edge detected!"
            assert "doc_100_2019_nd_cp.c_ii.a5" in se["target_path"]

        # 3. Check EXEMPTS_CONDITION
        assert (
            GraphRelationType.OVERRIDES_PRIORITY.value in relation_types
            or GraphRelationType.EXEMPTS_CONDITION.value in relation_types
        )


class TestPostgresBulkLoader:
    """Verifies idempotent PostgreSQL bulk loader operations with mock asyncpg pool."""

    @pytest.mark.asyncio
    async def test_bulk_loader_idempotent_flow(self) -> None:
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.fetchval = AsyncMock(
            return_value="00000000-0000-0000-0000-000000000001"
        )
        mock_conn.execute = AsyncMock()

        class MockTransactionContext:
            async def __aenter__(self) -> None:
                pass

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

        mock_conn.transaction.return_value = MockTransactionContext()

        mock_pool = MagicMock(spec=asyncpg.Pool)

        class MockAcquireContext:
            async def __aenter__(self) -> AsyncMock:
                return mock_conn

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

        mock_pool.acquire.return_value = MockAcquireContext()

        loader = PostgresBulkLoader(pool=mock_pool)

        # 1. Test load_document
        doc_uuid = await loader.load_document(
            doc_code="100/2019/NĐ-CP",
            title="Nghị định 100/2019/NĐ-CP",
        )
        assert doc_uuid == "00000000-0000-0000-0000-000000000001"
        assert mock_conn.fetchval.called

        # 2. Test load_hierarchy_nodes
        parser = LegalASTParser()
        ast_root = parser.parse_document(
            doc_code="100/2019/NĐ-CP",
            raw_text=SAMPLE_DECREE_100_TEXT,
        )
        nodes = ast_root.flatten()
        node_map = await loader.load_hierarchy_nodes(nodes=nodes, document_id=doc_uuid)
        assert len(node_map) == len(nodes)

        # 3. Test load_chunks
        engine = CPHCEngine()
        chunks, _ = engine.process_ast(root=ast_root)
        chunk_map = await loader.load_chunks(
            chunks=chunks, document_id=doc_uuid, node_id_map=node_map
        )
        assert len(chunk_map) == len(chunks)

        # 4. Test load_graph_edges
        linker = DeterministicGraphLinker()
        edges = linker.extract_edges_from_chunks(chunks=chunks, ast_root=ast_root)
        edge_count = await loader.load_graph_edges(
            edges=edges, chunk_id_map=chunk_map, node_id_map=node_map
        )
        assert edge_count == len(edges)


class TestLegalIngestionPipeline:
    """Verifies end-to-end orchestration pipeline execution."""

    @pytest.mark.asyncio
    async def test_pipeline_ingest_text(self) -> None:
        pipeline = LegalIngestionPipeline()
        result = await pipeline.ingest_text(
            doc_code="100/2019/NĐ-CP",
            raw_text=SAMPLE_DECREE_100_TEXT,
            doc_title="Nghị định 100/2019",
            doc_type="NGHI_DINH",
            persist_db=False,
        )

        assert result.doc_code == "100/2019/NĐ-CP"
        assert result.doc_title == "Nghị định 100/2019"
        assert len(result.hierarchy_nodes) > 0
        assert len(result.chunks) > 0
        assert len(result.norms) == len(result.chunks)
        assert len(result.edges) > 0

    @pytest.mark.asyncio
    async def test_pipeline_ingest_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "sample_doc.txt"
        file_path.write_text(SAMPLE_DECREE_100_TEXT, encoding="utf-8")

        pipeline = LegalIngestionPipeline()
        result = await pipeline.ingest_file(
            file_path=file_path,
            doc_code="100/2019/NĐ-CP",
            doc_title="Nghị định 100/2019",
            persist_db=False,
        )

        assert result.doc_code == "100/2019/NĐ-CP"
        assert len(result.chunks) > 0

    @pytest.mark.asyncio
    async def test_pipeline_missing_file_raises_error(self, tmp_path: Path) -> None:
        pipeline = LegalIngestionPipeline()
        with pytest.raises(FileNotFoundError):
            await pipeline.ingest_file(
                file_path=tmp_path / "non_existent.txt",
                doc_code="999/2026/NĐ-CP",
            )


class TestSyntheticBenchmarkGenerator:
    """Verifies Stage 4 Synthetic Benchmark QA Generation across 3 difficulty tiers."""

    def test_generate_three_tier_benchmark_suite(self, tmp_path: Path) -> None:
        from rag_eval.legal.ingestion.benchmark_gen import SyntheticBenchmarkGenerator
        from rag_eval.legal.schemas import LegalIntent

        parser = LegalASTParser()
        ast_root = parser.parse_document(
            doc_code="100/2019/NĐ-CP",
            raw_text=SAMPLE_DECREE_100_TEXT,
            doc_title="Nghị định 100/2019/NĐ-CP",
        )
        cphc = CPHCEngine()
        chunks, norms = cphc.process_ast(root=ast_root)
        linker = DeterministicGraphLinker()
        edges = linker.extract_edges_from_chunks(
            chunks=chunks, norms=norms, ast_root=ast_root
        )

        output_file = tmp_path / "synthetic_traffic_law_qa.jsonl"
        generator = SyntheticBenchmarkGenerator()
        qa_pairs = generator.generate_benchmark_suite(
            chunks=chunks,
            edges=edges,
            output_path=output_file,
        )

        assert len(qa_pairs) > 0
        assert output_file.exists()

        # Check JSONL file line count equals qa_pairs count
        lines = [line.strip() for line in output_file.read_text(encoding="utf-8").split("\n") if line.strip()]
        assert len(lines) == len(qa_pairs)

        # 1. Verify Tier 1
        tier1 = [qa for qa in qa_pairs if qa.tier == 1]
        assert len(tier1) >= 2
        for t1 in tier1:
            assert t1.intent == LegalIntent.INTENT_PENALTY_LOOKUP
            assert len(t1.gold_citation_paths) == 1
            assert t1.expected_fine_bounds.min_fine_vnd is not None
            assert t1.expected_fine_bounds.max_fine_vnd is not None

        # 2. Verify Tier 2
        tier2 = [qa for qa in qa_pairs if qa.tier == 2]
        assert len(tier2) >= 1
        for t2 in tier2:
            assert len(t2.gold_citation_paths) >= 1
            assert "SYN_T2" in t2.test_id

        # 3. Verify Tier 3
        tier3 = [qa for qa in qa_pairs if qa.tier == 3]
        assert len(tier3) >= 1
        for t3 in tier3:
            assert t3.intent == LegalIntent.INTENT_PRIORITY_CONFLICT
            assert t3.is_exempt is True

    @pytest.mark.asyncio
    async def test_pipeline_generate_benchmark_integration(self, tmp_path: Path) -> None:
        pipeline = LegalIngestionPipeline()
        output_file = tmp_path / "pipeline_benchmarks.jsonl"
        result = await pipeline.ingest_text(
            doc_code="100/2019/NĐ-CP",
            raw_text=SAMPLE_DECREE_100_TEXT,
            doc_title="Nghị định 100/2019",
            generate_benchmark=True,
            benchmark_output_path=output_file,
        )

        assert len(result.benchmarks) > 0
        assert output_file.exists()
        assert any(b.tier == 1 for b in result.benchmarks)
        assert any(b.tier == 2 for b in result.benchmarks)
        assert any(b.tier == 3 for b in result.benchmarks)


class TestTemporalASTDiffEngine:
    """Verifies incremental temporal AST diffing and amendment application."""

    def test_diff_and_apply_amendment_decree_123(self) -> None:
        from rag_eval.legal.ingestion.pipeline import TemporalASTDiffEngine

        parser = LegalASTParser()
        cphc = CPHCEngine()
        linker = DeterministicGraphLinker()
        diff_engine = TemporalASTDiffEngine(
            grammar=VietnameseLegalGrammar,
            parser=parser,
            cphc=cphc,
            linker=linker,
        )

        root = parser.parse_document("100/2019/NĐ-CP", SAMPLE_DECREE_100_TEXT)
        base_chunks, _ = cphc.process_ast(root)

        result = diff_engine.diff_and_apply_amendment(
            base_chunks=base_chunks,
            amending_doc_code="123/2021/NĐ-CP",
            amending_raw_text=SAMPLE_AMENDMENT_DECREE_123_TEXT,
            amending_effective_date="2022-01-01",
        )

        assert len(result.new_chunks) > 0
        assert result.base_doc_code == "100/2019/NĐ-CP"
        assert result.amending_doc_code == "123/2021/NĐ-CP"
        assert len(result.modifies_edges) > 0
        assert any(
            e["relation_type"] == GraphRelationType.MODIFIES_AND_REPLACES.value
            for e in result.modifies_edges
        )

    @pytest.mark.asyncio
    async def test_pipeline_apply_amendment_integration(self) -> None:
        pipeline = LegalIngestionPipeline()
        root = pipeline.parser.parse_document("100/2019/NĐ-CP", SAMPLE_DECREE_100_TEXT)
        base_chunks, _ = pipeline.cphc.process_ast(root)

        result = await pipeline.apply_amendment(
            base_chunks=base_chunks,
            amending_doc_code="123/2021/NĐ-CP",
            amending_raw_text=SAMPLE_AMENDMENT_DECREE_123_TEXT,
            amending_effective_date="2022-01-01",
        )

        assert len(result.new_chunks) > 0
        assert len(result.all_active_chunks) >= len(base_chunks)

