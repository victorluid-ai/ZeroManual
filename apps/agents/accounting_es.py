from __future__ import annotations

from typing import Any

from apps.agents.ai_mixin import AgentAIMixin
from apps.agents.base import BaseAutonomousAgent
from apps.orchestrator.models import AgentDecision, Event, RiskLevel
from apps.orchestrator.store import DataStore


class AgentAccountingAssistantES(BaseAutonomousAgent, AgentAIMixin):
    name = "AgentAccountingAssistantES"
    supported_actions = ("classify_transaction", "monthly_reconcile", "vat_draft")

    def __init__(self, store: DataStore | None = None) -> None:
        self._init_ai(store, "accounting_es")

    def plan(self, event: Event, approval_threshold_eur: float) -> AgentDecision:
        amount_raw = event.payload.get("amount_eur")
        amount = float(amount_raw) if amount_raw is not None else 0.0
        risk = self._risk_for_amount(amount, approval_threshold_eur) if amount else RiskLevel.B_MEDIUM
        is_tax_filing = event.action == "vat_draft"
        requires_approval = risk.value == "C_HIGH" or is_tax_filing

        default = AgentDecision(
            summary="Classify accounting movement under Spain-focused rules.",
            risk_level=risk,
            proposed_actions=["classify_ledger_entry", "reconcile_bank_event", "store_evidence"],
            requires_human_approval=requires_approval,
        )

        simple = event.action == "classify_transaction" and event.payload.get("invoice_id")
        if self._use_ai_for_plan(simple_case=simple):
            return self._plan_with_ai_fallback(event, approval_threshold_eur, default)
        return default

    def execute(self, event: Event, decision: AgentDecision) -> dict[str, Any]:
        client = event.payload.get("client_name") or event.payload.get("client")
        amount_raw = event.payload.get("amount_eur")
        amount = float(amount_raw) if amount_raw is not None else None

        if event.action == "classify_transaction":
            result = self._run_tool(
                "classify_ledger_entry",
                {
                    "event_id": event.event_id,
                    "client_name": str(client) if client else None,
                    "amount_eur": amount,
                    "invoice_id": event.payload.get("invoice_id"),
                    "entity_id": event.entity_id,
                },
            )
            if result:
                return result

        if event.action == "vat_draft":
            period = str(event.payload.get("period", "mensual"))
            result = self._run_tool(
                "record_vat_draft",
                {
                    "event_id": event.event_id,
                    "period": period,
                    "amount_eur": amount,
                    "entity_id": event.entity_id,
                },
            )
            if result:
                return result

        return {
            "ledger_status": "classified",
            "reconciliation": "queued",
            "message": "Entry classified and added to monthly close queue.",
        }
