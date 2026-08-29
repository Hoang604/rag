"""Scope Override Engine evaluating signaling precedence inequality and emergency privileges."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Any, Literal

from rag_eval.legal.schemas import (
    ConflictEvaluationResult,
    PrecedenceResolutionAudit,
    SignalTier,
    Temporality,
    TrafficSignalCommand,
    VehicleCategory,
)


class EmergencyVehicleTier(float, Enum):
    """5-Tier statutory emergency vehicle hierarchy per Law on Road Traffic 2008 Art 22 / Law 2024 Art 20."""

    FIRE_FIGHTING = 1.1  # Xe chữa cháy đi làm nhiệm vụ
    MILITARY_POLICE = 1.2  # Xe quân sự, xe công an đi làm nhiệm vụ khẩn cấp, đoàn xe có CSGT dẫn đường
    AMBULANCE = 1.3  # Xe cứu thương đang thực hiện nhiệm vụ cấp cứu
    DIKE_DISASTER_RELIEF = 1.4  # Xe hộ đê, xe làm nhiệm vụ khắc phục thiên tai, dịch bệnh, khẩn cấp
    FUNERAL_CORTEGE = 1.5  # Đoàn xe tang


class StatutoryPrecedenceRank(float, Enum):
    """Full 6-tier statutory priority hierarchy under Vietnamese Road Traffic Law and QCVN 41:2019."""

    TRAFFIC_POLICE = 1.0  # Người điều khiển giao thông / CSGT
    EMERGENCY_VEHICLE_GENERIC = 1.5  # Xe ưu tiên làm nhiệm vụ khẩn cấp chung
    TRAFFIC_LIGHT = 2.0  # Đèn tín hiệu giao thông
    ROAD_SIGN_TEMPORARY = 3.1  # Biển báo hiệu tạm thời
    ROAD_SIGN_PERMANENT = 3.2  # Biển báo hiệu cố định
    ROAD_MARKING = 4.0  # Vạch kẻ đường và thiết bị phụ trợ
    GENERAL_RULE = 5.0  # Quy tắc giao thông đường bộ chung


class ScopeOverrideEngine:
    """Evaluates statutory signal precedence inequality, emergency privilege lattices, and speed limits."""

    @staticmethod
    def get_statutory_rank(
        source_type: SignalTier,
        temporality: Temporality = Temporality.PERMANENT,
        emergency_tier: EmergencyVehicleTier | None = None,
    ) -> float:
        """Computes precise statutory priority rank value (lower number = higher priority)."""
        if source_type == SignalTier.POLICE_OFFICER:
            return StatutoryPrecedenceRank.TRAFFIC_POLICE.value

        if source_type == SignalTier.TRAFFIC_LIGHT:
            return StatutoryPrecedenceRank.TRAFFIC_LIGHT.value

        if source_type == SignalTier.TRAFFIC_SIGN:
            return (
                StatutoryPrecedenceRank.ROAD_SIGN_TEMPORARY.value
                if temporality == Temporality.TEMPORARY
                else StatutoryPrecedenceRank.ROAD_SIGN_PERMANENT.value
            )

        if source_type == SignalTier.ROAD_MARKING:
            return StatutoryPrecedenceRank.ROAD_MARKING.value

        return StatutoryPrecedenceRank.GENERAL_RULE.value

    def resolve_signal_conflict(
        self,
        signals: Sequence[SignalTier | TrafficSignalCommand],
        driver_action: Literal["PROCEED", "STOP", "TURN_LEFT", "TURN_RIGHT", "MAINTAIN_SPEED"] | str = "PROCEED",
        driver_speed_kmh: float | None = None,
        emergency_vehicle_tier: EmergencyVehicleTier | None = None,
    ) -> ConflictEvaluationResult:
        """Determines the legally governing signal command and evaluates compliance.

        Full 6-tier Precedence Inequality:
        TRAFFIC_POLICE (1.0) > EMERGENCY_VEHICLE (1.1-1.5) > TRAFFIC_LIGHT (2.0) >
        ROAD_SIGN_TEMPORARY (3.1) > ROAD_SIGN_PERMANENT (3.2) > ROAD_MARKING (4.0) > GENERAL_RULE (5.0).
        """
        if not signals:
            raise ValueError("Conflict resolution requires at least one active signal command.")

        # Normalize to TrafficSignalCommand
        cmd_list: list[TrafficSignalCommand] = []
        for s in signals:
            if isinstance(s, TrafficSignalCommand):
                cmd_list.append(s)
            elif isinstance(s, SignalTier):
                directive = "PROCEED" if s == SignalTier.POLICE_OFFICER else "STOP"
                citation = (
                    "Điều 4 Khoản 4.1 QCVN 41:2019/BGTVT"
                    if s == SignalTier.POLICE_OFFICER
                    else f"Điều 4 QCVN 41:2019/BGTVT (Thứ bậc {s.name})"
                )
                cmd_list.append(
                    TrafficSignalCommand(
                        source_type=s,
                        temporality=Temporality.PERMANENT,
                        command_directive=directive,
                        legal_citation=citation,
                    )
                )

        def sort_key(cmd: TrafficSignalCommand) -> tuple[float, int]:
            rank = self.get_statutory_rank(cmd.source_type, cmd.temporality, emergency_vehicle_tier)
            return (rank, cmd.temporality.value)

        sorted_signals = sorted(cmd_list, key=sort_key)
        dominant = sorted_signals[0]
        suppressed = sorted_signals[1:]

        rationale_parts: list[str] = []
        is_legal = False

        if dominant.source_type == SignalTier.POLICE_OFFICER:
            rationale_parts.append(
                "Theo Khoản 4.1 Điều 4 QCVN 41:2019/BGTVT và Điều 11 Luật GTĐB 2008, "
                "hiệu lệnh của người điều khiển giao thông có hiệu lực cao nhất, "
                "người tham gia giao thông phải chấp hành hiệu lệnh của CSGT ngay cả khi "
                "hiệu lệnh trái với tín hiệu đèn, biển báo hoặc vạch kẻ đường."
            )
            is_legal = (driver_action == dominant.command_directive)

        elif dominant.source_type == SignalTier.TRAFFIC_LIGHT:
            rationale_parts.append(
                "Theo Khoản 4.2 Điều 4 QCVN 41:2019/BGTVT, tín hiệu đèn giao thông "
                "ghi đè và có hiệu lực cao hơn biển báo hiệu đường bộ và vạch kẻ đường."
            )
            is_legal = (driver_action == dominant.command_directive)

        elif dominant.source_type == SignalTier.TRAFFIC_SIGN:
            if dominant.temporality == Temporality.TEMPORARY:
                rationale_parts.append(
                    "Theo Khoản 4.3 Điều 4 QCVN 41:2019/BGTVT, biển báo tạm thời có hiệu lực "
                    "cao hơn biển báo cố định và vạch kẻ đường."
                )
            else:
                rationale_parts.append(
                    "Theo Khoản 4.4 Điều 4 QCVN 41:2019/BGTVT, biển báo hiệu cố định có hiệu lực "
                    "cao hơn vạch kẻ đường."
                )
            if (
                dominant.command_directive == "SPEED_LIMIT"
                and driver_speed_kmh is not None
                and dominant.speed_cap_kmh is not None
            ):
                is_legal = driver_speed_kmh <= dominant.speed_cap_kmh
            else:
                is_legal = (driver_action == dominant.command_directive)

        elif dominant.source_type == SignalTier.ROAD_MARKING:
            rationale_parts.append(
                "Theo Khoản 4.4 Điều 4 QCVN 41:2019/BGTVT, vạch kẻ đường có hiệu lực tuân thủ "
                "khi không có biển báo hiệu, đèn tín hiệu hoặc hiệu lệnh của CSGT."
            )
            is_legal = (driver_action == dominant.command_directive)

        else:
            rationale_parts.append("Áp dụng quy tắc giao thông đường bộ chung.")
            is_legal = (driver_action == dominant.command_directive)

        legal_basis: list[str] = [dominant.legal_citation] + [s.legal_citation for s in suppressed]
        legal_basis.append("QCVN 41:2019/BGTVT Điều 4")
        legal_basis.append("Luật Giao thông đường bộ 2008 Điều 11")

        # Deduplicate preserving order
        seen: set[str] = set()
        dedup_basis: list[str] = []
        for b in legal_basis:
            if b and b not in seen:
                seen.add(b)
                dedup_basis.append(b)

        return ConflictEvaluationResult(
            dominant_signal=dominant,
            suppressed_signals=suppressed,
            is_driver_action_legal=is_legal,
            ruling_rationale=" ".join(rationale_parts),
            legal_basis=dedup_basis,
        )

    def evaluate_emergency_privilege(
        self,
        vehicle_type: VehicleCategory,
        is_on_duty: bool,
        has_siren_beacon: bool,
        behavior_type: str = "red_light_or_speeding",
        emergency_tier: EmergencyVehicleTier = EmergencyVehicleTier.AMBULANCE,
    ) -> dict[str, Any]:
        """Evaluates statutory emergency exemptions under Art 22 Law 2008 / Art 20 Law 2024."""
        if (
            vehicle_type == VehicleCategory.PRIORITY_VEHICLE
            and is_on_duty
            and has_siren_beacon
        ):
            return {
                "is_exempt": True,
                "emergency_tier": emergency_tier.name,
                "statutory_rank": emergency_tier.value,
                "legal_basis": [
                    "Điều 22 Luật GTĐB 2008",
                    "Luật Trật tự, an toàn giao thông đường bộ 2024 Điều 20",
                ],
                "ruling": (
                    f"Phương tiện ưu tiên ({emergency_tier.name}) đang làm nhiệm vụ khẩn cấp "
                    f"có phát tín hiệu còi, đèn, cờ theo quy định tại Điều 22 Luật GTĐB 2008 được quyền ưu tiên đi trước "
                    f"và được miễn trừ xử phạt đối với hành vi '{behavior_type}'."
                ),
            }
        return {
            "is_exempt": False,
            "emergency_tier": None,
            "statutory_rank": None,
            "legal_basis": ["Luật Giao thông đường bộ 2008"],
            "ruling": "Không đủ điều kiện hưởng quyền ưu tiên xe khẩn cấp.",
        }

    def resolve_emergency_vehicle_conflict(
        self,
        vehicle_a_tier: EmergencyVehicleTier,
        vehicle_b_tier: EmergencyVehicleTier,
    ) -> dict[str, Any]:
        """Resolves right-of-way conflict between two competing emergency vehicles per Law 2008 Art 22."""
        if vehicle_a_tier.value < vehicle_b_tier.value:
            dominant, subordinate = vehicle_a_tier, vehicle_b_tier
            dominant_name = "Vehicle A"
        elif vehicle_b_tier.value < vehicle_a_tier.value:
            dominant, subordinate = vehicle_b_tier, vehicle_a_tier
            dominant_name = "Vehicle B"
        else:
            return {
                "dominant_vehicle": "EQUAL_PRIORITY",
                "dominant_tier": vehicle_a_tier.name,
                "ruling": "Hai phương tiện có cùng mức độ ưu tiên; áp dụng quy tắc nhường đường bên phải.",
                "legal_basis": ["Điều 22 Khoản 1 Luật GTĐB 2008"],
            }

        return {
            "dominant_vehicle": dominant_name,
            "dominant_tier": dominant.name,
            "dominant_rank": dominant.value,
            "subordinate_tier": subordinate.name,
            "subordinate_rank": subordinate.value,
            "ruling": f"{dominant.name} (Thứ bậc {dominant.value}) được quyền ưu tiên đi trước {subordinate.name} (Thứ bậc {subordinate.value}).",
            "legal_basis": [
                "Điều 22 Khoản 1 Luật GTĐB 2008",
                "Luật Trật tự, an toàn giao thông đường bộ 2024 Điều 20 Khoản 1",
            ],
        }

    @staticmethod
    def to_audit_trace(
        conflict_result: ConflictEvaluationResult,
        conflict_type: str | None = None,
    ) -> PrecedenceResolutionAudit:
        """Converts a ConflictEvaluationResult into an immutable PrecedenceResolutionAudit record."""
        dom_name = conflict_result.dominant_signal.source_type.name
        overridden = [s.source_type.name for s in conflict_result.suppressed_signals]
        c_type = conflict_type or (f"{dom_name}_OVERRIDE_{overridden[0]}" if overridden else "PRECEDENCE_EVAL")
        statutory_rule = (
            conflict_result.legal_basis[0]
            if conflict_result.legal_basis
            else "QCVN 41:2019/BGTVT Điều 4"
        )
        return PrecedenceResolutionAudit(
            conflict_type=c_type,
            dominant_authority=dom_name,
            overridden_authorities=overridden,
            statutory_rule_applied=statutory_rule,
        )
