from __future__ import annotations

from apps.llm.claude_client import ClaudeClient
from apps.orchestrator.models import AgentDecision, Event, RiskLevel


class AgentAIEngine:
    def __init__(self) -> None:
        self.claude = ClaudeClient()

    def plan_with_ai(
        self,
        agent_key: str,
        event: Event,
        approval_threshold_eur: float,
        client_context: str = "",
    ) -> AgentDecision | None:
        if not self.claude.enabled:
            return None

        system = "Eres un planificador de agentes ZeroManual. Responde solo JSON compacto."
        user = (
            "Analiza este evento y devuelve SOLO JSON con claves:\n"
            "summary (string), risk_level (A_LOW|B_MEDIUM|C_HIGH), "
            "proposed_actions (array of strings), requires_human_approval (boolean).\n"
            f"Umbral aprobacion EUR: {approval_threshold_eur}\n"
            f"Evento: action={event.action}, payload={event.payload}\n"
            f"Contexto cliente: {client_context or 'sin datos'}\n"
            "Si amount_eur supera el umbral, requires_human_approval debe ser true."
        )
        data = self.claude.complete_json(system=system, user=user)
        if not data:
            return None

        risk_raw = str(data.get("risk_level", "B_MEDIUM"))
        try:
            risk = RiskLevel(risk_raw)
        except ValueError:
            risk = RiskLevel.B_MEDIUM

        amount = event.payload.get("amount_eur")
        if amount is not None and float(amount) > approval_threshold_eur:
            requires = True
            risk = RiskLevel.C_HIGH
        else:
            requires = bool(data.get("requires_human_approval", False))

        return AgentDecision(
            summary=str(data.get("summary", "AI planned action.")),
            risk_level=risk,
            proposed_actions=list(data.get("proposed_actions", [])),
            requires_human_approval=requires,
        )
