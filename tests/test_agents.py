from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.agents.billing_ops import AgentBillingOps
from apps.agents.accounting_es import AgentAccountingAssistantES
from apps.agents.delivery_manager import AgentClientDeliveryManager
from apps.agents.sales_pipeline import AgentSalesPipeline
from apps.agents.governance_compliance import AgentGovernanceAndCompliance
from apps.orchestrator.models import AgentDecision, Event, ExecutionStatus, RiskLevel
from apps.orchestrator.store import DataStore


THRESHOLD = 500.0


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(db_path=str(tmp_path / "test.db"))


def make_event(agent: str, action: str, payload: dict, entity_id: str | None = None) -> Event:
    kwargs = dict(event_id="test-0001", source="test", agent_name=agent, action=action, payload=payload)
    if entity_id is not None:
        kwargs["entity_id"] = entity_id
    return Event(**kwargs)


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


def test_billing_unsupported_action_fails_cleanly_no_fake_invoice(store: DataStore) -> None:
    agent = AgentBillingOps(store=store)
    event = make_event("AgentBillingOps", "not_a_real_action", {"amount_eur": 50.0})
    result = agent.handle_event(event, THRESHOLD)
    assert result.status == ExecutionStatus.FAILED
    assert "error" in result.output
    assert store.list_invoices() == []


def test_billing_send_reminder_without_invoice_id_fails_cleanly(store: DataStore) -> None:
    agent = AgentBillingOps(store=store)
    event = make_event("AgentBillingOps", "send_reminder", {})
    result = agent.handle_event(event, THRESHOLD)
    assert result.status == ExecutionStatus.FAILED


def test_billing_duplicate_event_id_does_not_burn_new_invoice_number(store: DataStore) -> None:
    agent = AgentBillingOps(store=store)
    event = make_event("AgentBillingOps", "create_invoice", {"amount_eur": 80.0, "client_name": "Retry SL"})
    decision = agent.plan(event, THRESHOLD)
    result1 = agent.execute(event, decision)
    result2 = agent.execute(event, decision)
    assert result1["invoice_id"] == result2["invoice_id"]
    assert result1["invoice_number"] == result2["invoice_number"]


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


def test_ai_cannot_waive_mandatory_approval(store: DataStore, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for the audit finding: the LLM's own JSON must never be
    able to turn off a human-approval requirement the deterministic rules
    already decided (vat_draft here; same mechanism protects every agent)."""
    agent = AgentAccountingAssistantES(store=store)
    event = make_event("AgentAccountingAssistantES", "vat_draft", {"period": "Q1-2025"})
    default = agent.plan(event, THRESHOLD)
    assert default.requires_human_approval  # sanity check on the deterministic rule

    rogue_ai_decision = AgentDecision(
        summary="La IA decide que no hace falta aprobación",
        risk_level=RiskLevel.A_LOW,
        proposed_actions=[],
        requires_human_approval=False,
    )
    monkeypatch.setattr(agent._ai, "plan_with_ai", lambda **kwargs: rogue_ai_decision)
    result = agent._plan_with_ai_fallback(event, THRESHOLD, default)
    assert result.requires_human_approval is True


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


def test_sales_high_value_deal_requires_approval(store: DataStore) -> None:
    agent = AgentSalesPipeline(store=store)
    event = make_event(
        "AgentSalesPipeline", "draft_proposal",
        {"lead_name": "Gran Cuenta SA", "deal_value_eur": THRESHOLD * 3},
    )
    decision = agent.plan(event, THRESHOLD)
    assert decision.requires_human_approval
    assert decision.risk_level == RiskLevel.C_HIGH


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


# --- Multi-entity (persona fisica / empresa) scoping ---

def test_billing_agent_writes_invoice_scoped_to_entity_id(store: DataStore) -> None:
    other = store.create_business_entity(
        entity_type="empresa", name="Otra Empresa", tax_id="B12345678", invoice_series="FAC-OTRA"
    )
    agent = AgentBillingOps(store=store)
    event = make_event(
        "AgentBillingOps", "create_invoice",
        {"amount_eur": 100.0, "client_name": "Test SL"},
        entity_id=other["entity_id"],
    )
    result = agent.handle_event(event, THRESHOLD)
    assert result.status == ExecutionStatus.COMPLETED
    invoice = store.get_invoice(result.output["invoice_id"])
    assert invoice is not None
    assert invoice["entity_id"] == other["entity_id"]
    assert invoice["invoice_number"].startswith("FAC-OTRA-")


def test_accounting_agent_ledger_entry_respects_entity_id(store: DataStore) -> None:
    other = store.create_business_entity(
        entity_type="persona_fisica", name="Victor Luid", tax_id="12345678A", invoice_series="FAC-P"
    )
    agent = AgentAccountingAssistantES(store=store)
    event = make_event(
        "AgentAccountingAssistantES", "classify_transaction",
        {"amount_eur": 50.0, "invoice_id": "INV-XYZ"},
        entity_id=other["entity_id"],
    )
    result = agent.handle_event(event, THRESHOLD)
    assert result.status == ExecutionStatus.COMPLETED
    entries = store.list_ledger_entries(entity_id=other["entity_id"])
    assert any(e["entry_id"] == result.output["ledger_entry_id"] for e in entries)
