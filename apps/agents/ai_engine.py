from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.llm.claude_client import ClaudeClient
from apps.orchestrator.models import AgentDecision, Event, RiskLevel


class AgentAIEngine:
    def __init__(self) -> None:
        self.claude = ClaudeClient()

    def load_prompt(self, agent_key: str) -> str:
        path = Path(__file__).parent / "prompts" / f"{agent_key}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return f"You are {agent_key} agent for ZeroManual."

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

    def choose_tool_with_ai(
        self,
        agent_key: str,
        event: Event,
        decision: AgentDecision,
        available_tools: list[str],
    ) -> dict[str, Any] | None:
        if not self.claude.enabled:
            return None

        system = self.load_prompt(agent_key)
        user = (
            "Elige UNA tool para ejecutar. Responde SOLO JSON:\n"
            '{"tool_name": "...", "arguments": {...}}\n'
            f"Tools disponibles: {available_tools}\n"
            f"Evento: {event.model_dump(mode='json')}\n"
            f"Decision: {decision.model_dump(mode='json')}\n"
            "Para create_invoice usa create_invoice_draft con event_id, client_name, amount_eur."
        )
        return self.claude.complete_json(system=system, user=user, max_tokens=500)
