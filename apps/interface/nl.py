from __future__ import annotations

import re
from typing import Any

from apps.llm.claude_client import ClaudeClient
from apps.zeromanual_env import zm_env


class NaturalLanguageInterpreter:
    def __init__(self) -> None:
        self.claude = ClaudeClient()

    def interpret(self, message: str) -> dict[str, Any]:
        ai_mode = zm_env("AI_MODE", "eco").lower()
        if ai_mode == "off":
            return self._interpret_with_rules(message)

        # eco: reglas primero (gratis) y Claude solo si no hay match claro
        if ai_mode != "full":
            rules_result = self._interpret_with_rules(message)
            # sla_followup with a note is the catch-all fallback — invoke Claude for ambiguous inputs
            if not (rules_result.get("action") == "sla_followup" and rules_result.get("payload", {}).get("note")):
                return rules_result

        if self.claude.enabled:
            llm_result = self._interpret_with_claude(message)
            if llm_result:
                return llm_result
        return self._interpret_with_rules(message)

    def _interpret_with_claude(self, message: str) -> dict[str, Any] | None:
        system = (
            "Convierte instrucciones de negocio en eventos JSON para agentes ZeroManual. "
            "Responde SOLO JSON con: agent_name, action, payload."
        )
        user = (
            "Agentes: AgentBillingOps, AgentAccountingAssistantES, "
            "AgentClientDeliveryManager, AgentSalesPipeline, AgentGovernanceAndCompliance.\n"
            "Billing actions: create_invoice, send_reminder, mark_paid\n"
            "Accounting: classify_transaction, monthly_reconcile, vat_draft\n"
            "Delivery: client_onboarding, sla_followup, incident_triage\n"
            "Sales: qualify_lead, draft_proposal, followup_sequence\n"
            "Governance: policy_check, access_review, gdpr_audit\n"
            f"Texto: {message}"
        )
        parsed = self.claude.complete_json(system=system, user=user)
        if parsed and "agent_name" in parsed and "action" in parsed:
            parsed.setdefault("payload", {})
            return parsed
        return None

    def _interpret_with_rules(self, message: str) -> dict[str, Any]:
        text = message.lower()
        amount_match = re.search(r"(\d+[.,]?\d*)\s*(eur|€)?", text)
        amount_eur = None
        if amount_match:
            amount_eur = float(amount_match.group(1).replace(",", "."))

        if any(word in text for word in ["factura", "facturar", "cobro", "invoice", "recordatorio"]):
            action = "send_reminder" if "recordatorio" in text else "create_invoice"
            payload: dict[str, Any] = {}
            if amount_eur is not None:
                payload["amount_eur"] = amount_eur
            client_match = re.search(r"cliente\s+([a-zA-Z0-9][\w\s.-]{0,40})", message, re.I)
            if client_match:
                payload["client_name"] = client_match.group(1).strip().split("\n")[0]
            email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", message)
            if email_match:
                payload["client_email"] = email_match.group(0)
            return {
                "agent_name": "AgentBillingOps",
                "action": action,
                "payload": payload,
            }

        if any(word in text for word in ["iva", "contabilidad", "conciliar", "asiento", "impuesto"]):
            action = "vat_draft" if "iva" in text or "impuesto" in text else "classify_transaction"
            payload = {}
            if amount_eur is not None:
                payload["amount_eur"] = amount_eur
            return {
                "agent_name": "AgentAccountingAssistantES",
                "action": action,
                "payload": payload,
            }

        if any(word in text for word in ["lead", "propuesta", "venta", "pipeline", "follow"]):
            payload = {}
            if amount_eur is not None:
                payload["deal_value_eur"] = amount_eur
            return {
                "agent_name": "AgentSalesPipeline",
                "action": "draft_proposal" if "propuesta" in text else "qualify_lead",
                "payload": payload,
            }

        if any(word in text for word in ["onboarding", "incidencia", "sla", "cliente"]):
            action = "incident_triage" if "incidencia" in text else "client_onboarding"
            return {
                "agent_name": "AgentClientDeliveryManager",
                "action": action,
                "payload": {"production_outage": "incidencia" in text},
            }

        if any(word in text for word in ["rgpd", "compliance", "acceso", "politica", "sensible"]):
            return {
                "agent_name": "AgentGovernanceAndCompliance",
                "action": "policy_check",
                "payload": {"sensitive_data": "sensible" in text or "rgpd" in text},
            }

        return {
            "agent_name": "AgentClientDeliveryManager",
            "action": "sla_followup",
            "payload": {"note": message},
        }
