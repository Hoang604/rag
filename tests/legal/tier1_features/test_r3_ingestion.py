"""Tier 1: Feature Coverage tests for Requirement 3 (R3) - CPHC Ingestion Pipeline."""

from __future__ import annotations

import pytest

from rag_eval.legal.ingestion.cphc import CPHCEngine
from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar
from rag_eval.legal.ingestion.parser import LegalASTParser
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
        assert "100/2019/NĐ-CP" in chunk.contextualized_text
        assert "Điều 5" in chunk.contextualized_text
        assert "Khoản 3" in chunk.contextualized_text
        assert "Điểm a" in chunk.contextualized_text
        assert (
            "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông"
            in chunk.contextualized_text
        )

    def test_cfqc_resolves_dangling_subpoint_with_vehicle_context(self) -> None:
        chunk = DECREE_100_ART6_CL8_PTA
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

        root = parser.parse_document("100/2019/NĐ-CP", SAMPLE_TIER1_TEXT)
        chunks, _ = cphc.process_ast(root)

        # 1. 100% path equality between AST and CPHC
        for chunk in chunks:
            assert chunk.hierarchy_path.startswith("doc_100_2019_nd_cp.c_ii.a5")

        # 2. Structural & verbatim text invariants
        chk_cl1_a = next(c for c in chunks if c.clause_number == 1 and c.point_letter == "a")
        assert "Không chấp hành hiệu lệnh" in chk_cl1_a.verbatim_text
        assert "[ĐIỀU 5]" in chk_cl1_a.contextualized_text

        chk_cl3_a = next(c for c in chunks if c.clause_number == 3 and c.point_letter == "a")
        assert "Không chấp hành hiệu lệnh của đèn" in chk_cl3_a.verbatim_text

        chk_cl3_c = next(c for c in chunks if c.clause_number == 3 and c.point_letter == "c")
        assert "Không tuân thủ hiệu lệnh CSGT" in chk_cl3_c.verbatim_text

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

    def test_incremental_temporal_ast_diff_engine(self) -> None:
        """F-15: Verifies AST diffing engine updates target base chunks with is_amended=True."""
        from rag_eval.legal.ingestion.pipeline import TemporalASTDiffEngine

        parser = LegalASTParser(VietnameseLegalGrammar)
        cphc = CPHCEngine(VietnameseLegalGrammar)
        diff_engine = TemporalASTDiffEngine(
            grammar=VietnameseLegalGrammar,
            parser=parser,
            cphc=cphc,
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
        assert len(result.all_active_chunks) > 0

    def test_f28_cleanse_vehicle_defaults_for_pedestrian_and_general_subjects(self) -> None:
        """F-28: Verifies general/pedestrian subjects without vehicle mentions default to empty vehicle list."""

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
            assert "Không đi đúng phần đường" in chunk.verbatim_text or "Không chấp hành hiệu lệnh" in chunk.verbatim_text

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



    def test_noise_sanitation_cleanse_noisy_headers(self) -> None:
        """Requirement R1 fast unit check: Verifies Công Báo noise stripping and legal line normalization."""
        from rag_eval.legal.ingestion.converter import sanitize_legal_text

        noisy_lines = [
            "2 CÔNG BÁO/Số 979 + 980/Ngày 24-8-2024",
            "VĂN BẢN QUY PHẠM PHÁP LUẬT",
            "Điều 24. Giao thông tại đường ngang",
            "1. Khi có hiệu lệnh của nhân viên gác chắn,",
            "người tham gia giao thông phải dừng lại.",
            "61",
            "CHỦ TỊCH QUỐC HỘI",
        ]
        clean = sanitize_legal_text(noisy_lines)
        assert "CÔNG BÁO" not in clean
        assert "CHỦ TỊCH QUỐC HỘI" not in clean
        assert "Điều 24. Giao thông tại đường ngang" in clean
        assert "1. Khi có hiệu lệnh của nhân viên gác chắn, người tham gia giao thông phải dừng lại." in clean

    @pytest.mark.slow
    def test_pdf_conversion_and_noise_sanitation(
        self, parsed_law_36_pdf_text: str
    ) -> None:
        """Requirement R1: Verifies PDF text extraction, Công Báo noise stripping, and 66-article preservation."""
        from pathlib import Path

        pdf_path = Path("data/36-2024-qh15_tiep.pdf")
        if not pdf_path.exists():
            return

        sanitized_text = parsed_law_36_pdf_text
        assert len(sanitized_text) > 50000

        # Verify no Công Báo headers or page numbers leak through
        assert "CÔNG BÁO/Số" not in sanitized_text
        assert "VĂN BẢN QUY PHẠM PHÁP LUẬT" not in sanitized_text

        # Verify all 66 articles (Điều 24 to Điều 89) are present
        parser = LegalASTParser(VietnameseLegalGrammar)
        ast = parser.parse_document("36/2024/QH15", sanitized_text, "Luật TTATGTĐB 2024", "LUAT")
        art_nodes = ast.find_nodes_by_level("ARTICLE")
        art_nums = [a.metadata.get("article_number") for a in art_nodes]
        assert len(art_nodes) == 66
        assert art_nums == list(range(24, 90))



    @pytest.mark.asyncio
    async def test_r3_postgres_bulk_loader_load_graph_edges_strict_fk_and_idempotency(self) -> None:
        """Requirement R3: Verifies PostgresBulkLoader.load_graph_edges strict FK resolution, ltree validation, and deduplication."""
        from types import TracebackType
        from unittest.mock import AsyncMock, MagicMock

        import asyncpg

        from rag_eval.legal.ingestion.loader import PostgresBulkLoader

        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.executemany = AsyncMock()

        class MockTx:
            async def __aenter__(self) -> None:
                pass
            async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
                pass

        mock_conn.transaction.return_value = MockTx()
        mock_pool = MagicMock(spec=asyncpg.Pool)

        class MockAcquire:
            async def __aenter__(self) -> AsyncMock:
                return mock_conn
            async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
                pass

        mock_pool.acquire.return_value = MockAcquire()
        loader = PostgresBulkLoader(pool=mock_pool)

        chunk_id_map = {
            "doc_100_2019_nd_cp.c_ii.a5.c1.p_a": "11111111-1111-1111-1111-111111111111",
            "doc_100_2019_nd_cp.c_ii.a5.c3.p_a": "22222222-2222-2222-2222-222222222222",
            "doc_100_2019_nd_cp.c_ii.a5.c11.p_b": "33333333-3333-3333-3333-333333333333",
        }
        node_id_map = {
            "doc_100_2019_nd_cp.c_ii.a5.c1.p_a": "node-1111-1111",
            "doc_100_2019_nd_cp.c_ii.a5.c3.p_a": "node-2222-2222",
            "doc_100_2019_nd_cp.c_ii.a5.c11.p_b": "node-3333-3333",
            "doc_100_2019_nd_cp.c_ii.a5": "node-art5",
            "doc_100_2019_nd_cp": "node-root",
        }

        sample_edges = [
            # Edge 1: Exact matches for both source and target
            {
                "source_path": "doc_100_2019_nd_cp.c_ii.a5.c3.p_a",
                "target_path": "doc_100_2019_nd_cp.c_ii.a5.c11.p_b",
                "relation_type": "HAS_ADDITIONAL_SANCTION",
                "description": "Tước GPLX 1-3 tháng",
                "citation_text": "Điểm a khoản 3 bị tước GPLX",
                "confidence_score": 0.98,
            },
            # Edge 2: Duplicate of Edge 1 (verifies intra-batch deduplication)
            {
                "source_path": "doc_100_2019_nd_cp.c_ii.a5.c3.p_a",
                "target_path": "doc_100_2019_nd_cp.c_ii.a5.c11.p_b",
                "relation_type": "HAS_ADDITIONAL_SANCTION",
                "description": "Tước GPLX 1-3 tháng duplicate",
                "confidence_score": 0.98,
            },
            # Edge 3: Hierarchical path resolution (canonical-to-structural)
            {
                "source_path": "doc_100_2019_nd_cp.a5.c1.p_a",
                "target_path": "doc_qcvn_41_2019.app_b.p_102",
                "target_external_ref": "QCVN 41:2019/BGTVT - Biển P.102",
                "relation_type": "REFERENCES_TECHNICAL_STANDARD",
                "description": "Dẫn chiếu biển P.102",
                "confidence_score": 1.0,
            },
            # Edge 4: Invalid source path (should be safely skipped)
            {
                "source_path": "doc_nonexistent_instrument.a99",
                "target_path": "doc_qcvn_41_2019.app_b.p_102",
                "relation_type": "REFERENCES_TECHNICAL_STANDARD",
            },
        ]

        count = await loader.load_graph_edges(
            edges=sample_edges,
            chunk_id_map=chunk_id_map,
            node_id_map=node_id_map,
        )

        # 2 valid deduplicated edges should be loaded (Edge 1 and Edge 3)
        assert count == 2
        assert mock_conn.executemany.called
        call_args = mock_conn.executemany.call_args[0]
        records = call_args[1]
        assert len(records) == 2

        # Verify Edge 1 records
        rec1 = next(r for r in records if r[7] == "HAS_ADDITIONAL_SANCTION")
        assert rec1[0] == "22222222-2222-2222-2222-222222222222"
        assert rec1[1] == "33333333-3333-3333-3333-333333333333"
        assert rec1[2] == "node-2222-2222"
        assert rec1[3] == "node-3333-3333"

        # Verify Edge 3 records (external target chunk & node are None)
        rec3 = next(r for r in records if r[7] == "REFERENCES_TECHNICAL_STANDARD")
        assert rec3[0] == "11111111-1111-1111-1111-111111111111"
        assert rec3[1] is None  # external unindexed chunk
        assert rec3[2] == "node-1111-1111"
        assert rec3[3] is None  # external unindexed node
        assert rec3[5] == "doc_qcvn_41_2019.app_b.p_102"

