from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")
    monkeypatch.setenv("ZEROMANUAL_API_KEY", "")  # auth disabled in tests


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("APPROVAL_THRESHOLD_EUR", "500.0")
    # Import after env patched so OrchestratorRuntime reads correct db path
    import importlib
    import apps.interface.api as api_module
    importlib.reload(api_module)
    return TestClient(api_module.app)


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_agents(client: TestClient) -> None:
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200
    names = [a["agent_name"] for a in resp.json()["agents"]]
    assert "AgentBillingOps" in names


def test_submit_event_low_amount(client: TestClient) -> None:
    resp = client.post("/api/v1/events", json={
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 100.0, "client_name": "Test SL"},
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


def test_submit_event_high_amount_needs_approval(client: TestClient) -> None:
    resp = client.post("/api/v1/events", json={
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 1500.0, "client_name": "Big Corp"},
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "NEEDS_APPROVAL"


def test_list_approvals(client: TestClient) -> None:
    client.post("/api/v1/events", json={
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 900.0, "client_name": "Pending Corp"},
        "event_id": "test-approve-001",
    })
    resp = client.get("/api/v1/approvals")
    assert resp.status_code == 200
    pending = resp.json()["pending"]
    assert any(p["event_id"] == "test-approve-001" for p in pending)


def test_approve_event(client: TestClient) -> None:
    client.post("/api/v1/events", json={
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 700.0, "client_name": "Approve Corp"},
        "event_id": "test-approve-002",
    })
    resp = client.post("/api/v1/approvals/test-approve-002/approve", json={"approved_by": "owner"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


def test_api_key_auth_blocks_when_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "auth_test.db"))
    monkeypatch.setenv("ZEROMANUAL_API_KEY", "secret-key-123")
    import importlib
    import apps.interface.api as api_module
    importlib.reload(api_module)
    c = TestClient(api_module.app)
    resp = c.post("/api/v1/events", json={
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {},
    })
    assert resp.status_code == 401


def test_api_key_auth_passes_with_correct_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "auth_test2.db"))
    monkeypatch.setenv("ZEROMANUAL_API_KEY", "secret-key-123")
    import importlib
    import apps.interface.api as api_module
    importlib.reload(api_module)
    c = TestClient(api_module.app)
    resp = c.post(
        "/api/v1/events",
        json={"agent_name": "AgentBillingOps", "action": "create_invoice", "payload": {"amount_eur": 50.0, "client_name": "Auth SL"}},
        headers={"x-api-key": "secret-key-123"},
    )
    assert resp.status_code == 200
