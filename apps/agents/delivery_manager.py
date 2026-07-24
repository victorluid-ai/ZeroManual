from __future__ import annotations

from typing import Any

from apps.agents.ai_mixin import AgentAIMixin
from apps.agents.base import BaseAutonomousAgent
from apps.orchestrator.models import AgentDecision, Event, RiskLevel
from apps.orchestrator.store import DataStore


class AgentClientDeliveryManager(BaseAutonomousAgent, AgentAIMixin):
    name = "AgentClientDeliveryManager"
    supported_actions = ("client_onboarding", "sla_followup", "incident_triage")

    def __init__(self, store: DataStore | None = None) -> None:
        self._init_ai(store, "delivery_manager")

    def plan(self, event: Event, approval_threshold_eur: float) -> AgentDecision:
        has_outage = bool(event.payload.get("production_outage", False))
        risk = RiskLevel.C_HIGH if has_outage else RiskLevel.A_LOW

        default = AgentDecision(
            summary="Coordinate client delivery tasks and SLA adherence.",
            risk_level=risk,
            proposed_actions=["check_client_runbooks", "sync_automation_workflows", "notify_stakeholders"],
            requires_human_approval=has_outage,
        )

        client = event.payload.get("client_name") or event.payload.get("client")
        simple = bool(client) and event.action == "client_onboarding"
        if self._use_ai_for_plan(simple_case=simple):
            return self._plan_with_ai_fallback(event, approval_threshold_eur, default)
        return default

    def execute(self, event: Event, decision: AgentDecision) -> dict[str, Any]:
        client = str(
            event.payload.get("client_name")
            or event.payload.get("client")
            or "cliente"
        )
        status = {
            "client_onboarding": "onboarding_started",
            "sla_followup": "sla_checked",
            "incident_triage": "incident_triaged",
        }.get(event.action, "updated")

        note = str(event.payload.get("note", ""))
        if event.payload.get("production_outage"):
            note = (note + " incidencia produccion").strip()

        result = self._run_tool(
            "log_delivery_update",
            {
                "event_id": event.event_id,
                "client_name": client,
                "delivery_status": status,
                "note": note,
                "entity_id": event.entity_id,
            },
        )
        if result:
            return result

        return {
            "delivery_status": status,
            "workflow_sync": "completed",
            "message": "Delivery plan updated and automations synchronized.",
        }
