from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from apps.orchestrator.models import AgentDecision, Event, ExecutionResult, ExecutionStatus, RiskLevel


class BaseAutonomousAgent(ABC):
    name: str
    supported_actions: tuple[str, ...]

    def handle_event(self, event: Event, approval_threshold_eur: float) -> ExecutionResult:
        decision = self.plan(event, approval_threshold_eur)
        if decision.requires_human_approval:
            return ExecutionResult(
                status=ExecutionStatus.NEEDS_APPROVAL,
                decision=decision,
                output={"next_step": "human_approval_required"},
                audit_notes=["Escalated to human approval gate."],
            )
        try:
            output = self.execute(event, decision)
        except ValueError as exc:
            # Malformed/unsupported input for this agent+action must fail
            # visibly, never masquerade as a fabricated success.
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                decision=decision,
                output={"error": str(exc)},
                audit_notes=[f"Execution failed: {exc}"],
            )
        return ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            decision=decision,
            output=output,
            audit_notes=["Executed autonomously."],
        )

    @abstractmethod
    def plan(self, event: Event, approval_threshold_eur: float) -> AgentDecision:
        raise NotImplementedError

    @abstractmethod
    def execute(self, event: Event, decision: AgentDecision) -> dict[str, Any]:
        raise NotImplementedError

    def _risk_for_amount(self, amount: float, threshold: float) -> RiskLevel:
        if amount <= threshold * 0.5:
            return RiskLevel.A_LOW
        if amount <= threshold:
            return RiskLevel.B_MEDIUM
        return RiskLevel.C_HIGH
