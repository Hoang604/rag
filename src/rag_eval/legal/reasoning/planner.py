"""Query Decomposition, Intent Classification, and DAG Planning Engine."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from rag_eval.legal.schemas import (
    ExecutionPlanDAG,
    ExtractedEntities,
    LegalIntent,
    SubGoalNode,
    SubGoalType,
    VehicleCategory,
    remove_vietnamese_diacritics,
)


class QueryPlanner:
    """Translates raw natural language traffic queries into structured entity slots and DAG plans."""

    SPEED_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*(?:km/h|kmh|km/g|cây\s*số)", re.IGNORECASE)
    SPEED_LIMIT_REGEX = re.compile(
        r"(?:tối\s+đa|giới\s+hạn|cho\s+phép|đoạn\s+đường|tốc\s+độ\s+tối\s+đa)\s*(\d+(?:\.\d+)?)\s*(?:km/h|kmh)?",
        re.IGNORECASE,
    )
    BRAC_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mg/l|mg/1l|miligam/lít|miligam/l)", re.IGNORECASE)
    BAC_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mg/100ml|miligam/100ml)", re.IGNORECASE)
    WEIGHT_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*(?:tấn|tan|kg)", re.IGNORECASE)
    SIGN_REGEX = re.compile(r"(?:biển|biển\s+báo|biển\s+hiệu|biển\s+số)\s*([P|W|R|I|S|DP]\.[0-9]+[a-z]?)", re.IGNORECASE)
    MARKING_REGEX = re.compile(r"(?:vạch|vạch\s+kẻ|vạch\s+kẻ\s+đường|vạch\s+số)\s*([0-9]+\.[0-9]+[a-z]?)", re.IGNORECASE)

    def plan(self, query: str) -> ExecutionPlanDAG:
        """Decomposes a user query into structured entity slots and execution DAG."""
        query_clean = query.strip()
        query_lower = query_clean.lower()
        query_id = f"plan_{hashlib.sha256(query_clean.encode('utf-8')).hexdigest()[:12]}"

        # 1. Intent Classification covering 6 Legal Intents
        intent = self._classify_intent(query_lower)

        # 2. Entity Extraction
        entities = self._extract_entities(query_clean, query_lower)

        # 3. Sub-Goal DAG Construction
        sub_goals, exec_order = self._construct_dag(query_clean, intent, entities)

        # 4. Ambiguity / Clarification check
        clarification_prompt = None
        if len(query_clean.split()) < 2:
            clarification_prompt = "Câu hỏi quá ngắn hoặc thiếu thông tin hành vi/phương tiện. Vui lòng cung cấp thêm chi tiết."

        return ExecutionPlanDAG(
            query_id=query_id,
            original_query=query_clean,
            primary_intent=intent,
            extracted_entities=entities,
            sub_goals=sub_goals,
            execution_order=exec_order,
            fallback_clarification_prompt=clarification_prompt,
        )

    def _classify_intent(self, query_lower: str) -> LegalIntent:
        """Classifies query into one of 6 primary LegalIntent categories."""
        # Priority Conflict Check
        if (
            ("cảnh sát" in query_lower or "csgt" in query_lower or "người điều khiển giao thông" in query_lower)
            and ("đèn" in query_lower or "biển" in query_lower or "vạch" in query_lower or "hiệu lệnh" in query_lower)
        ) or (
            "biển tạm" in query_lower and ("biển cố định" in query_lower or "vạch" in query_lower)
        ) or (
            "xe ưu tiên" in query_lower and ("đèn đỏ" in query_lower or "nhường đường" in query_lower or "xung đột" in query_lower)
        ) or (
            "nhường đường" in query_lower and "ngã tư" in query_lower
        ):
            return LegalIntent.INTENT_PRIORITY_CONFLICT

        # Technical Standard Check
        if (
            "biển" in query_lower
            and any(w in query_lower for w in ["ý nghĩa", "kích thước", "quy chuẩn", "qcvn", "hình dạng", "màu sắc", "tác dụng"])
        ) or (
            "vạch" in query_lower and any(w in query_lower for w in ["ý nghĩa", "quy chuẩn", "kích thước", "bề rộng"])
        ):
            return LegalIntent.INTENT_TECHNICAL_STANDARD

        # Procedural Timeline Check
        if any(
            w in query_lower
            for w in [
                "thời hạn",
                "thời hiệu",
                "thủ tục",
                "nộp phạt",
                "khiếu nại",
                "tước gplx trong bao lâu",
                "giữ bằng lái bao lâu",
                "tạm giữ xe bao lâu",
                "bao nhiêu ngày",
                "đóng phạt ở đâu",
                "kho bạc",
            ]
        ):
            return LegalIntent.INTENT_PROCEDURAL_TIMELINE

        # Comparative Synthesis Check
        if any(
            w in query_lower
            for w in [
                "so sánh",
                "khác nhau",
                "giữa ô tô và",
                "giữa xe máy và",
                "phân biệt",
                "mức phạt xe tải so với",
                "khác biệt mức phạt",
            ]
        ):
            return LegalIntent.INTENT_COMPARATIVE_SYNTHESIS

        # Behavior Validation Check
        if any(
            w in query_lower
            for w in [
                "hành vi",
                "đúng hay sai",
                "được phép",
                "có được",
                "có được phép",
                "vi phạm không",
                "hợp lệ không",
                "có bị coi là",
                "có phạm luật",
            ]
        ):
            return LegalIntent.INTENT_BEHAVIOR_VALIDATION

        # Default to Penalty Lookup
        return LegalIntent.INTENT_PENALTY_LOOKUP

    @staticmethod
    def _normalize_text(text: str) -> str:
        return remove_vietnamese_diacritics(text).lower().replace("_", " ")

    def _extract_entities(self, query: str, query_lower: str) -> ExtractedEntities:
        """Extracts structured numerical, code, categorical, and contextual entity slots."""
        query_unaccented = self._normalize_text(query_lower)

        # Vehicle Category Extraction
        veh_cat: VehicleCategory | None = None
        if any(
            w in query_lower or w in query_unaccented
            for w in ["xe tải", "ô tô tải", "xe ben", "xe container", "xe bồn", "xe tai", "o to tai"]
        ):
            veh_cat = VehicleCategory.CAR_TRUCK
        elif any(
            w in query_lower or w in query_unaccented
            for w in ["xe khách", "ô tô khách", "xe bus", "xe buýt", "xe 16 chỗ", "xe 29 chỗ", "xe khach", "o to khach", "xe buy"]
        ):
            veh_cat = VehicleCategory.CAR_BUS
        elif any(
            w in query_lower or w in query_unaccented
            for w in ["đầu kéo", "rơ moóc", "sơ mi rơ moóc", "xe kéo", "dau keo", "ro mooc"]
        ):
            veh_cat = VehicleCategory.CAR_TRACTOR
        elif any(
            w in query_lower or w in query_unaccented
            for w in ["ô tô con", "xe ô tô", "xe hơi", "xe con", "ô tô", "xe o to", "o to con", "o to", "xe hoi"]
        ):
            veh_cat = VehicleCategory.CAR_PASSENGER
        elif any(
            w in query_lower or w in query_unaccented
            for w in ["xe máy điện", "mô tô điện", "xe may dien", "mo to dien"]
        ):
            veh_cat = VehicleCategory.E_MOPED
        elif any(
            w in query_lower or w in query_unaccented
            for w in ["xe đạp điện", "xe dap dien"]
        ):
            veh_cat = VehicleCategory.E_BICYCLE
        elif any(
            w in query_lower or w in query_unaccented
            for w in ["xe gắn máy", "xe gan may", "moped"]
        ):
            veh_cat = VehicleCategory.MOPED
        elif any(
            w in query_lower or w in query_unaccented
            for w in ["xe máy", "mô tô", "xe 2 bánh", "xe hai bánh", "xe may", "mo to"]
        ):
            veh_cat = VehicleCategory.MOTORCYCLE
        elif any(
            w in query_lower or w in query_unaccented
            for w in ["cứu thương", "chữa cháy", "công an", "xe ưu tiên", "cuu thuong", "chua chay", "xe uu tien"]
        ):
            veh_cat = VehicleCategory.PRIORITY_VEHICLE
        elif any(
            w in query_lower or w in query_unaccented
            for w in ["xe đạp", "xích lô", "xe thô sơ", "xe dap", "xich lo", "xe tho so"]
        ):
            veh_cat = VehicleCategory.BICYCLE_PRIMITIVE
        elif any(
            w in query_lower or w in query_unaccented
            for w in ["xe chuyên dùng", "xe máy chuyên dùng", "máy xúc", "xe cẩu", "xe chuyen dung", "may xuc"]
        ):
            veh_cat = VehicleCategory.SPECIALIZED_MACHINE

        # Numeric Speed & Limit Extraction
        speed: float | None = None
        speed_m = self.SPEED_REGEX.search(query)
        if speed_m:
            try:
                speed = float(speed_m.group(1))
            except (ValueError, TypeError):
                speed = None

        limit: float | None = None
        limit_m = self.SPEED_LIMIT_REGEX.search(query)
        if limit_m:
            try:
                limit = float(limit_m.group(1))
            except (ValueError, TypeError):
                limit = None

        # Alcohol metrics
        brac: float | None = None
        brac_m = self.BRAC_REGEX.search(query)
        if brac_m:
            try:
                brac = float(brac_m.group(1))
            except (ValueError, TypeError):
                brac = None

        bac: float | None = None
        bac_m = self.BAC_REGEX.search(query)
        if bac_m:
            try:
                bac = float(bac_m.group(1))
            except (ValueError, TypeError):
                bac = None

        # Vehicle Weight
        weight: float | None = None
        weight_m = self.WEIGHT_REGEX.search(query)
        if weight_m:
            try:
                raw_wt = float(weight_m.group(1))
                if "kg" in weight_m.group(0).lower():
                    weight = raw_wt / 1000.0
                else:
                    weight = raw_wt
            except (ValueError, TypeError):
                weight = None

        # Traffic Signs & Markings
        signs: list[str] = []
        for sm in self.SIGN_REGEX.finditer(query):
            signs.append(sm.group(1).upper().replace(" ", ""))

        markings: list[str] = []
        for mm in self.MARKING_REGEX.finditer(query):
            markings.append(mm.group(1).replace(" ", ""))

        # Location Context
        loc: Literal["urban_residential", "rural_non_residential", "expressway", "unknown"] = "unknown"
        if any(w in query_lower for w in ["đô thị", "dân cư", "nội thành", "nội thị", "trong phố"]):
            loc = "urban_residential"
        elif any(w in query_lower for w in ["cao tốc", "đường cao tốc", "highway"]):
            loc = "expressway"
        elif any(w in query_lower for w in ["ngoài đô thị", "ngoài khu dân cư", "nông thôn", "ngoại thành"]):
            loc = "rural_non_residential"

        # Flags
        is_emergency = any(w in query_lower for w in ["cấp cứu", "khẩn cấp", "chữa cháy", "hộ đê", "nhiệm vụ khẩn cấp", "còi ưu tiên"])
        has_conflicting = (
            ("cảnh sát" in query_lower or "csgt" in query_lower) and ("đèn" in query_lower or "biển" in query_lower or "vạch" in query_lower)
        ) or ("biển tạm" in query_lower and ("biển cố định" in query_lower or "vạch" in query_lower))

        return ExtractedEntities(
            vehicle_category=veh_cat,
            vehicle_weight_tons=weight,
            recorded_speed_kmh=speed,
            speed_limit_kmh=limit,
            alcohol_breath_mg_l=brac,
            alcohol_blood_mg_100ml=bac,
            traffic_sign_codes=signs,
            road_marking_codes=markings,
            location_context=loc,
            is_emergency_mission=is_emergency,
            has_conflicting_authority=has_conflicting,
        )

    def _construct_dag(
        self, query: str, intent: LegalIntent, entities: ExtractedEntities
    ) -> tuple[list[SubGoalNode], list[list[str]]]:
        """Constructs sub-goals and topological execution stages for DAG execution."""
        sub_goals: list[SubGoalNode] = []
        veh_list = [entities.vehicle_category.value] if entities.vehicle_category else []

        if intent == LegalIntent.INTENT_TECHNICAL_STANDARD:
            # G1: Technical spec lookup, G2: Technical reference expansion
            sub_goals.append(
                SubGoalNode(
                    goal_id="G1",
                    goal_type=SubGoalType.LOOKUP_TECHNICAL_SPEC,
                    mcp_tool_name="sign_catalog_lookup",
                    tool_arguments={"sign_code": entities.traffic_sign_codes[0] if entities.traffic_sign_codes else "P.102"},
                    dependencies=[],
                    can_execute_parallel=False,
                )
            )
            sub_goals.append(
                SubGoalNode(
                    goal_id="G2",
                    goal_type=SubGoalType.EXPAND_ADDITIONAL_SANCTION,
                    mcp_tool_name="graph_traverse",
                    tool_arguments={"relation_types": ["DEFINES_SANCTION_FOR", "GUIDES"]},
                    dependencies=["G1"],
                    can_execute_parallel=False,
                )
            )
            exec_order = [["G1"], ["G2"]]
        else:
            # Standard Sanction Search G1
            sub_goals.append(
                SubGoalNode(
                    goal_id="G1",
                    goal_type=SubGoalType.SEARCH_PRIMARY_SANCTION,
                    mcp_tool_name="hybrid_search",
                    tool_arguments={"query": query, "vehicle_types": veh_list},
                    dependencies=[],
                    can_execute_parallel=False,
                )
            )
            # Additional Sanction / Amendment Traverse G2
            sub_goals.append(
                SubGoalNode(
                    goal_id="G2",
                    goal_type=SubGoalType.EXPAND_ADDITIONAL_SANCTION,
                    mcp_tool_name="graph_traverse",
                    tool_arguments={"relation_types": ["HAS_ADDITIONAL_SANCTION", "REFERENCES_TECHNICAL_STANDARD"]},
                    dependencies=["G1"],
                    can_execute_parallel=False,
                )
            )
            exec_order = [["G1"], ["G2"]]

        # If priority conflict or emergency mission, add G3
        if entities.has_conflicting_authority or entities.is_emergency_mission:
            scenario = "EMERGENCY_AMBULANCE" if entities.is_emergency_mission else "POLICE_OVERRIDE_RED_LIGHT"
            sub_goals.append(
                SubGoalNode(
                    goal_id="G3",
                    goal_type=SubGoalType.EVALUATE_PRIORITY_CASCADE,
                    mcp_tool_name="scope_override_detect",
                    tool_arguments={"scenario_type": scenario},
                    dependencies=["G1"],
                    can_execute_parallel=True,
                )
            )
            exec_order = [["G1"], ["G2", "G3"]]

        return sub_goals, exec_order
