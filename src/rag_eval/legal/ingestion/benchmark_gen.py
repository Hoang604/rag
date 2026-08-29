"""Stage 4 Synthetic QA Benchmark Generator for Vietnamese Traffic Law RAG.

Generates verified 3-tier multi-hop synthetic benchmark evaluation QA pairs
with deterministic gold citation paths (Chain of Custody) from ingested statutory AST nodes,
CFQC chunks, and knowledge graph edges conforming to docs/04_ingestion_and_chunking_strategy.md#L791.

Tiers:
- Tier 1: Single-hop factual queries grounded in article/clause.
- Tier 2: Boundary/penalty calculation queries with vehicle & speed/BAC parameters or technical standard lookups.
- Tier 3: Multi-hop norm precedence & conflict resolution scenarios.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rag_eval.legal.ingestion.grammar import VietnameseLegalGrammar
from rag_eval.legal.schemas import (
    CanonicalFullyQualifiedChunk,
    FineBounds,
    GraphRelationType,
    LegalIntent,
    SyntheticQAPair,
    VehicleCategory,
    ViolationCategory,
    ViolationType,
)

logger = logging.getLogger(__name__)

VEHICLE_DISPLAY_NAMES: dict[VehicleCategory, str] = {
    VehicleCategory.CAR_PASSENGER: "xe ô tô con",
    VehicleCategory.CAR_TRUCK: "xe ô tô tải",
    VehicleCategory.CAR_BUS: "xe ô tô khách",
    VehicleCategory.CAR_TRACTOR: "xe ô tô đầu kéo",
    VehicleCategory.MOTORCYCLE: "xe mô tô, xe máy",
    VehicleCategory.MOPED: "xe gắn máy",
    VehicleCategory.E_MOPED: "xe máy điện",
    VehicleCategory.E_BICYCLE: "xe đạp điện",
    VehicleCategory.BICYCLE_PRIMITIVE: "xe đạp, xe thô sơ",
    VehicleCategory.SPECIALIZED_MACHINE: "xe máy chuyên dùng",
    VehicleCategory.PRIORITY_VEHICLE: "xe ưu tiên",
}


def _clean_statutory_behavior_text(text: str) -> str:
    """Cleans point indices, leading punctuation, and trailing semicolons from statutory text."""
    clean = text.strip()
    if clean.endswith((";", ".")):
        clean = clean[:-1].strip()
    if len(clean) >= 3 and clean[1] == ")" and clean[0].isalpha():
        clean = clean[2:].strip()
    return clean


class SyntheticBenchmarkGenerator:
    """Stage 4 Automated Synthetic QA Benchmark Generator producing 3-tier benchmark suites."""

    def __init__(
        self, grammar: type[VietnameseLegalGrammar] = VietnameseLegalGrammar
    ) -> None:
        self.grammar = grammar

    def generate_tier1_factual_qa(
        self,
        chunks: list[CanonicalFullyQualifiedChunk],
        max_samples: int | None = None,
    ) -> list[SyntheticQAPair]:
        """Generates Tier 1 single-hop factual QA pairs grounded in a single article/clause."""
        qa_pairs: list[SyntheticQAPair] = []

        for chunk in chunks:
            if (
                chunk.fine_bounds.min_fine_vnd is None
                or chunk.fine_bounds.min_fine_vnd <= 0
            ):
                continue

            veh_cat = chunk.vehicle_types[0] if chunk.vehicle_types else None
            veh_name = (
                VEHICLE_DISPLAY_NAMES.get(veh_cat, "xe cơ giới")
                if veh_cat
                else "người điều khiển phương tiện"
            )
            clean_behavior = _clean_statutory_behavior_text(chunk.verbatim_text)

            if len(clean_behavior) < 10:
                continue

            test_id = f"SYN_T1_{chunk.hierarchy_path.replace('.', '_')}"
            query = f"Mức phạt đối với người điều khiển {veh_name} thực hiện hành vi: {clean_behavior} là bao nhiêu?"

            qa_pairs.append(
                SyntheticQAPair(
                    test_id=test_id,
                    tier=1,
                    intent=LegalIntent.INTENT_PENALTY_LOOKUP,
                    query=query,
                    context_scenario=f"Hành vi vi phạm quy tắc giao thông theo {chunk.doc_title} ({chunk.hierarchy_path})",
                    gold_citation_paths=[chunk.hierarchy_path],
                    primary_vehicle=veh_cat,
                    violation_categories=list(chunk.violation_categories),
                    violation_types=list(chunk.violation_types),
                    expected_fine_bounds=chunk.fine_bounds,
                    expected_additional_sanctions=chunk.additional_sanctions,
                    is_exempt=False,
                    metadata={
                        "document_code": chunk.document_code,
                        "article_index": chunk.article_index,
                        "clause_index": chunk.clause_index or "",
                        "point_index": chunk.point_index or "",
                    },
                )
            )

            if max_samples is not None and len(qa_pairs) >= max_samples:
                break

        return qa_pairs

    def generate_tier2_boundary_qa(
        self,
        chunks: list[CanonicalFullyQualifiedChunk],
        edges: list[dict[str, Any]] | None = None,
        max_samples: int | None = None,
    ) -> list[SyntheticQAPair]:
        """Generates Tier 2 boundary, numerical calculation, and technical standard multi-hop QA pairs."""
        qa_pairs: list[SyntheticQAPair] = []
        edges_list = edges or []

        chunk_by_path: dict[str, CanonicalFullyQualifiedChunk] = {
            c.hierarchy_path: c for c in chunks
        }

        # 1. Technical Standard & Sign/Marking Cross-Reference Queries
        for edge in edges_list:
            if (
                edge.get("relation_type")
                == GraphRelationType.REFERENCES_TECHNICAL_STANDARD.value
            ):
                src_path = edge.get("source_path", "")
                tgt_path = edge.get("target_path", "")
                chunk = chunk_by_path.get(src_path)
                if not chunk:
                    continue

                veh_cat = chunk.vehicle_types[0] if chunk.vehicle_types else None
                veh_name = (
                    VEHICLE_DISPLAY_NAMES.get(veh_cat, "xe cơ giới")
                    if veh_cat
                    else "người điều khiển phương tiện"
                )
                clean_behavior = _clean_statutory_behavior_text(chunk.verbatim_text)

                test_id = f"SYN_T2_TECH_{src_path.replace('.', '_')}"
                query = f"Người điều khiển {veh_name} không tuân thủ biển báo/vạch kẻ ({edge.get('target_external_ref', 'báo hiệu đường bộ')}) khi {clean_behavior} bị xử phạt như thế nào?"

                gold_paths = [tgt_path, src_path] if tgt_path else [src_path]

                qa_pairs.append(
                    SyntheticQAPair(
                        test_id=test_id,
                        tier=2,
                        intent=LegalIntent.INTENT_TECHNICAL_STANDARD,
                        query=query,
                        context_scenario=f"Tra cứu quy chuẩn kỹ thuật và mức phạt kết hợp ({edge.get('target_external_ref', '')})",
                        gold_citation_paths=gold_paths,
                        primary_vehicle=veh_cat,
                        violation_categories=list(chunk.violation_categories),
                        violation_types=list(chunk.violation_types),
                        expected_fine_bounds=chunk.fine_bounds,
                        expected_additional_sanctions=chunk.additional_sanctions,
                        is_exempt=False,
                        metadata={
                            "target_external_ref": edge.get("target_external_ref", ""),
                            "source_path": src_path,
                            "target_path": tgt_path,
                        },
                    )
                )

        # 2. Speed Bracket Boundary Parameter Queries
        speed_delta_specs: list[tuple[ViolationType, float, float, float]] = [
            (ViolationType.SPEED_OVER_5_10, 50.0, 58.0, 8.0),
            (ViolationType.SPEED_OVER_10_20, 50.0, 68.0, 18.0),
            (ViolationType.SPEED_OVER_20_35, 60.0, 85.0, 25.0),
            (ViolationType.SPEED_OVER_35_PLUS, 80.0, 125.0, 45.0),
        ]

        for chunk in chunks:
            for v_type, limit, recorded, delta in speed_delta_specs:
                if v_type in chunk.violation_types or (
                    chunk.violation_categories
                    and ViolationCategory.SPEED_DISTANCE
                    in chunk.violation_categories
                    and f"{int(delta)}" in chunk.verbatim_text
                ):
                    veh_cat = chunk.vehicle_types[0] if chunk.vehicle_types else None
                    veh_name = (
                        VEHICLE_DISPLAY_NAMES.get(veh_cat, "xe ô tô")
                        if veh_cat
                        else "xe ô tô"
                    )

                    test_id = f"SYN_T2_SPEED_{chunk.hierarchy_path.replace('.', '_')}_{v_type.value}"
                    query = f"Người điều khiển {veh_name} chạy tốc độ {recorded:.0f} km/h trên đoạn đường giới hạn {limit:.0f} km/h (vượt quá {delta:.0f} km/h) thì bị xử phạt bao nhiêu và có bị tước GPLX không?"

                    qa_pairs.append(
                        SyntheticQAPair(
                            test_id=test_id,
                            tier=2,
                            intent=LegalIntent.INTENT_PENALTY_LOOKUP,
                            query=query,
                            context_scenario=f"Tình huống chạy quá tốc độ: tốc độ giới hạn {limit} km/h, tốc độ ghi nhận {recorded} km/h (quá {delta} km/h)",
                            gold_citation_paths=[chunk.hierarchy_path],
                            primary_vehicle=veh_cat,
                            violation_categories=[ViolationCategory.SPEED_DISTANCE],
                            violation_types=[v_type],
                            expected_fine_bounds=chunk.fine_bounds,
                            expected_additional_sanctions=chunk.additional_sanctions,
                            is_exempt=False,
                            metadata={
                                "speed_limit_kmh": limit,
                                "recorded_speed_kmh": recorded,
                                "speed_delta_kmh": delta,
                            },
                        )
                    )

        # 3. Alcohol Concentration Boundary Queries
        alc_specs: list[tuple[ViolationType, float, str]] = [
            (ViolationType.ALC_BRACKET_1, 0.15, "chưa vượt quá 0.25 mg/1 lít khí thở"),
            (
                ViolationType.ALC_BRACKET_2,
                0.35,
                "vượt quá 0.25 mg đến 0.40 mg/1 lít khí thở",
            ),
            (ViolationType.ALC_BRACKET_3, 0.55, "vượt quá 0.40 mg/1 lít khí thở"),
        ]

        for chunk in chunks:
            for v_type, reading, desc in alc_specs:
                if v_type in chunk.violation_types or (
                    ViolationCategory.ALCOHOL_DRUGS in chunk.violation_categories
                    and (
                        f"{reading:.2f}" in chunk.verbatim_text
                        or desc in chunk.verbatim_text
                    )
                ):
                    veh_cat = chunk.vehicle_types[0] if chunk.vehicle_types else None
                    veh_name = (
                        VEHICLE_DISPLAY_NAMES.get(veh_cat, "xe ô tô")
                        if veh_cat
                        else "xe ô tô"
                    )

                    test_id = f"SYN_T2_ALC_{chunk.hierarchy_path.replace('.', '_')}_{v_type.value}"
                    query = f"Người điều khiển {veh_name} có kết quả đo nồng độ cồn {reading:.2f} mg/l khí thở ({desc}) bị xử phạt như thế nào?"

                    qa_pairs.append(
                        SyntheticQAPair(
                            test_id=test_id,
                            tier=2,
                            intent=LegalIntent.INTENT_PENALTY_LOOKUP,
                            query=query,
                            context_scenario=f"Tình huống vi phạm nồng độ cồn: {reading} mg/l khí thở",
                            gold_citation_paths=[chunk.hierarchy_path],
                            primary_vehicle=veh_cat,
                            violation_categories=[ViolationCategory.ALCOHOL_DRUGS],
                            violation_types=[v_type],
                            expected_fine_bounds=chunk.fine_bounds,
                            expected_additional_sanctions=chunk.additional_sanctions,
                            is_exempt=False,
                            metadata={
                                "alcohol_breath_mg_l": reading,
                                "bracket_description": desc,
                            },
                        )
                    )

        # 4. Supplementary Sanction Multi-Hop Queries
        for edge in edges_list:
            if (
                edge.get("relation_type")
                == GraphRelationType.HAS_ADDITIONAL_SANCTION.value
            ):
                src_path = edge.get("source_path", "")
                tgt_path = edge.get("target_path", "")
                chunk = chunk_by_path.get(src_path)
                if not chunk:
                    continue

                veh_cat = chunk.vehicle_types[0] if chunk.vehicle_types else None
                veh_name = (
                    VEHICLE_DISPLAY_NAMES.get(veh_cat, "xe cơ giới")
                    if veh_cat
                    else "người điều khiển phương tiện"
                )
                clean_behavior = _clean_statutory_behavior_text(chunk.verbatim_text)

                test_id = f"SYN_T2_SUPP_{src_path.replace('.', '_')}"
                query = f"Người lái {veh_name} có hành vi '{clean_behavior}' ngoài bị phạt tiền còn bị áp dụng hình thức phạt bổ sung và trừ điểm bằng lái xe như thế nào?"

                gold_paths = (
                    [src_path, tgt_path]
                    if tgt_path and tgt_path != src_path
                    else [src_path]
                )

                qa_pairs.append(
                    SyntheticQAPair(
                        test_id=test_id,
                        tier=2,
                        intent=LegalIntent.INTENT_PENALTY_LOOKUP,
                        query=query,
                        context_scenario=f"Truy xuất chế tài phạt bổ sung liên kết ({src_path} -> {tgt_path})",
                        gold_citation_paths=gold_paths,
                        primary_vehicle=veh_cat,
                        violation_categories=list(chunk.violation_categories),
                        violation_types=list(chunk.violation_types),
                        expected_fine_bounds=chunk.fine_bounds,
                        expected_additional_sanctions=chunk.additional_sanctions,
                        is_exempt=False,
                        metadata={
                            "source_path": src_path,
                            "target_path": tgt_path,
                        },
                    )
                )

        if max_samples is not None:
            return qa_pairs[:max_samples]
        return qa_pairs

    def generate_tier3_override_qa(
        self,
        chunks: list[CanonicalFullyQualifiedChunk],
        edges: list[dict[str, Any]] | None = None,
        max_samples: int | None = None,
    ) -> list[SyntheticQAPair]:
        """Generates Tier 3 multi-hop statutory precedence and conflict override QA pairs."""
        qa_pairs: list[SyntheticQAPair] = []

        for chunk in chunks:
            # 1. Emergency Vehicle Priority Exemption Scenarios
            if (
                chunk.exceptions_and_overrides.has_exception
                or "xe ưu tiên" in chunk.contextualized_text.lower()
                or "ưu tiên" in chunk.verbatim_text.lower()
                or any(
                    v
                    in (
                        ViolationType.RED_LIGHT,
                        ViolationType.PROHIBITED_ZONE,
                        ViolationType.OPPOSITE_DIRECTION,
                    )
                    for v in chunk.violation_types
                )
            ):
                clean_behavior = _clean_statutory_behavior_text(chunk.verbatim_text)
                test_id = (
                    f"SYN_T3_EMERGENCY_{chunk.hierarchy_path.replace('.', '_')}"
                )

                query = f"Xe cứu thương (hoặc xe chữa cháy) đang phát tín hiệu còi và đèn ưu tiên đi làm nhiệm vụ khẩn cấp có hành vi '{clean_behavior}' thì có bị xử phạt vi phạm hành chính không?"

                gold_paths = ["doc_luat_gtdb_2008.a22", chunk.hierarchy_path]

                qa_pairs.append(
                    SyntheticQAPair(
                        test_id=test_id,
                        tier=3,
                        intent=LegalIntent.INTENT_PRIORITY_CONFLICT,
                        query=query,
                        context_scenario="Xe ưu tiên (cứu thương/chữa cháy) đang làm nhiệm vụ khẩn cấp theo Điều 22 Luật Giao thông đường bộ",
                        gold_citation_paths=gold_paths,
                        primary_vehicle=VehicleCategory.PRIORITY_VEHICLE,
                        violation_categories=list(chunk.violation_categories),
                        violation_types=list(chunk.violation_types),
                        expected_fine_bounds=FineBounds(
                            min_fine_vnd=0, max_fine_vnd=0, average_fine_vnd=0
                        ),
                        expected_additional_sanctions=chunk.additional_sanctions,
                        is_exempt=True,
                        dominant_authority="EMERGENCY_MISSION",
                        metadata={
                            "statutory_basis": "Điều 22 Luật Giao thông đường bộ 2008 / Luật TTATGTĐB 2024",
                            "overridden_chunk": chunk.hierarchy_path,
                        },
                    )
                )

            # 2. Signal Precedence Hierarchy Scenarios (Police Command > Traffic Light > Signs > Markings)
            if (
                ViolationType.RED_LIGHT in chunk.violation_types
                or "đèn tín hiệu" in chunk.verbatim_text.lower()
                or "hiệu lệnh" in chunk.verbatim_text.lower()
            ):
                test_id = f"SYN_T3_POLICE_OVERRIDE_{chunk.hierarchy_path.replace('.', '_')}"
                query = (
                    "Tại nơi đường giao nhau có đèn tín hiệu giao thông màu đỏ nhưng có Cảnh sát giao thông "
                    "ra hiệu lệnh cho phép xe tiếp tục đi thẳng, người điều khiển xe đi thẳng theo hiệu lệnh của CSGT "
                    "có bị xử phạt lỗi không chấp hành đèn tín hiệu giao thông không?"
                )

                gold_paths = [
                    "doc_luat_gtdb_2008.a11",
                    "doc_qcvn_41_2019.a4",
                    chunk.hierarchy_path,
                ]

                qa_pairs.append(
                    SyntheticQAPair(
                        test_id=test_id,
                        tier=3,
                        intent=LegalIntent.INTENT_PRIORITY_CONFLICT,
                        query=query,
                        context_scenario="Xung đột hiệu lệnh: Hiệu lệnh CSGT đối lập với tín hiệu đèn đỏ (QCVN 41:2019 Điều 4 & Luật GTĐB Điều 11)",
                        gold_citation_paths=gold_paths,
                        primary_vehicle=chunk.vehicle_types[0]
                        if chunk.vehicle_types
                        else VehicleCategory.CAR_PASSENGER,
                        violation_categories=[ViolationCategory.SIGNAL_COMPLIANCE],
                        violation_types=[
                            ViolationType.POLICE_COMMAND,
                            ViolationType.RED_LIGHT,
                        ],
                        expected_fine_bounds=FineBounds(
                            min_fine_vnd=0, max_fine_vnd=0, average_fine_vnd=0
                        ),
                        expected_additional_sanctions=chunk.additional_sanctions,
                        is_exempt=True,
                        dominant_authority="POLICE_OFFICER",
                        metadata={
                            "statutory_precedence": "POLICE_OFFICER > TRAFFIC_LIGHT > TRAFFIC_SIGN > ROAD_MARKING",
                            "controlling_norm": "QCVN 41:2019/BGTVT Điều 4 Khoản 4.1",
                        },
                    )
                )

            # 3. Explicit Exception Clause Scenarios
            if (
                chunk.exceptions_and_overrides.has_exception
                and chunk.exceptions_and_overrides.exception_clause_text
            ):
                clean_behavior = _clean_statutory_behavior_text(chunk.verbatim_text)
                exc_text = chunk.exceptions_and_overrides.exception_clause_text

                test_id = f"SYN_T3_EXC_{chunk.hierarchy_path.replace('.', '_')}"
                query = f"Hành vi '{clean_behavior}' có bị xử phạt vi phạm hành chính không nếu người điều khiển xe thuộc trường hợp: {exc_text}?"

                qa_pairs.append(
                    SyntheticQAPair(
                        test_id=test_id,
                        tier=3,
                        intent=LegalIntent.INTENT_PRIORITY_CONFLICT,
                        query=query,
                        context_scenario=f"Điều khoản loại trừ trách nhiệm: {exc_text}",
                        gold_citation_paths=[chunk.hierarchy_path],
                        primary_vehicle=chunk.vehicle_types[0]
                        if chunk.vehicle_types
                        else None,
                        violation_categories=list(chunk.violation_categories),
                        violation_types=list(chunk.violation_types),
                        expected_fine_bounds=FineBounds(
                            min_fine_vnd=0, max_fine_vnd=0, average_fine_vnd=0
                        ),
                        expected_additional_sanctions=chunk.additional_sanctions,
                        is_exempt=True,
                        dominant_authority="STATUTORY_EXCEPTION",
                        metadata={
                            "exception_clause_text": exc_text,
                        },
                    )
                )

            if max_samples is not None and len(qa_pairs) >= max_samples:
                break

        return qa_pairs

    def generate_benchmark_suite(
        self,
        chunks: list[CanonicalFullyQualifiedChunk],
        edges: list[dict[str, Any]] | None = None,
        output_path: str | Path | None = None,
        max_tier1_samples: int | None = None,
        max_tier2_samples: int | None = None,
        max_tier3_samples: int | None = None,
    ) -> list[SyntheticQAPair]:
        """Generates full 3-tier benchmark suite and optionally persists to a JSONL file."""
        edges_list = edges or []

        tier1 = self.generate_tier1_factual_qa(
            chunks=chunks, max_samples=max_tier1_samples
        )
        tier2 = self.generate_tier2_boundary_qa(
            chunks=chunks, edges=edges_list, max_samples=max_tier2_samples
        )
        tier3 = self.generate_tier3_override_qa(
            chunks=chunks, edges=edges_list, max_samples=max_tier3_samples
        )

        all_qa = tier1 + tier2 + tier3
        logger.info(
            "Generated %d synthetic benchmark QA pairs (Tier 1: %d, Tier 2: %d, Tier 3: %d)",
            len(all_qa),
            len(tier1),
            len(tier2),
            len(tier3),
        )

        if output_path is not None:
            out_file = Path(output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with out_file.open("w", encoding="utf-8") as f:
                for qa in all_qa:
                    f.write(qa.model_dump_json() + "\n")
            logger.info("Persisted synthetic benchmark suite to %s", out_file)

        return all_qa
