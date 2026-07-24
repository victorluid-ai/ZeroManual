from __future__ import annotations

from typing import Any

from apps.agents.ai_mixin import AgentAIMixin
from apps.agents.base import BaseAutonomousAgent
from apps.orchestrator.models import AgentDecision, Event, RiskLevel
from apps.orchestrator.store import DataStore


class AgentSalesPipeline(BaseAutonomousAgent, AgentAIMixin):
    name = "AgentSalesPipeline"
    supported_actions = ("qualify_lead", "draft_proposal", "followup_sequence")

    def __init__(self, store: DataStore | None = None) -> None:
        self._init_ai(store, "sales_pipeline")

    def plan(self, event: Event, approval_threshold_eur: float) -> AgentDecision:
        deal_raw = event.payload.get("deal_value_eur")
        deal_value = float(deal_raw) if deal_raw is not None else 0.0
        risk = self._risk_for_amount(deal_value, approval_threshold_eur * 2.0) if deal_value else RiskLevel.A_LOW

        default = AgentDecision(
            summary="Advance lead through sales funnel and prepare handoff.",
            risk_level=risk,
            proposed_actions=["score_lead", "draft_offer", "schedule_followup"],
            requires_human_approval=risk.value == "C_HIGH",
        )

        lead = event.payload.get("lead_name") or event.payload.get("client_name")
        simple = bool(lead) and event.action in ("qualify_lead", "draft_proposal")
        if self._use_ai_for_plan(simple_case=simple):
            return self._plan_with_ai_fallback(event, approval_threshold_eur, default)
        return default

    def execute(self, event: Event, decision: AgentDecision) -> dict[str, Any]:
        lead = str(
            event.payload.get("lead_name")
            or event.payload.get("client_name")
            or event.payload.get("client")
            or "lead"
        )
        deal_raw = event.payload.get("deal_value_eur")
        deal_value = float(deal_raw) if deal_raw is not None else None

        stage = {
            "qualify_lead": "qualified",
            "draft_proposal": "proposal_sent",
            "followup_sequence": "followup_scheduled",
        }.get(event.action, "updated")

        result = self._run_tool(
            "update_lead",
            {
                "event_id": event.event_id,
                "lead_name": lead,
                "stage": stage,
                "deal_value_eur": deal_value,
                "entity_id": event.entity_id,
            },
        )
        if result:
            result["handoff"] = "prepared" if event.action == "draft_proposal" else "none"
            return result

        return {
            "lead_status": stage,
            "handoff": "prepared",
            "message": "Lead updated with next best action and proposal draft.",
        }
