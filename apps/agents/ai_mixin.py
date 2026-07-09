from __future__ import annotations

from apps.zeromanual_env import zm_env
from typing import Any

from apps.agents.ai_engine import AgentAIEngine
from apps.agents.tools.registry import ToolRegistry
from apps.orchestrator.models import AgentDecision, Event
from apps.orchestrator.store import DataStore


class AgentAIMixin:
    """Patron eco/full/off compartido por agentes de negocio."""

    def _init_ai(self, store: DataStore | None, agent_key: str) -> None:
        self._store = store
        self._agent_key = agent_key
        self._ai = AgentAIEngine()
        self._tools: ToolRegistry | None = ToolRegistry(store) if store else None
        self._ai_mode = zm_env("AI_MODE", "eco").lower()

    def _use_ai_for_plan(self, simple_case: bool) -> bool:
        if self._ai_mode == "off" or not self._ai.claude.enabled:
            return False
        if self._ai_mode == "full":
            return True
        return not simple_case

    def _plan_with_ai_fallback(
        self,
        event: Event,
        approval_threshold_eur: float,
        default: AgentDecision,
    ) -> AgentDecision:
        client_context = self._client_context(event)
        ai_decision = self._ai.plan_with_ai(
            agent_key=self._agent_key,
            event=event,
            approval_threshold_eur=approval_threshold_eur,
            client_context=client_context,
        )
        return ai_decision if ai_decision is not None else default

    def _client_context(self, event: Event) -> str:
        if not self._store:
            return ""
        client_name = event.payload.get("client_name") or event.payload.get("client")
        if not client_name:
            return ""
        return self._store.get_client_memory(str(client_name)) or ""

    def _run_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        if not self._tools:
            return None
        return self._tools.run(tool_name, arguments)
