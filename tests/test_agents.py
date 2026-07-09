from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.agents.billing_ops import AgentBillingOps
from apps.agents.accounting_es import AgentAccountingAssistantES
from apps.agents.delivery_manager import AgentClientDeliveryManager
from apps.agents.sales_pipeline import AgentSalesPipeline
from apps.agents.governance_compliance import AgentGovernanceAndCompliance
from apps.orchestrator.models import Event, ExecutionStatus, RiskLevel
from apps.orchestrator.store import DataStore


THRESHOLD = 500.0


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(db_path=str(tmp_path / "test.db"))


def make_event(agent: str, action: str, payload: dict) -> Event:
    return Event(event_id="test-0001", source="test", agent_name=agent, action=action, payload=payload)


# --- AgentBillingOps ---

def test_billing_low_amount_no_approval(store: DataStore) -> None:
    agent = AgentBillingOps(store=store)
    event = make_event("AgentBillingOps", "create_invoice", {"amount_eur": 100.0, "client_name": "Test SL"})
    decision = agent.plan(event, THRESHOLD)
    assert not decision.requires_human_approval
    assert decision.risk_level == RiskLevel.A_LOW


def test_billing_high_amount_requires_approval(store: DataStore) -> None:
    agent = AgentBillingOps(store=store)
    event = make_event("AgentBillingOps", "create_invoice", {"amount_eur": 600.0, "client_name": "Big Corp"})
    decision = agent.plan(event, THRESHOLD)
    assert decision.requires_human_approval
    assert decision.risk_level == RiskLevel.C_HIGH


def test_billing_handle_event_low_amount(store: DataStore) -> None:
    agent = AgentBillingOps(store=store)
    event = make_event("AgentBillingOps", "create_invoice", {"amount_eur": 200.0, "client_name": "Test SL"})
    result = agent.handle_event(event, THRESHOLD)
    assert result.status == ExecutionStatus.COMPLETED


def test_billing_handle_event_high_amount_needs_approval(store: DataStore) -> None:
    agent = AgentBillingOps(store=store)
    event = make_event("AgentBillingOps", "create_invoice", {"amount_eur": 1000.0, "client_name": "Test SL"})
    result = agent.handle_event(event, THRESHOLD)
    assert result.status == ExecutionStatus.NEEDS_APPROVAL


# --- AgentAccountingAssistantES ---

def test_accounting_classify_no_approval(store: DataStore) -> None:
    agent = AgentAccountingAssistantES(store=store)
    event = make_event("AgentAccountingAssistantES", "classify_transaction", {"amount_eur": 100.0, "invoice_id": "INV-001"})
    decision = agent.plan(event, THRESHOLD)
    assert not decision.requires_human_approval


def test_accounting_vat_draft_always_approval(store: DataStore) -> None:
    agent = AgentAccountingAssistantES(store=store)
    event = make_event("AgentAccountingAssistantES", "vat_draft", {"period": "Q1-2025"})
    decision = agent.plan(event, THRESHOLD)
    assert decision.requires_human_approval


# --- AgentClientDeliveryManager ---

def test_delivery_normal_onboarding_no_approval(store: DataStore) -> None:
    agent = AgentClientDeliveryManager(store=store)
    event = make_event("AgentClientDeliveryManager", "client_onboarding", {"client_name": "Nuevo SL"})
    decision = agent.plan(event, THRESHOLD)
    assert not decision.requires_human_approval
    assert decision.risk_level == RiskLevel.A_LOW


def test_delivery_production_outage_requires_approval(store: DataStore) -> None:
    agent = AgentClientDeliveryManager(store=store)
    event = make_event("AgentClientDeliveryManager", "incident_triage", {"production_outage": True})
    decision = agent.plan(event, THRESHOLD)
    assert decision.requires_human_approval
    assert decision.risk_level == RiskLevel.C_HIGH


# --- AgentSalesPipeline ---

def test_sales_qualify_lead_autonomous(store: DataStore) -> None:
    agent = AgentSalesPipeline(store=store)
    event = make_event("AgentSalesPipeline", "qualify_lead", {"lead_name": "Potencial SA"})
    decision = agent.plan(event, THRESHOLD)
    assert not decision.requires_human_approval


# --- AgentGovernanceAndCompliance ---

def test_governance_sensitive_requires_approval(store: DataStore) -> None:
    agent = AgentGovernanceAndCompliance(store=store)
    event = make_event("AgentGovernanceAndCompliance", "policy_check", {"sensitive_data": True})
    decision = agent.plan(event, THRESHOLD)
    assert decision.requires_human_approval
    assert decision.risk_level == RiskLevel.C_HIGH


def test_governance_routine_no_approval(store: DataStore) -> None:
    agent = AgentGovernanceAndCompliance(store=store)
    event = make_event("AgentGovernanceAndCompliance", "policy_check", {})
    decision = agent.plan(event, THRESHOLD)
    assert not decision.requires_human_approval
