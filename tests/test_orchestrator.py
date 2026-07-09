from __future__ import annotations

from pathlib import Path

import pytest

from apps.orchestrator.runtime import OrchestratorRuntime
from apps.orchestrator.config import Settings


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> OrchestratorRuntime:
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", db)
    monkeypatch.setenv("APPROVAL_THRESHOLD_EUR", "500.0")
    return OrchestratorRuntime()


def test_unknown_agent_returns_error(runtime: OrchestratorRuntime) -> None:
    result = runtime.process_event({
        "event_id": "evt-001",
        "source": "test",
        "agent_name": "NonExistentAgent",
        "action": "do_something",
        "payload": {},
    })
    assert "error" in result


def test_billing_event_completed(runtime: OrchestratorRuntime) -> None:
    result = runtime.process_event({
        "event_id": "evt-002",
        "source": "test",
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 100.0, "client_name": "Test SL"},
    })
    assert result["status"] == "COMPLETED"


def test_billing_high_amount_needs_approval(runtime: OrchestratorRuntime) -> None:
    result = runtime.process_event({
        "event_id": "evt-003",
        "source": "test",
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 1000.0, "client_name": "Big Corp"},
    })
    assert result["status"] == "NEEDS_APPROVAL"
    pending = runtime.list_pending_approvals()
    assert any(p["event_id"] == "evt-003" for p in pending)


def test_approve_pending_event(runtime: OrchestratorRuntime) -> None:
    runtime.process_event({
        "event_id": "evt-004",
        "source": "test",
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 1000.0, "client_name": "VIP Corp"},
    })
    result = runtime.approve(event_id="evt-004", approved_by="owner")
    assert result["status"] == "COMPLETED"
    assert result["approved_by"] == "owner"
    pending = runtime.list_pending_approvals()
    assert not any(p["event_id"] == "evt-004" for p in pending)


def test_reject_pending_event(runtime: OrchestratorRuntime) -> None:
    runtime.process_event({
        "event_id": "evt-005",
        "source": "test",
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 2000.0, "client_name": "Rejected Corp"},
    })
    result = runtime.reject(event_id="evt-005", rejected_by="owner", reason="Too large")
    assert result["status"] == "REJECTED"
    pending = runtime.list_pending_approvals()
    assert not any(p["event_id"] == "evt-005" for p in pending)


def test_list_agents(runtime: OrchestratorRuntime) -> None:
    agents = runtime.list_agents()
    names = [a["agent_name"] for a in agents]
    assert "AgentBillingOps" in names
    assert "AgentAccountingAssistantES" in names
    assert "AgentSalesPipeline" in names


def test_billing_triggers_accounting_handoff(runtime: OrchestratorRuntime) -> None:
    result = runtime.process_event({
        "event_id": "evt-006",
        "source": "test",
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 200.0, "client_name": "Handoff SL"},
    })
    assert result["status"] == "COMPLETED"
    assert "handoffs" in result
    handoff_agents = [h["event"]["agent_name"] for h in result["handoffs"]]
    assert "AgentAccountingAssistantES" in handoff_agents
