"""End-to-End Multi-Hop Legal Reasoning Pipeline."""

from __future__ import annotations

from typing import Any

from rag_eval.legal.mcp.tools import LegalMCPTools
from rag_eval.legal.reasoning.chain_of_custody import ChainOfCustodyGenerator
from rag_eval.legal.reasoning.overrides import EmergencyVehicleTier, ScopeOverrideEngine
from rag_eval.legal.reasoning.planner import QueryPlanner
from rag_eval.legal.reasoning.traverser import DeterministicTriadTraverser
from rag_eval.legal.schemas import (
    ExecutionPlanDAG,
    PrecedenceResolutionAudit,
    SignalTier,
    Temporality,
    TrafficSignalCommand,
    VehicleCategory,
)


class LegalReasoningPipeline:
    """Orchestrates end-to-end multi-hop legal reasoning queries against the MCP stack."""

    def __init__(self, tools: LegalMCPTools | None = None) -> None:
        self.tools = tools or LegalMCPTools()
        self.planner = QueryPlanner()
        self.traverser = DeterministicTriadTraverser(self.tools)
        self.override_engine = ScopeOverrideEngine()
        self.coc_generator = ChainOfCustodyGenerator()

    async def execute_query(self, query: str) -> dict[str, Any]:
        """Executes a full E2E pipeline turn: Plan -> Search -> Traverse -> Override -> CoC.

        Eliminates duplicate hybrid search calls by forwarding pre-retrieved seed chunks.
        """
        # 1. Plan & Entity Slot Extraction
        plan: ExecutionPlanDAG = self.planner.plan(query)

        # 2. Search & Retrieval (Single execution)
        search_args = plan.sub_goals[0].tool_arguments if plan.sub_goals else {}
        vtypes = search_args.get("vehicle_types")
        vehicle_types_list = vtypes if isinstance(vtypes, list) else None

        search_res = await self.tools.hybrid_search(
            query=query,
            vehicle_types=vehicle_types_list,
            limit=5,
        )
        retrieved_matches: list[dict[str, Any]] = search_res.get("results", [])

        # 3. Deterministic Parallel Traversal (Consumes initial seeds directly)
        veh_cat_str = (
            plan.extracted_entities.vehicle_category.value
            if plan.extracted_entities.vehicle_category
            else None
        )
        traversal_paths = await self.traverser.traverse(
            query=query,
            vehicle_category=veh_cat_str,
            seed_chunks=retrieved_matches[: self.traverser.beam_width],
        )

        # 4. Scope Override / Precedence Check
        override_ruling: dict[str, Any] | None = None
        precedence_audits: list[PrecedenceResolutionAudit] = []

        if (
            plan.extracted_entities.has_conflicting_authority
            or plan.extracted_entities.is_emergency_mission
        ):
            # 4a. Emergency Vehicle Exemption & Privilege Evaluation
            if plan.extracted_entities.is_emergency_mission:
                vcat = plan.extracted_entities.vehicle_category or VehicleCategory.PRIORITY_VEHICLE
                em_tier = EmergencyVehicleTier.AMBULANCE
                q_lower = query.lower()
                if any(w in q_lower for w in ["chữa cháy", "cứu hỏa"]):
                    em_tier = EmergencyVehicleTier.FIRE_FIGHTING
                elif any(w in q_lower for w in ["quân sự", "công an", "dẫn đường"]):
                    em_tier = EmergencyVehicleTier.MILITARY_POLICE
                elif any(w in q_lower for w in ["hộ đê", "thiên tai", "dịch bệnh"]):
                    em_tier = EmergencyVehicleTier.DIKE_DISASTER_RELIEF
                elif any(w in q_lower for w in ["xe tang", "đoàn xe tang"]):
                    em_tier = EmergencyVehicleTier.FUNERAL_CORTEGE

                em_res = self.override_engine.evaluate_emergency_privilege(
                    vehicle_type=vcat,
                    is_on_duty=True,
                    has_siren_beacon=True,
                    emergency_tier=em_tier,
                )
                if em_res["is_exempt"]:
                    override_ruling = {
                        "status": "success",
                        "is_override_active": True,
                        "dominant_authority": "EMERGENCY_MISSION",
                        "override_type": "EMERGENCY_PRIVILEGE",
                        "is_driver_action_legal": True,
                        "legal_basis": em_res["legal_basis"],
                        "ruling_rationale": em_res["ruling"],
                    }
                    precedence_audits.append(
                        PrecedenceResolutionAudit(
                            conflict_type="EMERGENCY_VEHICLE_PRIVILEGE",
                            dominant_authority=str(em_res.get("emergency_tier", "PRIORITY_VEHICLE")),
                            overridden_authorities=["GENERAL_RULE", "TRAFFIC_LIGHT"],
                            statutory_rule_applied=em_res["legal_basis"][0],
                        )
                    )

            # 4b. Dynamic Signal Conflict Resolution
            if plan.extracted_entities.has_conflicting_authority:
                active_signals: list[TrafficSignalCommand] = []
                q_lower = query.lower()
                if any(w in q_lower for w in ["cảnh sát", "csgt", "người điều khiển"]):
                    active_signals.append(
                        TrafficSignalCommand(
                            source_type=SignalTier.POLICE_OFFICER,
                            temporality=Temporality.PERMANENT,
                            command_directive="PROCEED",
                            legal_citation="QCVN 41:2019/BGTVT Điều 4 Khoản 4.1",
                        )
                    )
                if any(w in q_lower for w in ["đèn đỏ", "đèn tín hiệu", "đèn"]):
                    active_signals.append(
                        TrafficSignalCommand(
                            source_type=SignalTier.TRAFFIC_LIGHT,
                            temporality=Temporality.PERMANENT,
                            command_directive="STOP",
                            legal_citation="QCVN 41:2019/BGTVT Điều 4 Khoản 4.2",
                        )
                    )
                if any(w in q_lower for w in ["biển tạm", "biển báo tạm thời", "công trường"]):
                    active_signals.append(
                        TrafficSignalCommand(
                            source_type=SignalTier.TRAFFIC_SIGN,
                            temporality=Temporality.TEMPORARY,
                            command_directive=(
                                "SPEED_LIMIT"
                                if plan.extracted_entities.recorded_speed_kmh is not None
                                else "PROCEED"
                            ),
                            speed_cap_kmh=plan.extracted_entities.speed_limit_kmh,
                            legal_citation="QCVN 41:2019/BGTVT Điều 4 Khoản 4.3",
                        )
                    )
                elif any(w in q_lower for w in ["biển báo", "biển cố định", "biển số", "biển"]):
                    active_signals.append(
                        TrafficSignalCommand(
                            source_type=SignalTier.TRAFFIC_SIGN,
                            temporality=Temporality.PERMANENT,
                            command_directive=(
                                "SPEED_LIMIT"
                                if plan.extracted_entities.recorded_speed_kmh is not None
                                else "PROCEED"
                            ),
                            speed_cap_kmh=plan.extracted_entities.speed_limit_kmh,
                            legal_citation="QCVN 41:2019/BGTVT Điều 4 Khoản 4.4",
                        )
                    )
                if any(w in q_lower for w in ["vạch kẻ", "vạch đường", "vạch số"]):
                    active_signals.append(
                        TrafficSignalCommand(
                            source_type=SignalTier.ROAD_MARKING,
                            temporality=Temporality.PERMANENT,
                            command_directive="PROCEED",
                            legal_citation="QCVN 41:2019/BGTVT Điều 4 Khoản 4.4",
                        )
                    )

                if active_signals:
                    conflict_res = self.override_engine.resolve_signal_conflict(
                        signals=active_signals,
                        driver_action="PROCEED",
                        driver_speed_kmh=plan.extracted_entities.recorded_speed_kmh,
                    )
                    audit_trace = self.override_engine.to_audit_trace(conflict_res)
                    precedence_audits.append(audit_trace)
                    override_ruling = {
                        "status": "success",
                        "is_override_active": True,
                        "dominant_authority": conflict_res.dominant_signal.source_type.name,
                        "is_driver_action_legal": conflict_res.is_driver_action_legal,
                        "legal_basis": conflict_res.legal_basis,
                        "ruling_rationale": conflict_res.ruling_rationale,
                    }

        # 5. Synthesize Verifiable Chain of Custody
        coc = self.coc_generator.generate(
            query=query,
            retrieved_chunks=retrieved_matches,
            advisory_text="Tư vấn căn cứ quy định pháp luật giao thông đường bộ Việt Nam.",
            plan_summary={
                "intent": plan.primary_intent.value,
                "total_subgoals": len(plan.sub_goals),
                "execution_order": plan.execution_order,
            },
            precedence_resolutions=precedence_audits,
        )

        return {
            "query": query,
            "plan": plan,
            "retrieved_matches": retrieved_matches,
            "traversal_paths": [
                {
                    "nodes": [n.node_id for n in p.nodes],
                    "hierarchy_paths": [n.hierarchy_path for n in p.nodes],
                    "edges": p.edge_types,
                    "score": p.cumulative_score,
                }
                for p in traversal_paths
            ],
            "override_ruling": override_ruling,
            "chain_of_custody": coc,
        }
