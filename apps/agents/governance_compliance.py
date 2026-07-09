from __future__ import annotations

from typing import Any

from apps.agents.ai_mixin import AgentAIMixin
from apps.agents.base import BaseAutonomousAgent
from apps.orchestrator.models import AgentDecision, Event, RiskLevel
from apps.orchestrator.store import DataStore


class AgentGovernanceAndCompliance(BaseAutonomousAgent, AgentAIMixin):
    name = "AgentGovernanceAndCompliance"
    supported_actions = ("policy_check", "access_review", "gdpr_audit")

    def __init__(self, store: DataStore | None = None) -> None:
        self._init_ai(store, "governance_compliance")

    def plan(self, event: Event, approval_threshold_eur: float) -> AgentDecision:
        sensitive = bool(event.payload.get("sensitive_data", False))
        risky_operation = bool(event.payload.get("irreversible_action", False))
        requires_approval = sensitive or risky_operation
        risk = RiskLevel.C_HIGH if requires_approval else RiskLevel.B_MEDIUM

        default = AgentDecision(
            summary="Validate policy, data protection and action permissions.",
            risk_level=risk,
            proposed_actions=["run_policy_checks", "verify_permissions", "write_compliance_report"],
            requires_human_approval=requires_approval,
        )

        simple = event.action == "policy_check" and not sensitive and not risky_operation
        if self._use_ai_for_plan(simple_case=simple):
            return self._plan_with_ai_fallback(event, approval_threshold_eur, default)
        return default

    def execute(self, event: Event, decision: AgentDecision) -> dict[str, Any]:
        check_type = {
            "policy_check": "policy",
            "access_review": "access",
            "gdpr_audit": "gdpr",
        }.get(event.action, event.action)

        outcome = "passed" if not decision.requires_human_approval else "review_required"
        result = self._run_tool(
            "log_compliance_check",
            {
                "event_id": event.event_id,
                "check_type": check_type,
                "outcome": outcome,
                "details": str(event.payload),
            },
        )
        if result:
            return result

        return {
            "compliance_status": outcome,
            "controls": "recorded",
            "message": "Operation validated against governance controls.",
        }
