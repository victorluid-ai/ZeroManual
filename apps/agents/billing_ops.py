from __future__ import annotations

from typing import Any

from apps.agents.ai_mixin import AgentAIMixin
from apps.agents.base import BaseAutonomousAgent
from apps.orchestrator.models import AgentDecision, Event, RiskLevel
from apps.orchestrator.store import DataStore


class AgentBillingOps(BaseAutonomousAgent, AgentAIMixin):
    name = "AgentBillingOps"
    supported_actions = ("create_invoice", "send_reminder", "mark_paid")

    def __init__(self, store: DataStore | None = None) -> None:
        self._init_ai(store, "billing_ops")

    def plan(self, event: Event, approval_threshold_eur: float) -> AgentDecision:
        amount = float(event.payload.get("amount_eur", 0.0)) if event.payload.get("amount_eur") is not None else 0.0
        risk = self._risk_for_amount(amount, approval_threshold_eur) if amount else RiskLevel.B_MEDIUM
        requires_approval = risk.value == "C_HIGH"

        default = AgentDecision(
            summary="Prepare and process client billing workflow.",
            risk_level=risk,
            proposed_actions=["validate_invoice_data", "issue_invoice", "notify_client"],
            requires_human_approval=requires_approval,
        )

        simple = event.action == "create_invoice" and event.payload.get("amount_eur") is not None
        if self._use_ai_for_plan(simple_case=simple):
            return self._plan_with_ai_fallback(event, approval_threshold_eur, default)
        return default

    def _execute_deterministic(self, event: Event) -> dict[str, Any] | None:
        if not self._tools:
            return None
        client = str(
            event.payload.get("client_name") or event.payload.get("client") or "cliente"
        )
        amount_raw = event.payload.get("amount_eur")
        amount: float | None = float(amount_raw) if amount_raw is not None else None

        if event.action == "create_invoice":
            return self._run_tool(
                "create_invoice_draft",
                {
                    "event_id": event.event_id,
                    "client_name": client,
                    "amount_eur": amount,
                    "client_email": event.payload.get("client_email"),
                    "client_nif": event.payload.get("client_nif"),
                    "concept": event.payload.get("concept"),
                    "entity_id": event.entity_id,
                },
            )

        if event.action == "send_reminder":
            invoice_id = event.payload.get("invoice_id")
            if not invoice_id:
                raise ValueError("send_reminder requiere 'invoice_id' en el payload.")
            return self._run_tool(
                "send_invoice_email",
                {
                    "invoice_id": str(invoice_id),
                    "to_email": event.payload.get("client_email"),
                },
            )

        if event.action == "mark_paid":
            invoice_id = event.payload.get("invoice_id")
            if not invoice_id:
                raise ValueError("mark_paid requiere 'invoice_id' en el payload.")
            return self._run_tool("mark_invoice_paid", {"invoice_id": str(invoice_id)})

        raise ValueError(f"Accion no soportada por AgentBillingOps: '{event.action}'.")

    def execute(self, event: Event, decision: AgentDecision) -> dict[str, Any]:
        # Aprobar/ejecutar NUNCA necesita LLM: accion ya decidida
        deterministic = self._execute_deterministic(event)
        if deterministic is not None:
            return deterministic
        # Only reached with no store/tools attached (e.g. a dry run without
        # persistence) — nothing was actually issued, so say so plainly
        # instead of fabricating an invoice_id/status.
        return {
            "status": "skipped",
            "message": "Sin almacenamiento conectado: no se ha emitido ninguna factura real.",
        }
