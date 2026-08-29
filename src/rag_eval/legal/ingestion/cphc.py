"""Context-Preserving Hierarchical Chunking (CPHC) Engine.

Transforms statutory AST nodes into Canonical Fully Qualified Chunks (CFQC) and LegalNormExtraction
models, guaranteeing that all atomic sub-points inherit parent Article titles, actor/vehicle scopes,
and Clause lead sentences with precise, point-level supplementary sanction scoping.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Literal

from rag_eval.legal.ingestion.grammar import (
    VietnameseLegalGrammar,
    parse_vnd_amount,
)
from rag_eval.legal.ingestion.parser import ASTNode, sanitize_ltree_label
from rag_eval.legal.schemas import (
    ActorCategory,
    AdditionalSanctions,
    CanonicalFullyQualifiedChunk,
    ExceptionMetadata,
    FineBounds,
    LegalNormExtraction,
    NormRole,
    ReferencedEntity,
    VehicleCategory,
    ViolationCategory,
    ViolationType,
    canonical_doc_slug,
    expand_vehicle_category,
)


def synthesize_cphc_prefix(
    doc_code: str,
    doc_title: str,
    chapter_title: str | None,
    article_num: int,
    article_title: str,
    clause_num: int | None,
    clause_lead: str | None,
    point_letter: str | None,
    point_body: str,
    additional_sanctions_summary: str | None = None,
    ast_node: ASTNode | None = None,
    hierarchy_path: str | None = None,
    custom_path: str | None = None,
) -> tuple[str, str]:
    """Synthesizes deterministic ltree path and human/LLM contextualized text."""
    if ast_node is not None:
        ltree_path = ast_node.full_path
    elif hierarchy_path is not None or custom_path is not None:
        ltree_path = hierarchy_path or custom_path or ""
    else:
        root_slug = canonical_doc_slug(doc_code)
        path_parts: list[str] = [root_slug]
        if article_num:
            path_parts.append(f"a{article_num}")
        if clause_num:
            path_parts.append(f"c{clause_num}")
        if point_letter:
            path_parts.append(f"p_{sanitize_ltree_label(point_letter)}")
        ltree_path = ".".join(path_parts)

    # Context Header lines
    header_lines = [
        f"[VĂN BẢN]: {doc_title} (Số hiệu: {doc_code})",
    ]
    if chapter_title:
        header_lines.append(f"[CHƯƠNG]: {chapter_title}")

    if ast_node is not None and ast_node.level in ("SIGN_SPEC", "MARKING_SPEC"):
        if ast_node.lead_sentence:
            header_lines.append(ast_node.lead_sentence)
    else:
        header_lines.append(f"[ĐIỀU {article_num}]: {article_title}")

        if clause_num and clause_lead:
            # Strip leading numbering if present to prevent double indexing
            clean_lead = re.sub(r"^\d+\.\s*", "", clause_lead.strip())
            header_lines.append(f"[KHOẢN {clause_num} - LỜI DẪN]: {clean_lead}")

    prefix = "\n".join(header_lines)

    # Body line
    body_line = (
        f"[ĐIỂM {point_letter}]: {point_body.strip()}"
        if point_letter
        else point_body.strip()
    )
    components = [prefix, body_line]
    if additional_sanctions_summary:
        components.append(
            f"[CHẾ TÀI BỔ SUNG & TRỪ ĐIỂM]: {additional_sanctions_summary.strip()}"
        )

    contextualized_text = "\n".join(components)
    return ltree_path, contextualized_text


@dataclass
class SupplementaryRule:
    """Structured representation of an indexed supplementary sanction sub-rule."""

    clause_num: int
    point_letter: str | None
    target_clause: int
    target_points: list[str]
    raw_text: str
    ast_path: str


class SupplementarySanctionParser:
    """Parses and indexes article supplementary sanction clauses with point-level granularity."""

    TARGET_REF_REGEX = re.compile(
        r"(?:(?:các\s+)?điểm\s+(?P<pts>[a-zđA-ZĐ0-9](?:[,\s–\-\.]+(?:và|hoặc|đến|các|điểm|[a-zđA-ZĐ0-9])){0,10})\s+)?khoản\s+(?P<cl>\d+)",
        re.IGNORECASE,
    )

    @classmethod
    def index_article_supplementary_rules(
        cls, art_node: ASTNode
    ) -> list[SupplementaryRule]:
        """Extracts and parses all supplementary sanction sub-rules from an Article AST."""
        rules: list[SupplementaryRule] = []
        for cl_node in art_node.children:
            if cl_node.level != "CLAUSE":
                continue
            text_lower = cl_node.raw_text.lower()
            if (
                "xử phạt bổ sung" not in text_lower
                and "hình thức xử phạt bổ sung" not in text_lower
                and "khắc phục hậu quả" not in text_lower
            ):
                continue

            cl_num = cl_node.metadata.get("clause_number", 0)

            # If clause has child points, inspect each point
            if cl_node.children:
                for pt_node in cl_node.children:
                    if pt_node.level != "POINT":
                        continue
                    pt_letter = pt_node.metadata.get("point_letter")
                    matches = list(cls.TARGET_REF_REGEX.finditer(pt_node.raw_text))
                    matched_any = False
                    for m in matches:
                        target_cl = int(m.group("cl"))
                        pts_raw = m.group("pts")
                        target_pts: list[str] = []
                        if pts_raw:
                            target_pts = [
                                p.lower()
                                for p in re.findall(
                                    r"\b([a-zđ])\b", pts_raw.lower()
                                )
                                if p.lower() not in (
                                    "va",
                                    "cac",
                                    "diem",
                                    "điem",
                                    "tai",
                                    "theo",
                                    "quy",
                                    "dinh",
                                    "đinh",
                                )
                            ]
                        rules.append(
                            SupplementaryRule(
                                clause_num=cl_num,
                                point_letter=pt_letter,
                                target_clause=target_cl,
                                target_points=target_pts,
                                raw_text=pt_node.raw_text.strip(),
                                ast_path=pt_node.full_path,
                            )
                        )
                        matched_any = True

                    if not matched_any:
                        # Fallback for standalone clause references
                        cl_fallback = re.search(
                            r"khoản\s+(\d+)", pt_node.raw_text, re.IGNORECASE
                        )
                        if cl_fallback:
                            rules.append(
                                SupplementaryRule(
                                    clause_num=cl_num,
                                    point_letter=pt_letter,
                                    target_clause=int(cl_fallback.group(1)),
                                    target_points=[],
                                    raw_text=pt_node.raw_text.strip(),
                                    ast_path=pt_node.full_path,
                                )
                            )
            else:
                # Standalone clause without points
                matches = list(cls.TARGET_REF_REGEX.finditer(cl_node.raw_text))
                for m in matches:
                    target_cl = int(m.group("cl"))
                    pts_raw = m.group("pts")
                    target_pts = []
                    if pts_raw:
                        target_pts = [
                            p.lower()
                            for p in re.findall(
                                r"\b([a-zđ])\b", pts_raw.lower()
                            )
                            if p.lower() not in (
                                "va",
                                "cac",
                                "diem",
                                "điem",
                                "tai",
                                "theo",
                                "quy",
                                "dinh",
                                "đinh",
                            )
                        ]
                    rules.append(
                        SupplementaryRule(
                            clause_num=cl_num,
                            point_letter=None,
                            target_clause=target_cl,
                            target_points=target_pts,
                            raw_text=cl_node.raw_text.strip(),
                            ast_path=cl_node.full_path,
                        )
                    )
        return rules

    @classmethod
    def match_rules(
        cls,
        rules: list[SupplementaryRule],
        clause_num: int | None,
        point_letter: str | None,
    ) -> list[SupplementaryRule]:
        """Finds matching supplementary rules for a specific violation clause and point."""
        if clause_num is None:
            return []
        matched: list[SupplementaryRule] = []
        pt_clean = point_letter.lower() if point_letter else None

        for rule in rules:
            if rule.target_clause == clause_num:
                if not rule.target_points:
                    # Applies to the entire clause
                    matched.append(rule)
                elif pt_clean and pt_clean in rule.target_points:
                    # Specific point match
                    matched.append(rule)

        return matched


class CPHCEngine:
    """Context-Preserving Hierarchical Chunking Engine."""

    def __init__(
        self, grammar: type[VietnameseLegalGrammar] = VietnameseLegalGrammar
    ) -> None:
        self.grammar = grammar

    def process_ast(
        self,
        root: ASTNode,
        document_id: str | None = None,
        effective_date: str = "2020-01-15",
        expiration_date: str | None = None,
    ) -> tuple[list[CanonicalFullyQualifiedChunk], list[LegalNormExtraction]]:
        """Processes an AST hierarchy into CanonicalFullyQualifiedChunks and LegalNormExtractions."""
        doc_id = document_id or str(
            uuid.uuid5(uuid.NAMESPACE_DNS, root.index_label)
        )
        doc_code = root.index_label
        doc_title = root.title

        chunks: list[CanonicalFullyQualifiedChunk] = []
        extractions: list[LegalNormExtraction] = []

        # Index supplementary sanction rules per article
        article_rules_map: dict[int, list[SupplementaryRule]] = {}
        for art_node in root.find_nodes_by_level("ARTICLE"):
            art_num = art_node.metadata.get("article_number", 0)
            article_rules_map[art_num] = (
                SupplementarySanctionParser.index_article_supplementary_rules(
                    art_node
                )
            )

        # Traverse and chunk
        self._traverse_and_chunk(
            node=root,
            doc_id=doc_id,
            doc_code=doc_code,
            doc_title=doc_title,
            current_chapter=None,
            current_article=None,
            current_clause=None,
            article_rules_map=article_rules_map,
            effective_date=effective_date,
            expiration_date=expiration_date,
            out_chunks=chunks,
            out_extractions=extractions,
        )

        return chunks, extractions

    def _traverse_and_chunk(
        self,
        node: ASTNode,
        doc_id: str,
        doc_code: str,
        doc_title: str,
        current_chapter: ASTNode | None,
        current_article: ASTNode | None,
        current_clause: ASTNode | None,
        article_rules_map: dict[int, list[SupplementaryRule]],
        effective_date: str,
        expiration_date: str | None,
        out_chunks: list[CanonicalFullyQualifiedChunk],
        out_extractions: list[LegalNormExtraction],
    ) -> None:
        """Recursive traversal generating CFQC chunks for atomic nodes."""
        if node.level == "CHAPTER":
            current_chapter = node
        elif node.level == "ARTICLE":
            current_article = node
        elif node.level == "CLAUSE":
            current_clause = node

        # Determine if this node is an atomic chunk target
        is_point = node.level == "POINT"
        is_standalone_clause = node.level == "CLAUSE" and not node.children
        is_sign_spec = node.level in ("SIGN_SPEC", "MARKING_SPEC")

        if is_point or is_standalone_clause or is_sign_spec:
            art_num = (
                current_article.metadata.get("article_number", 1)
                if current_article
                else 1
            )
            art_title = current_article.title if current_article else doc_title
            cl_num = (
                current_clause.metadata.get("clause_number", 1)
                if current_clause
                else None
            )
            cl_lead = current_clause.lead_sentence if current_clause else None
            pt_letter = (
                node.metadata.get("point_letter", None) if is_point else None
            )

            # Strictly match supplementary sanctions for this specific clause & point
            matched_rules = SupplementarySanctionParser.match_rules(
                rules=article_rules_map.get(art_num, []),
                clause_num=cl_num,
                point_letter=pt_letter,
            )
            supp_summary_text: str | None = None
            if matched_rules:
                supp_summary_text = "\n".join(r.raw_text for r in matched_rules)

            # Synthesize prefix using exact AST node full_path (FIND-08)
            ltree_path, contextualized_text = synthesize_cphc_prefix(
                doc_code=doc_code,
                doc_title=doc_title,
                chapter_title=current_chapter.title
                if current_chapter
                else None,
                article_num=art_num,
                article_title=art_title,
                clause_num=cl_num,
                clause_lead=cl_lead,
                point_letter=pt_letter,
                point_body=node.raw_text,
                additional_sanctions_summary=supp_summary_text,
                ast_node=node,
            )

            # Metadata extraction
            combined_context = f"{art_title}\n{cl_lead or ''}\n{node.raw_text}\n{supp_summary_text or ''}"
            actor = self._infer_actor(combined_context)
            vehicle_types = self._extract_vehicle_types(combined_context, actor=actor)
            violation_cats, violation_types = self._extract_violations(
                combined_context
            )
            fine_bounds = self._extract_fine_bounds(cl_lead or node.raw_text)

            # Extract additional sanctions strictly from matched rules or direct text (FIND-09)
            additional_sanctions = self._extract_additional_sanctions(
                supp_text=supp_summary_text or "",
                direct_text=node.raw_text,
            )
            exceptions = self._extract_exceptions(node.raw_text)
            referenced = self._extract_references(node.raw_text)

            all_norm_roles = self._infer_norm_roles(
                node, fine_bounds, additional_sanctions, node.raw_text
            )
            norm_role = all_norm_roles[0]
            node.metadata["norm_roles"] = [r.value for r in all_norm_roles]
            if len(all_norm_roles) > 1:
                node.metadata["secondary_norm_roles"] = [
                    r.value for r in all_norm_roles[1:]
                ]

            chunk_id = f"chk_{uuid.uuid5(uuid.NAMESPACE_DNS, ltree_path)}"

            cfqc = CanonicalFullyQualifiedChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                document_code=doc_code,
                hierarchy_path=ltree_path,
                article_number=art_num,
                article_index=f"Điều {art_num}"
                if current_article
                else art_title,
                clause_number=cl_num,
                point_letter=pt_letter,
                synthesized_prefix=node.lead_sentence
                or f"[{node.level}]: {node.title}"
                if is_sign_spec
                else f"[ĐIỀU {art_num}]: {art_title}\n[KHOẢN {cl_num}]: {cl_lead or ''}",
                verbatim_text=node.raw_text,
                contextualized_text=contextualized_text,
                norm_role=norm_role,
                primary_actor=actor,
                vehicle_types=vehicle_types,
                violation_categories=violation_cats,
                violation_types=violation_types,
                fine_bounds=fine_bounds,
                additional_sanctions=additional_sanctions,
                exceptions_and_overrides=exceptions,
                referenced_entities=referenced,
                effective_date=effective_date,
                expiry_date=expiration_date,
                is_active=True,
            )
            out_chunks.append(cfqc)

            norm_ext = LegalNormExtraction(
                chunk_id=chunk_id,
                hierarchy_path=ltree_path,
                document_code=doc_code,
                document_type="NGHI_DINH" if "NĐ-CP" in doc_code else "LUAT",
                article_number=art_num,
                article_index=f"Điều {art_num}"
                if current_article
                else art_title,
                clause_number=cl_num,
                point_letter=pt_letter,
                norm_role=norm_role,
                primary_actor=actor,
                vehicle_types=vehicle_types,
                violation_categories=violation_cats,
                violation_types=violation_types,
                behavior_summary=node.raw_text[:200].strip(),
                fine_bounds=fine_bounds,
                additional_sanctions=additional_sanctions,
                remedial_measures=[],
                exceptions_and_overrides=exceptions,
                referenced_entities=referenced,
                contextualized_text=contextualized_text,
                verbatim_text=node.raw_text,
            )
            out_extractions.append(norm_ext)

        # Recurse children
        for child in node.children:
            self._traverse_and_chunk(
                node=child,
                doc_id=doc_id,
                doc_code=doc_code,
                doc_title=doc_title,
                current_chapter=current_chapter,
                current_article=current_article,
                current_clause=current_clause,
                article_rules_map=article_rules_map,
                effective_date=effective_date,
                expiration_date=expiration_date,
                out_chunks=out_chunks,
                out_extractions=out_extractions,
            )

    def _extract_vehicle_types(
        self, text: str, actor: ActorCategory | None = None
    ) -> list[VehicleCategory]:
        """Infers target vehicle categories from textual context."""
        if actor in (ActorCategory.PEDESTRIAN, ActorCategory.PASSENGER):
            return []

        text_lower = text.lower()
        matched: set[VehicleCategory] = set()

        if (
            "xe ô tô" in text_lower
            or "ô tô con" in text_lower
            or "xe con" in text_lower
        ):
            for cat in expand_vehicle_category("CAR"):
                matched.add(cat)
        if "xe ô tô tải" in text_lower or "xe tải" in text_lower:
            matched.add(VehicleCategory.CAR_TRUCK)
            matched.add(VehicleCategory.CAR_TRACTOR)
        if (
            "xe mô tô" in text_lower
            or "xe gắn máy" in text_lower
            or "xe máy" in text_lower
        ):
            for cat in expand_vehicle_category("TWO_WHEELER"):
                if cat in (
                    VehicleCategory.MOTORCYCLE,
                    VehicleCategory.MOPED,
                    VehicleCategory.E_MOPED,
                ):
                    matched.add(cat)
        if "xe máy điện" in text_lower:
            matched.add(VehicleCategory.E_MOPED)
        if "xe đạp điện" in text_lower:
            matched.add(VehicleCategory.E_BICYCLE)
        if "xe đạp" in text_lower or "xe thô sơ" in text_lower:
            matched.add(VehicleCategory.BICYCLE_PRIMITIVE)
            matched.add(VehicleCategory.E_BICYCLE)
        if "xe máy chuyên dùng" in text_lower:
            matched.add(VehicleCategory.SPECIALIZED_MACHINE)
        if (
            "xe ưu tiên" in text_lower
            or "cứu thương" in text_lower
            or "chữa cháy" in text_lower
        ):
            matched.add(VehicleCategory.PRIORITY_VEHICLE)

        if not matched:
            return []
        return sorted(matched, key=lambda x: x.value)

    def _extract_violations(
        self, text: str
    ) -> tuple[list[ViolationCategory], list[ViolationType]]:
        """Infers violation categories and granular types from text."""
        text_lower = text.lower()
        cats: set[ViolationCategory] = set()
        types: set[ViolationType] = set()

        if (
            "nồng độ cồn" in text_lower
            or "ma túy" in text_lower
            or "rượu, bia" in text_lower
        ):
            cats.add(ViolationCategory.ALCOHOL_DRUGS)
            types.add(ViolationType.ALC_BRACKET_1)

        if "tốc độ" in text_lower or "chạy quá tốc độ" in text_lower:
            cats.add(ViolationCategory.SPEED_DISTANCE)
            types.add(ViolationType.SPEED_OVER_10_20)

        if "đèn tín hiệu" in text_lower or "đèn đỏ" in text_lower:
            cats.add(ViolationCategory.SIGNAL_COMPLIANCE)
            types.add(ViolationType.RED_LIGHT)

        if (
            "ngược chiều" in text_lower
            or "đường cấm" in text_lower
            or "làn đường" in text_lower
        ):
            cats.add(ViolationCategory.LANE_DIRECTION)
            if "ngược chiều" in text_lower:
                types.add(ViolationType.OPPOSITE_DIRECTION)
            if "làn đường" in text_lower:
                types.add(ViolationType.WRONG_LANE)

        if "dừng xe" in text_lower or "đỗ xe" in text_lower:
            cats.add(ViolationCategory.STOP_PARK)
            types.add(ViolationType.ILLEGAL_STOP_PARK)

        if "quá tải" in text_lower or "chở quá" in text_lower:
            cats.add(ViolationCategory.LOAD_PASSENGER)
            types.add(ViolationType.OVERLOAD_VEHICLE)

        if (
            "mũ bảo hiểm" in text_lower
            or "dây an toàn" in text_lower
            or "điện thoại" in text_lower
        ):
            cats.add(ViolationCategory.EQUIPMENT_SAFETY)
            if "mũ bảo hiểm" in text_lower:
                types.add(ViolationType.HELMET_VIOLATION)
            if "điện thoại" in text_lower:
                types.add(ViolationType.PHONE_HANDHELD)

        if not cats:
            cats.add(ViolationCategory.SIGNAL_COMPLIANCE)

        return sorted(cats, key=lambda x: x.value), sorted(
            types, key=lambda x: x.value
        )

    def _extract_fine_bounds(self, text: str) -> FineBounds:
        """Extracts numerical minimum and maximum fines in VND."""
        match = self.grammar.FINE_RANGE_REGEX.search(text)
        if not match:
            return FineBounds()

        min_val_str = match.group("min_val")
        min_unit = match.group("min_unit")
        max_val_str = match.group("max_val")
        max_unit = match.group("max_unit")

        # If min unit omitted, use max unit
        if not min_unit:
            min_unit = max_unit

        min_fine = parse_vnd_amount(min_val_str, min_unit)
        max_fine = parse_vnd_amount(max_val_str, max_unit)

        return FineBounds(
            min_fine_vnd=min_fine,
            max_fine_vnd=max_fine,
            average_fine_vnd=((min_fine + max_fine) // 2)
            if min_fine and max_fine
            else min_fine or max_fine,
        )

    def _extract_additional_sanctions(
        self, supp_text: str, direct_text: str = ""
    ) -> AdditionalSanctions:
        """Extracts license suspension months, impoundment days, and demerit points without cross-point bleed."""
        target_text = (
            supp_text.strip() if supp_text.strip() else direct_text.strip()
        )
        if not target_text:
            return AdditionalSanctions()

        susp_min: int | None = None
        susp_max: int | None = None
        days: int | None = None

        susp_match = self.grammar.SUSPENSION_REGEX.search(target_text)
        if susp_match:
            if susp_match.group("fixed_months"):
                m = int(susp_match.group("fixed_months"))
                susp_min, susp_max = m, m
            elif (
                susp_match.group("min_months")
                and susp_match.group("max_months")
            ):
                susp_min = int(susp_match.group("min_months"))
                susp_max = int(susp_match.group("max_months"))

        imp_match = self.grammar.IMPOUNDMENT_REGEX.search(target_text)
        if imp_match:
            days = int(imp_match.group("days"))

        demerit_val: Literal[0, 2, 3, 4, 6, 8, 10, 12] | None = None
        dem_match = self.grammar.DEMERIT_REGEX.search(target_text)
        if dem_match:
            raw_pts = int(dem_match.group("points"))
            if raw_pts == 0:
                demerit_val = 0
            elif raw_pts == 2:
                demerit_val = 2
            elif raw_pts == 3:
                demerit_val = 3
            elif raw_pts == 4:
                demerit_val = 4
            elif raw_pts == 6:
                demerit_val = 6
            elif raw_pts == 8:
                demerit_val = 8
            elif raw_pts == 10:
                demerit_val = 10
            elif raw_pts == 12:
                demerit_val = 12

        return AdditionalSanctions(
            license_suspension_months_min=susp_min,
            license_suspension_months_max=susp_max,
            vehicle_impoundment_days=days,
            demerit_points=demerit_val,
        )

    def _extract_exceptions(self, text: str) -> ExceptionMetadata:
        """Extracts exception rules and emergency vehicle overrides."""
        match = self.grammar.EXCEPTION_REGEX.search(text)
        text_lower = text.lower()
        has_priority_ref = (
            "xe ưu tiên" in text_lower
            or "khẩn cấp" in text_lower
            or "cứu thương" in text_lower
            or "chữa cháy" in text_lower
        )

        if match:
            clause_text = (
                match.group("clause_text").strip() or match.group(0).strip()
            )
            is_emergency = (
                "xe ưu tiên" in clause_text.lower()
                or "khẩn cấp" in clause_text.lower()
                or has_priority_ref
            )
            return ExceptionMetadata(
                has_exception=True,
                exception_type="EMERGENCY_VEHICLE"
                if is_emergency
                else "STATUTORY_EXCEPTION",
                exception_clause_text=clause_text,
                overridden_by=["POLICE_COMMAND", "EMERGENCY_MISSION"]
                if is_emergency
                else ["POLICE_COMMAND"],
                exempt_vehicle_categories=[VehicleCategory.PRIORITY_VEHICLE]
                if is_emergency
                else [],
            )
        elif has_priority_ref:
            return ExceptionMetadata(
                has_exception=True,
                exception_type="EMERGENCY_VEHICLE",
                exception_clause_text="Quy định liên quan đến xe ưu tiên",
                overridden_by=["POLICE_COMMAND", "EMERGENCY_MISSION"],
                exempt_vehicle_categories=[VehicleCategory.PRIORITY_VEHICLE],
            )

        return ExceptionMetadata(has_exception=False)

    def _extract_references(self, text: str) -> ReferencedEntity:
        """Extracts cross-references to laws, sign codes, markings, and amending decrees."""
        laws: list[str] = []
        signs: list[str] = []
        markings: list[str] = []
        amends: list[str] = []

        for m in self.grammar.ARTICLE_REF_REGEX.finditer(text):
            art = m.group("article")
            cl = m.group("clause")
            pt = m.group("point")
            doc = m.group("doc_ref")
            ref_str = f"Điều {art}"
            if cl:
                ref_str = f"Khoản {cl} {ref_str}"
            if pt:
                ref_str = f"Điểm {pt} {ref_str}"
            if doc:
                ref_str = f"{ref_str} ({doc})"

            # Only append to law_articles if it is a law or external document reference
            matched_slice = text[
                max(0, m.start() - 25) : min(len(text), m.end() + 30)
            ].lower()
            if doc or "luật" in matched_slice:
                laws.append(ref_str)

        for m in self.grammar.SIGN_REF_REGEX.finditer(text):
            if m.group("sign_code"):
                signs.append(m.group("sign_code").upper())
            elif m.group("sign_name"):
                signs.append(m.group("sign_name"))

        for m in self.grammar.MARKING_REF_REGEX.finditer(text):
            markings.append(m.group("marking_code"))

        for m in self.grammar.DECREE_AMENDMENT_REGEX.finditer(text):
            amends.append(m.group("doc_code"))

        return ReferencedEntity(
            law_articles=laws,
            qcvn_signs=signs,
            qcvn_markings=markings,
            amending_decrees=amends,
        )

    def _infer_norm_roles(
        self,
        node: ASTNode,
        fine_bounds: FineBounds,
        additional_sanctions: AdditionalSanctions,
        text: str,
    ) -> list[NormRole]:
        """Infers all applicable normative roles under formal legal theory for multi-penalty clauses."""
        text_lower = text.lower()
        roles: list[NormRole] = []
        if (
            fine_bounds.min_fine_vnd is not None
            or fine_bounds.max_fine_vnd is not None
        ):
            roles.append(NormRole.SANCTION_PRINCIPAL)
        if (
            "xử phạt bổ sung" in text_lower
            or "hình thức xử phạt bổ sung" in text_lower
            or additional_sanctions.license_suspension_months_min is not None
            or additional_sanctions.license_suspension_months_max is not None
            or additional_sanctions.vehicle_impoundment_days is not None
        ):
            roles.append(NormRole.SANCTION_SUPPLEMENTARY)
        if (
            additional_sanctions.demerit_points is not None
            or ("bị trừ" in text_lower and "điểm" in text_lower)
        ):
            roles.append(NormRole.SANCTION_POINT_DEDUCTION)
        if (
            "khắc phục hậu quả" in text_lower
            or "biện pháp khắc phục" in text_lower
        ):
            roles.append(NormRole.REMEDIAL_MEASURE)
        if node.level in ("SIGN_SPEC", "MARKING_SPEC"):
            roles.append(NormRole.HYPOTHESIS_CONDITION)
        if (
            "định nghĩa" in node.title.lower()
            or "giải thích từ ngữ" in node.title.lower()
        ):
            roles.append(NormRole.PRESCRIPTION_PERMISSION)
        if "phải" in text_lower or "có trách nhiệm" in text_lower:
            roles.append(NormRole.PRESCRIPTION_DUTY)

        if not roles:
            roles.append(NormRole.PRESCRIPTION_PROHIBITION)
        return roles

    def _infer_norm_role(
        self,
        node: ASTNode,
        fine_bounds: FineBounds,
        additional_sanctions: AdditionalSanctions,
        text: str,
    ) -> NormRole:
        """Infers the primary normative role under formal legal theory."""
        roles = self._infer_norm_roles(
            node=node,
            fine_bounds=fine_bounds,
            additional_sanctions=additional_sanctions,
            text=text,
        )
        return roles[0]

    def _infer_actor(self, text: str) -> ActorCategory:
        """Infers target actor category."""
        text_lower = text.lower()
        if "người đi bộ" in text_lower:
            return ActorCategory.PEDESTRIAN
        if "người ngồi trên xe" in text_lower or "hành khách" in text_lower:
            return ActorCategory.PASSENGER
        if "chủ phương tiện" in text_lower or "chủ xe" in text_lower:
            return ActorCategory.VEHICLE_OWNER
        if "doanh nghiệp vận tải" in text_lower or "hợp tác xã" in text_lower:
            return ActorCategory.TRANSPORT_BUSINESS
        return ActorCategory.DRIVER
