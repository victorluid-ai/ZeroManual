from __future__ import annotations

import re
from typing import Any

from apps.llm.claude_client import ClaudeClient
from apps.triggers.models import ActivationDecision, TriggerSignal, TriggerType


BILLING_KEYWORDS = (
    "factura",
    "invoice",
    "cobro",
    "pago",
    "payment",
    "presupuesto",
    "quote",
    "pedido",
    "order",
    "billing",
)

SALES_KEYWORDS = ("lead", "interesad", "propuesta", "demo", "reunion", "oportunidad")

DELIVERY_KEYWORDS = ("incidencia", "error", "caido", "down", "sla", "urgente", "soporte")


class TriggerDetector:
    """Decides whether an external signal should wake an autonomous agent."""

    def __init__(self) -> None:
        self.claude = ClaudeClient()

    def evaluate(self, signal: TriggerSignal) -> ActivationDecision:
        if signal.trigger_type == TriggerType.EMAIL:
            return self._evaluate_email(signal)
        return ActivationDecision(should_activate=False, reason="Unsupported trigger type.")

    def _evaluate_email(self, signal: TriggerSignal) -> ActivationDecision:
        llm_decision = self._evaluate_email_with_claude(signal)
        if llm_decision is not None:
            return llm_decision
        return self._evaluate_email_with_rules(signal)

    def _evaluate_email_with_rules(self, signal: TriggerSignal) -> ActivationDecision:
        subject = (signal.payload.get("subject") or "").lower()
        body = (signal.payload.get("body") or "").lower()
        text = f"{subject}\n{body}"

        amount = self._extract_amount(text)
        client = self._extract_client(text) or signal.payload.get("from_email")

        if any(k in text for k in BILLING_KEYWORDS):
            payload: dict[str, Any] = {
                "email_subject": signal.payload.get("subject"),
                "from_email": signal.payload.get("from_email"),
                "trigger_summary": signal.summary,
            }
            if amount is not None:
                payload["amount_eur"] = amount
            if client:
                payload["client_name"] = client

            action = "send_reminder" if "recordatorio" in text or "reminder" in text else "create_invoice"
            return ActivationDecision(
                should_activate=True,
                agent_name="AgentBillingOps",
                action=action,
                event_payload=payload,
                reason="Email matches billing-related patterns.",
            )

        if any(k in text for k in SALES_KEYWORDS):
            payload = {
                "email_subject": signal.payload.get("subject"),
                "from_email": signal.payload.get("from_email"),
                "trigger_summary": signal.summary,
            }
            if amount is not None:
                payload["deal_value_eur"] = amount
            return ActivationDecision(
                should_activate=True,
                agent_name="AgentSalesPipeline",
                action="qualify_lead",
                event_payload=payload,
                reason="Email matches sales lead patterns.",
            )

        if any(k in text for k in DELIVERY_KEYWORDS):
            return ActivationDecision(
                should_activate=True,
                agent_name="AgentClientDeliveryManager",
                action="incident_triage",
                event_payload={
                    "email_subject": signal.payload.get("subject"),
                    "from_email": signal.payload.get("from_email"),
                    "production_outage": "caido" in text or "down" in text or "error" in text,
                    "trigger_summary": signal.summary,
                },
                reason="Email matches delivery/incident patterns.",
            )

        return ActivationDecision(should_activate=False, reason="No agent pattern matched this email.")

    def _evaluate_email_with_claude(self, signal: TriggerSignal) -> ActivationDecision | None:
        if not self.claude.enabled:
            return None

        system = (
            "Route incoming business emails to ZeroManual autonomous agents. "
            "Respond ONLY JSON."
        )
        user = (
            "If no action: {\"should_activate\": false, \"reason\": \"...\"}\n"
            "If action: {\"should_activate\": true, \"agent_name\": \"...\", \"action\": \"...\", "
            "\"event_payload\": {...}, \"reason\": \"...\"}\n"
            f"Subject: {signal.payload.get('subject')}\n"
            f"From: {signal.payload.get('from_email')}\n"
            f"Body: {signal.payload.get('body', '')[:1500]}"
        )
        data = self.claude.complete_json(system=system, user=user, max_tokens=400)
        if not data:
            return None
        if not data.get("should_activate"):
            return ActivationDecision(should_activate=False, reason=data.get("reason", "LLM: no action"))
        return ActivationDecision(
            should_activate=True,
            agent_name=data.get("agent_name"),
            action=data.get("action"),
            event_payload=data.get("event_payload", {}),
            reason=data.get("reason", "LLM routing"),
        )

    def _extract_amount(self, text: str) -> float | None:
        match = re.search(r"(\d+[.,]?\d*)\s*(€|eur|euros?)", text, re.I)
        if match:
            return float(match.group(1).replace(",", "."))
        return None

    def _extract_client(self, text: str) -> str | None:
        match = re.search(r"cliente\s+([a-zA-Z0-9][\w\s.-]{0,40})", text, re.I)
        if match:
            return match.group(1).strip().split("\n")[0].strip()
        return None
