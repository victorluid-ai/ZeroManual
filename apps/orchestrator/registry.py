from __future__ import annotations

from apps.agents.accounting_es import AgentAccountingAssistantES
from apps.agents.billing_ops import AgentBillingOps
from apps.agents.delivery_manager import AgentClientDeliveryManager
from apps.agents.governance_compliance import AgentGovernanceAndCompliance
from apps.agents.sales_pipeline import AgentSalesPipeline
from apps.agents.base import BaseAutonomousAgent
from apps.orchestrator.store import DataStore


def build_agent_registry(store: DataStore | None = None) -> dict[str, BaseAutonomousAgent]:
    agents: list[BaseAutonomousAgent] = [
        AgentBillingOps(store=store),
        AgentAccountingAssistantES(store=store),
        AgentClientDeliveryManager(store=store),
        AgentSalesPipeline(store=store),
        AgentGovernanceAndCompliance(store=store),
    ]
    return {agent.name: agent for agent in agents}
