r"""Deterministic Cross-Reference Graph Linker for Vietnamese Traffic Law.

Constructs typed, directed graph edges across the decoupled normative triad:
- Law (Luật GTĐB 2008 / TTATGTĐB 2024)
- Decree (Nghị định 100/2019, 123/2021, 168/2024)
- National Technical Regulation (QCVN 41:2019/BGTVT)

Extracts all 9 statutory relationship types:
1. DEFINES_SANCTION_FOR ($Node_{Decree} \to Node_{Law}$)
2. HAS_ADDITIONAL_SANCTION ($Node_{Decree\_Violation} \to Node_{Decree\_Supp}$)
3. REFERENCES_TECHNICAL_STANDARD ($Node_{Decree} \to Node_{QCVN}$)
4. MODIFIES_AND_REPLACES ($Node_{Amending\_Decree} \to Node_{Base\_Decree}$)
5. REPEALS ($Node_{Amending} \to Node_{Repealed}$)
6. OVERRIDES_PRIORITY ($Node_{Police/Emergency} \to Node_{Light/Sign/Marking}$)
7. EXEMPTS_CONDITION ($Node_{Exception} \to Node_{General\_Rule}$)
8. GUIDES ($Node_{Circular} \to Node_{Decree/Law}$)
9. DEFINES_TERM ($Node_{Definition} \to Node_{Rule}$)
"""

from __future__ import annotations

import re
from typing import Any

from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar
from rag_eval.legal.ingestion.parser import ASTNode, sanitize_ltree_label
from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    GraphRelationType,
    LegalNormExtraction,
    NormRole,
    canonical_doc_slug,
)


class DeterministicGraphLinker:
    """High-precision cross-precision extraction engine for legal knowledge graphs."""

    QCVN_DOC_SLUG: str = canonical_doc_slug("QCVN 41:2019/BGTVT")  # doc_qcvn_41_2019
    LUAT_GTDB_DOC_SLUG: str = canonical_doc_slug("Luật GTĐB 2008")  # doc_luat_gtdb_2008
    LUAT_TTATGTDB_DOC_SLUG: str = canonical_doc_slug("Luật TTATGTĐB 2024")  # doc_luat_ttatgtdb_2024

    def __init__(
        self, grammar: type[VietnameseLegalGrammar] = VietnameseLegalGrammar
    ) -> None:
        self.grammar = grammar

    @staticmethod
    def _resolve_qcvn_appendix_tag(sign_code: str) -> str:
        """Maps QCVN 41:2019 sign or marking codes to their corresponding technical appendix tag.

        Supports all classification families:
        - DP (Hết cấm), P (Biển cấm) -> app_b (Phụ lục B)
        - W (Cảnh báo và nguy hiểm) -> app_c (Phụ lục C)
        - RE (Hết hiệu lệnh), R (Biển hiệu lệnh) -> app_d (Phụ lục D)
        - IE (Chỉ dẫn cao tốc), I (Biển chỉ dẫn) -> app_e (Phụ lục E)
        - S (Biển phụ) -> app_f (Phụ lục F)
        - M or numeric (Vạch kẻ đường) -> app_g (Phụ lục G)
        """
        clean = sign_code.upper().strip()
        if clean.startswith(("DP", "P")):
            return "app_b"
        if clean.startswith("W"):
            return "app_c"
        if clean.startswith(("RE", "R")):
            return "app_d"
        if clean.startswith(("IE", "I")):
            return "app_e"
        if clean.startswith("S"):
            return "app_f"
        if clean.startswith(("M", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9")):
            return "app_g"
        return "app_b"

    def extract_edges_from_chunks(
        self,
        chunks: list[CanonicalFullyQualifiedChunk],
        norms: list[LegalNormExtraction] | None = None,
        ast_root: ASTNode | None = None,
    ) -> list[dict[str, Any]]:
        """Scans chunks and extracts directed statutory graph edges across all 9 relation types."""
        edges: list[dict[str, Any]] = []
        if not chunks:
            return edges

        # Pre-index supplementary sanction clauses and points per (doc_code, article_number)
        supp_map = self._build_supplementary_sanctions_index(chunks, ast_root)

        # Pre-index defined terms for DEFINES_TERM relation
        term_map = self._build_defined_terms_index(chunks, ast_root)

        for chunk in chunks:
            # 1. REFERENCES_TECHNICAL_STANDARD (Sign and Marking references)
            edges.extend(self._extract_technical_standard_edges(chunk))

            # 2. DEFINES_SANCTION_FOR (Decree sanctions Law duties)
            edges.extend(self._extract_sanction_for_law_edges(chunk))

            # 3. HAS_ADDITIONAL_SANCTION (Links violation to supplementary sanction - FIND-12 FIX)
            edges.extend(
                self._extract_additional_sanction_edges(chunk, supp_map)
            )

            # 4. MODIFIES_AND_REPLACES (Amending decree references)
            edges.extend(self._extract_modifies_replaces_edges(chunk))

            # 5. REPEALS (Explicit statutory repeals and abolishments)
            edges.extend(self._extract_repeal_edges(chunk))

            # 6. OVERRIDES_PRIORITY (Emergency exemptions & Signal hierarchy)
            edges.extend(self._extract_priority_override_edges(chunk))

            # 7. EXEMPTS_CONDITION (Specific conditional exclusion clauses)
            edges.extend(self._extract_exemption_edges(chunk))

            # 8. GUIDES (Circulars guiding Decree/Law execution)
            edges.extend(self._extract_guides_edges(chunk))

            # 9. DEFINES_TERM (Statutory definitions referencing operational rules)
            edges.extend(self._extract_defines_term_edges(chunk, term_map))

        return edges

    def _build_supplementary_sanctions_index(
        self,
        chunks: list[CanonicalFullyQualifiedChunk],
        ast_root: ASTNode | None = None,
    ) -> dict[tuple[str, int], list[tuple[str, str, str]]]:
        """Maps (doc_code, article_number) -> list of (clause_or_point_path, raw_text, point_letter)."""
        supp_index: dict[tuple[str, int], list[tuple[str, str, str]]] = {}

        # 1. Scan chunks for supplementary sanctions
        for c in chunks:
            if c.article_number is None:
                continue
            key = (c.document_code, c.article_number)
            text_lower = c.verbatim_text.lower()
            is_supp = (
                c.norm_role
                in (
                    NormRole.SANCTION_SUPPLEMENTARY,
                    NormRole.SANCTION_POINT_DEDUCTION,
                    NormRole.REMEDIAL_MEASURE,
                )
                or "xử phạt bổ sung" in text_lower
                or "hình thức xử phạt bổ sung" in text_lower
                or "tước quyền sử dụng giấy phép lái xe" in text_lower
                or "tước quyền sử dụng gplx" in text_lower
                or ("bị trừ" in text_lower and "điểm" in text_lower)
            )
            if is_supp:
                supp_index.setdefault(key, []).append(
                    (c.hierarchy_path, c.verbatim_text, c.point_letter or "")
                )

        # 2. If ast_root provided, complement with AST Clause nodes
        if ast_root:
            for art_node in ast_root.find_nodes_by_level("ARTICLE"):
                art_num = art_node.metadata.get("article_number")
                if not art_num:
                    continue
                key = (ast_root.index_label, art_num)
                for cl_node in art_node.children:
                    if cl_node.level == "CLAUSE":
                        cl_text_lower = cl_node.raw_text.lower()
                        if (
                            "xử phạt bổ sung" in cl_text_lower
                            or "hình thức xử phạt bổ sung" in cl_text_lower
                        ):
                            supp_index.setdefault(key, []).append(
                                (cl_node.full_path, cl_node.raw_text, "")
                            )
        return supp_index

    def _build_defined_terms_index(
        self,
        chunks: list[CanonicalFullyQualifiedChunk],
        ast_root: ASTNode | None = None,
    ) -> dict[str, str]:
        """Maps defined term (lowercase) -> definition node path."""
        term_map: dict[str, str] = {}
        for c in chunks:
            if (
                "giải thích từ ngữ" in c.synthesized_prefix.lower()
                or "định nghĩa" in c.synthesized_prefix.lower()
            ):
                m = re.search(
                    r"“([^”]+)”|\"([^\"]+)\"|^[0-9a-zđ\.\)\s]+([A-ZÀ-Ỹa-zà-ỹ\s]+)\s+là\b",
                    c.verbatim_text,
                )
                if m:
                    term = (
                        m.group(1) or m.group(2) or m.group(3) or ""
                    ).strip().lower()
                    if len(term) >= 3:
                        term_map[term] = c.hierarchy_path
        return term_map

    def _extract_technical_standard_edges(
        self, chunk: CanonicalFullyQualifiedChunk
    ) -> list[dict[str, Any]]:
        """1. REFERENCES_TECHNICAL_STANDARD: Maps sign and marking citations to standardized QCVN slugs."""
        edges: list[dict[str, Any]] = []

        # Signs
        for sign in chunk.referenced_entities.qcvn_signs:
            clean_sign = sign.upper().strip()
            sign_slug = sanitize_ltree_label(clean_sign)
            app_tag = self._resolve_qcvn_appendix_tag(clean_sign)
            target_path = f"{self.QCVN_DOC_SLUG}.{app_tag}.{sign_slug}"
            edges.append(
                {
                    "source_chunk_id": chunk.chunk_id,
                    "target_chunk_id": None,
                    "source_path": chunk.hierarchy_path,
                    "target_path": target_path,
                    "target_external_ref": f"QCVN 41:2019/BGTVT - Biển {clean_sign}",
                    "relation_type": GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value,
                    "description": f"Dẫn chiếu quy chuẩn kỹ thuật biển báo {clean_sign}",
                    "citation_text": chunk.verbatim_text,
                    "confidence_score": 1.000,
                    "condition_expression": None,
                }
            )

        # Markings
        for marking in chunk.referenced_entities.qcvn_markings:
            clean_m = marking.strip()
            m_slug = sanitize_ltree_label(clean_m)
            target_path = f"{self.QCVN_DOC_SLUG}.app_g.{m_slug}"
            edges.append(
                {
                    "source_chunk_id": chunk.chunk_id,
                    "target_chunk_id": None,
                    "source_path": chunk.hierarchy_path,
                    "target_path": target_path,
                    "target_external_ref": f"QCVN 41:2019/BGTVT - Vạch {clean_m}",
                    "relation_type": GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value,
                    "description": f"Dẫn chiếu quy chuẩn kỹ thuật vạch kẻ đường {clean_m}",
                    "citation_text": chunk.verbatim_text,
                    "confidence_score": 1.000,
                    "condition_expression": None,
                }
            )
        return edges

    def _extract_sanction_for_law_edges(
        self, chunk: CanonicalFullyQualifiedChunk
    ) -> list[dict[str, Any]]:
        """2. DEFINES_SANCTION_FOR: Maps decree penalties to Law duties."""
        edges: list[dict[str, Any]] = []
        for law_ref in chunk.referenced_entities.law_articles:
            art_match = re.search(r"Điều\s+(\d+)", law_ref, re.IGNORECASE)
            if art_match:
                art_num = art_match.group(1)
                doc_slug = (
                    self.LUAT_TTATGTDB_DOC_SLUG
                    if "2024" in law_ref or "TTATGTĐB" in law_ref
                    else self.LUAT_GTDB_DOC_SLUG
                )
                target_path = f"{doc_slug}.a{art_num}"
                edges.append(
                    {
                        "source_chunk_id": chunk.chunk_id,
                        "target_chunk_id": None,
                        "source_path": chunk.hierarchy_path,
                        "target_path": target_path,
                        "target_external_ref": f"Luật Giao thông đường bộ - Điều {art_num}",
                        "relation_type": GraphRelationType.DEFINES_SANCTION_FOR.value,
                        "description": f"Xử phạt vi phạm quy tắc quy định tại Điều {art_num} Luật GTĐB",
                        "citation_text": law_ref,
                        "confidence_score": 0.950,
                        "condition_expression": None,
                    }
                )
        return edges

    def _extract_additional_sanction_edges(
        self,
        chunk: CanonicalFullyQualifiedChunk,
        supp_map: dict[tuple[str, int], list[tuple[str, str, str]]],
    ) -> list[dict[str, Any]]:
        """3. HAS_ADDITIONAL_SANCTION: Fixes FIND-12 by resolving true supplementary clause AST path."""
        edges: list[dict[str, Any]] = []
        has_susp = (
            chunk.additional_sanctions.license_suspension_months_min is not None
            or chunk.additional_sanctions.demerit_points is not None
            or chunk.additional_sanctions.vehicle_impoundment_days is not None
        )
        if not has_susp or chunk.article_number is None:
            return edges

        key = (chunk.document_code, chunk.article_number)
        candidates = supp_map.get(key, [])

        resolved_target_path: str | None = None
        # Try matching specific point
        if chunk.clause_number and chunk.point_letter:
            for path, text, _pt in candidates:
                # Check if this supplementary point references our clause/point
                pt_pattern = rf"điểm\s+[a-zđ,\s]*\b{re.escape(chunk.point_letter.lower())}\b.*khoản\s+{chunk.clause_number}"
                cl_pattern = rf"khoản\s+{chunk.clause_number}\b"
                if re.search(pt_pattern, text, re.IGNORECASE) or (
                    re.search(cl_pattern, text, re.IGNORECASE)
                ):
                    resolved_target_path = path
                    break

        if not resolved_target_path and candidates:
            # Pick first candidate that is not the source chunk itself
            for path, _, _ in candidates:
                if path != chunk.hierarchy_path:
                    resolved_target_path = path
                    break

        # Fallback: Construct canonical supplementary clause path under same article
        if not resolved_target_path:
            prefix_path = (
                chunk.hierarchy_path.rsplit(".c", 1)[0]
                if ".c" in chunk.hierarchy_path
                else chunk.hierarchy_path
            )
            resolved_target_path = f"{prefix_path}.c_supp"

        # Guarantee no self-loop
        if resolved_target_path == chunk.hierarchy_path:
            resolved_target_path = f"{chunk.hierarchy_path}.c_supp"

        susp_desc: list[str] = []
        if chunk.additional_sanctions.license_suspension_months_min:
            susp_desc.append(
                f"Tước GPLX từ {chunk.additional_sanctions.license_suspension_months_min} "
                f"đến {chunk.additional_sanctions.license_suspension_months_max or chunk.additional_sanctions.license_suspension_months_min} tháng"
            )
        if chunk.additional_sanctions.demerit_points:
            susp_desc.append(
                f"Trừ {chunk.additional_sanctions.demerit_points} điểm GPLX"
            )
        if chunk.additional_sanctions.vehicle_impoundment_days:
            susp_desc.append(
                f"Tạm giữ phương tiện {chunk.additional_sanctions.vehicle_impoundment_days} ngày"
            )

        edges.append(
            {
                "source_chunk_id": chunk.chunk_id,
                "target_chunk_id": None,
                "source_path": chunk.hierarchy_path,
                "target_path": resolved_target_path,
                "target_external_ref": f"Điều {chunk.article_number} Khoản Xử phạt bổ sung",
                "relation_type": GraphRelationType.HAS_ADDITIONAL_SANCTION.value,
                "description": "; ".join(susp_desc)
                or "Hình thức xử phạt bổ sung và trừ điểm GPLX",
                "citation_text": chunk.verbatim_text,
                "confidence_score": 0.980,
                "condition_expression": None,
            }
        )
        return edges

    def _extract_modifies_replaces_edges(
        self, chunk: CanonicalFullyQualifiedChunk
    ) -> list[dict[str, Any]]:
        """4. MODIFIES_AND_REPLACES: Links amending decrees to base decrees."""
        edges: list[dict[str, Any]] = []
        for amend in chunk.referenced_entities.amending_decrees:
            amend_slug = canonical_doc_slug(amend)
            edges.append(
                {
                    "source_chunk_id": chunk.chunk_id,
                    "target_chunk_id": None,
                    "source_path": chunk.hierarchy_path,
                    "target_path": amend_slug,
                    "target_external_ref": f"Nghị định sửa đổi {amend}",
                    "relation_type": GraphRelationType.MODIFIES_AND_REPLACES.value,
                    "description": f"Quy định được sửa đổi, bổ sung bởi {amend}",
                    "citation_text": chunk.verbatim_text,
                    "confidence_score": 1.000,
                    "condition_expression": None,
                }
            )

        # Check in-text references to modified articles across combined context
        text_to_scan = f"{chunk.synthesized_prefix}\n{chunk.lead_sentence or ''}\n{chunk.verbatim_text}\n{chunk.contextualized_text}"
        m = re.search(
            r"sửa\s+đổi[,\s\bvà]+bổ\s+sung\s+(?:(?:các\s+)?(?:điểm\s+)?([a-zđ,\s\bvà]+)[\s,]+)?(?:khoản\s+(\d+)[\s,]+)?điều\s+(\d+)(?:[\s,]+(?:của\s+)?(?:nghị\s+định|luật|thông\s+tư)?\s*(?:số\s*)?([0-9/A-ZÀ-Ỹa-zà-ỹĐđ\-]+))?",
            text_to_scan,
            re.IGNORECASE,
        )
        if m:
            pt, cl, art, doc = m.groups()
            doc_str = doc or "100/2019/NĐ-CP"
            doc_slug = canonical_doc_slug(doc_str)
            target_path = f"{doc_slug}.a{art}"
            if cl:
                target_path += f".c{cl}"
            if pt:
                pt_clean = pt.strip().split(",")[0].strip()
                if pt_clean:
                    target_path += f".p_{pt_clean.lower()}"
            edges.append(
                {
                    "source_chunk_id": chunk.chunk_id,
                    "target_chunk_id": None,
                    "source_path": chunk.hierarchy_path,
                    "target_path": target_path,
                    "target_external_ref": f"Nghị định {doc_str} - Điều {art}",
                    "relation_type": GraphRelationType.MODIFIES_AND_REPLACES.value,
                    "description": f"Sửa đổi, bổ sung Điều {art} Nghị định {doc_str}",
                    "citation_text": chunk.verbatim_text,
                    "confidence_score": 1.000,
                    "condition_expression": None,
                }
            )
        return edges

    def _extract_repeal_edges(
        self, chunk: CanonicalFullyQualifiedChunk
    ) -> list[dict[str, Any]]:
        """5. REPEALS: Links abolishing clauses to repealed statutory provisions."""
        edges: list[dict[str, Any]] = []
        m = re.search(
            r"(?:bãi\s+bỏ|hủy\s+bỏ|hết\s+hiệu\s+lực)\s+(?:quy\s+định\s+tại\s+)?(?:(?:các\s+)?(?:điểm\s+)?([a-zđ,\s\bvà]+),\s*)?(?:khoản\s+(\d+),\s*)?(?:điều\s+(\d+)\s+)?(?:của\s+)?(?:Nghị\s+định|Luật|Thông\s+tư)?\s*(?:số\s*)?([0-9/A-ZÀ-Ỹa-zà-ỹĐđ\-]+)",
            chunk.verbatim_text,
            re.IGNORECASE,
        )
        if m:
            pt, cl, art, doc = m.groups()
            doc_slug = sanitize_ltree_label(doc)
            target_path = f"doc_{doc_slug}"
            if art:
                target_path += f".a{art}"
            if cl:
                target_path += f".c{cl}"
            if pt:
                pt_clean = pt.strip().split(",")[0].strip()
                if pt_clean:
                    target_path += f".p_{pt_clean.lower()}"
            edges.append(
                {
                    "source_chunk_id": chunk.chunk_id,
                    "target_chunk_id": None,
                    "source_path": chunk.hierarchy_path,
                    "target_path": target_path,
                    "target_external_ref": f"Văn bản bãi bỏ {doc}",
                    "relation_type": GraphRelationType.REPEALS.value,
                    "description": f"Bãi bỏ quy định tại {doc}",
                    "citation_text": chunk.verbatim_text,
                    "confidence_score": 0.990,
                    "condition_expression": None,
                }
            )
        return edges

    def _extract_priority_override_edges(
        self, chunk: CanonicalFullyQualifiedChunk
    ) -> list[dict[str, Any]]:
        """6. OVERRIDES_PRIORITY: Links emergency exemptions and signal priority hierarchies."""
        edges: list[dict[str, Any]] = []
        if chunk.exceptions_and_overrides.has_exception:
            clause_lower = (
                chunk.exceptions_and_overrides.exception_clause_text or ""
            ).lower()
            verbatim_lower = chunk.verbatim_text.lower()
            is_emergency = (
                "xe ưu tiên" in clause_lower
                or "khẩn cấp" in clause_lower
                or "xe ưu tiên" in verbatim_lower
                or "cứu thương" in verbatim_lower
                or "chữa cháy" in verbatim_lower
            )
            if is_emergency:
                edges.append(
                    {
                        "source_chunk_id": chunk.chunk_id,
                        "target_chunk_id": None,
                        "source_path": chunk.hierarchy_path,
                        "target_path": f"{self.LUAT_GTDB_DOC_SLUG}.a22",
                        "target_external_ref": "Điều 22 Luật Giao thông đường bộ (Quyền ưu tiên)",
                        "relation_type": GraphRelationType.OVERRIDES_PRIORITY.value,
                        "description": "Hiệu lực ưu tiên của xe ưu tiên đang làm nhiệm vụ khẩn cấp",
                        "citation_text": chunk.exceptions_and_overrides.exception_clause_text
                        or chunk.verbatim_text,
                        "confidence_score": 0.990,
                        "condition_expression": "Xe ưu tiên đang thực hiện nhiệm vụ khẩn cấp",
                    }
                )
        return edges

    def _extract_exemption_edges(
        self, chunk: CanonicalFullyQualifiedChunk
    ) -> list[dict[str, Any]]:
        """7. EXEMPTS_CONDITION: Links conditional exclusion clauses to specific exempted rules."""
        edges: list[dict[str, Any]] = []
        text_to_scan = ""
        if (
            chunk.exceptions_and_overrides.has_exception
            and chunk.exceptions_and_overrides.exception_clause_text
        ):
            text_to_scan = (
                chunk.exceptions_and_overrides.exception_clause_text
            )
        elif "trừ" in chunk.verbatim_text.lower():
            text_to_scan = chunk.verbatim_text

        if text_to_scan:
            m = re.search(
                r"(?:tại\s+)?(?:điểm\s+([a-zđ])[\s,]+)?(?:khoản\s+(\d+)[\s,]+)?điều\s+(\d+)",
                text_to_scan,
                re.IGNORECASE,
            )
            if m:
                pt, cl, art = m.groups()
                doc_prefix = chunk.hierarchy_path.split(".")[0]
                target_path = f"{doc_prefix}.a{art}"
                if cl:
                    target_path += f".c{cl}"
                if pt:
                    target_path += f".p_{pt.lower()}"
                edges.append(
                    {
                        "source_chunk_id": chunk.chunk_id,
                        "target_chunk_id": None,
                        "source_path": chunk.hierarchy_path,
                        "target_path": target_path,
                        "target_external_ref": f"Điều khoản miễn trừ tại Điều {art}",
                        "relation_type": GraphRelationType.EXEMPTS_CONDITION.value,
                        "description": f"Loại trừ hành vi vi phạm: {text_to_scan}",
                        "citation_text": text_to_scan,
                        "confidence_score": 0.950,
                        "condition_expression": text_to_scan,
                    }
                )
        return edges

    def _extract_guides_edges(
        self, chunk: CanonicalFullyQualifiedChunk
    ) -> list[dict[str, Any]]:
        """8. GUIDES: Links Circulars (Thông tư) to governed Decrees/Laws."""
        edges: list[dict[str, Any]] = []
        m = re.search(
            r"(?:hướng\s+dẫn|quy\s+định\s+chi\s+tiết)\s+(?:thi\s+hành\s+)?(?:điều\s+(\d+)\s+)?(?:Nghị\s+định|Luật)\s+([0-9/A-Z\-]+)",
            chunk.verbatim_text,
            re.IGNORECASE,
        )
        if m:
            art, doc = m.groups()
            doc_slug = sanitize_ltree_label(doc)
            target_path = f"doc_{doc_slug}" + (f".a{art}" if art else "")
            edges.append(
                {
                    "source_chunk_id": chunk.chunk_id,
                    "target_chunk_id": None,
                    "source_path": chunk.hierarchy_path,
                    "target_path": target_path,
                    "target_external_ref": f"Văn bản được hướng dẫn: {doc}",
                    "relation_type": GraphRelationType.GUIDES.value,
                    "description": f"Thông tư hướng dẫn thi hành {doc}",
                    "citation_text": chunk.verbatim_text,
                    "confidence_score": 0.950,
                    "condition_expression": None,
                }
            )
        return edges

    def _extract_defines_term_edges(
        self,
        chunk: CanonicalFullyQualifiedChunk,
        term_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        """9. DEFINES_TERM: Links statutory definition nodes to operational rule chunks."""
        edges: list[dict[str, Any]] = []
        chunk_text_lower = chunk.verbatim_text.lower()
        for term, def_path in term_map.items():
            if def_path != chunk.hierarchy_path and term in chunk_text_lower:
                edges.append(
                    {
                        "source_chunk_id": chunk.chunk_id,
                        "target_chunk_id": None,
                        "source_path": def_path,
                        "target_path": chunk.hierarchy_path,
                        "target_external_ref": f"Thuật ngữ pháp lý: {term}",
                        "relation_type": GraphRelationType.DEFINES_TERM.value,
                        "description": f"Giải thích thuật ngữ '{term}' áp dụng cho quy định này",
                        "citation_text": term,
                        "confidence_score": 0.920,
                        "condition_expression": None,
                    }
                )
        return edges
