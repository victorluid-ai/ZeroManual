from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_API_KEY = "test-suite-key"
API_HEADERS = {"x-api-key": TEST_API_KEY}


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")
    # verify_api_key fails closed now (no key => reject everything), so tests
    # need a real key configured and sent on every non-admin /api/v1/* call.
    monkeypatch.setenv("ZEROMANUAL_API_KEY", TEST_API_KEY)


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
    }, headers=API_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "COMPLETED"


def test_submit_event_high_amount_needs_approval(client: TestClient) -> None:
    resp = client.post("/api/v1/events", json={
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 1500.0, "client_name": "Big Corp"},
    }, headers=API_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "NEEDS_APPROVAL"


def test_list_approvals(client: TestClient) -> None:
    client.post("/api/v1/events", json={
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 900.0, "client_name": "Pending Corp"},
        "event_id": "test-approve-001",
    }, headers=API_HEADERS)
    resp = client.get("/api/v1/approvals", headers=API_HEADERS)
    assert resp.status_code == 200
    pending = resp.json()["pending"]
    assert any(p["event_id"] == "test-approve-001" for p in pending)


def test_approve_event(client: TestClient) -> None:
    client.post("/api/v1/events", json={
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 700.0, "client_name": "Approve Corp"},
        "event_id": "test-approve-002",
    }, headers=API_HEADERS)
    resp = client.post(
        "/api/v1/approvals/test-approve-002/approve", json={"approved_by": "owner"}, headers=API_HEADERS
    )
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


def test_api_key_unset_blocks_everything_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: an unset ZEROMANUAL_API_KEY must reject, not allow."""
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "auth_test3.db"))
    monkeypatch.setenv("ZEROMANUAL_API_KEY", "")
    import importlib
    import apps.interface.api as api_module
    importlib.reload(api_module)
    c = TestClient(api_module.app)
    resp = c.post(
        "/api/v1/events",
        json={"agent_name": "AgentBillingOps", "action": "create_invoice", "payload": {}},
    )
    assert resp.status_code == 401


# ---- Client onboarding: pending-activation-through-OAuth-callback ----


def _register_client(client: TestClient, email: str = "onboard@example.com") -> dict:
    resp = client.post("/client/register", json={"name": "Onboard SL", "email": email, "password": "s3cret!!"})
    assert resp.status_code == 200
    return resp.json()  # {"token": ..., "client": {...}}


def test_client_register_login_me(client: TestClient) -> None:
    reg = _register_client(client)
    auth = {"Authorization": f"Bearer {reg['token']}"}
    me = client.get("/client/me", headers=auth)
    assert me.status_code == 200
    assert me.json()["client"]["email"] == "onboard@example.com"

    login = client.post("/client/login", json={"email": "onboard@example.com", "password": "s3cret!!"})
    assert login.status_code == 200
    assert login.json()["client"]["client_id"] == reg["client"]["client_id"]


def test_pending_automation_requires_auth(client: TestClient) -> None:
    resp = client.post("/client/pending-automation", json={"automation_type": "google_reviews"})
    assert resp.status_code == 401


def test_activate_requires_google_connected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    reg = _register_client(client, "no-google@example.com")
    auth = {"Authorization": f"Bearer {reg['token']}"}
    resp = client.post("/client/automations/google_reviews/activate", headers=auth)
    assert resp.status_code == 400
    assert "Google" in resp.json()["detail"]


def test_google_callback_auto_activates_pending_automation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    import apps.interface.api as api_module

    reg = _register_client(client, "fast-path@example.com")
    client_id = reg["client"]["client_id"]
    auth = {"Authorization": f"Bearer {reg['token']}"}

    pending = client.post(
        "/client/pending-automation", json={"automation_type": "google_reviews"}, headers=auth
    )
    assert pending.status_code == 200
    assert api_module.runtime.store.get_pending_automation(client_id) == "google_reviews"

    monkeypatch.setattr(
        api_module._google_oauth,
        "exchange_code",
        lambda code, state: (client_id, {"access_token": "tok", "refresh_token": "reftok", "expires_in": 3600}),
    )
    monkeypatch.setattr(api_module._google_oauth, "get_user_email", lambda access_token: "biz@example.com")
    monkeypatch.setattr(api_module._n8n, "duplicate_template", lambda **kwargs: "wf-fake-1")

    resp = client.get(
        "/client/google/callback", params={"code": "fake-code", "state": "fake-state"}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/client?activated=google_reviews"

    # Pending flag consumed exactly once.
    assert api_module.runtime.store.get_pending_automation(client_id) is None

    autos = client.get("/client/automations", headers=auth)
    active_types = [a["automation_type"] for a in autos.json()["active"] if a["status"] == "active"]
    assert "google_reviews" in active_types

    status = client.get("/client/google/status", headers=auth)
    assert status.json()["connected"] is True


def test_google_callback_without_pending_automation_redirects_connected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    reg = _register_client(client, "no-pending@example.com")
    client_id = reg["client"]["client_id"]

    monkeypatch.setattr(
        api_module._google_oauth,
        "exchange_code",
        lambda code, state: (client_id, {"access_token": "tok", "refresh_token": "reftok"}),
    )
    monkeypatch.setattr(api_module._google_oauth, "get_user_email", lambda access_token: "biz@example.com")

    resp = client.get(
        "/client/google/callback", params={"code": "fake-code", "state": "fake-state"}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/client?connected=1"


# ---- Business entities (persona fisica / empresa) admin CRUD ----


def _admin_auth(client: TestClient) -> dict:
    import apps.interface.api as api_module
    password = api_module.runtime.store.generated_admin_password
    resp = client.post("/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_login_rate_limited_after_repeated_failures(client: TestClient) -> None:
    for _ in range(5):
        resp = client.post("/auth/login", json={"username": "admin", "password": "wrong-password"})
        assert resp.status_code == 401
    blocked = client.post("/auth/login", json={"username": "admin", "password": "wrong-password"})
    assert blocked.status_code == 429


def test_admin_create_list_company(client: TestClient) -> None:
    auth = _admin_auth(client)
    resp = client.post(
        "/api/v1/admin/companies",
        json={
            "entity_type": "persona_fisica",
            "name": "Victor Luid",
            "tax_id": "12345678Z",
            "invoice_series": "FAC-P",
        },
        headers=auth,
    )
    assert resp.status_code == 200
    entity_id = resp.json()["company"]["entity_id"]

    listing = client.get("/api/v1/admin/companies", headers=auth)
    assert listing.status_code == 200
    assert any(c["entity_id"] == entity_id for c in listing.json()["companies"])


def test_admin_create_company_rejects_invalid_tax_id(client: TestClient) -> None:
    auth = _admin_auth(client)
    resp = client.post(
        "/api/v1/admin/companies",
        json={"entity_type": "empresa", "name": "Mala SL", "tax_id": "not-a-nif", "invoice_series": "FAC-M"},
        headers=auth,
    )
    assert resp.status_code == 400


def test_admin_update_company(client: TestClient) -> None:
    auth = _admin_auth(client)
    created = client.post(
        "/api/v1/admin/companies",
        json={"entity_type": "empresa", "name": "Old SL", "tax_id": "B12345674", "invoice_series": "FAC-O"},
        headers=auth,
    ).json()["company"]
    resp = client.put(
        f"/api/v1/admin/companies/{created['entity_id']}",
        json={"name": "New SL"},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.json()["company"]["name"] == "New SL"
    assert resp.json()["company"]["tax_id"] == "B12345674"


def test_invoices_endpoint_entity_id_filter(client: TestClient) -> None:
    auth = _admin_auth(client)
    other = client.post(
        "/api/v1/admin/companies",
        json={"entity_type": "empresa", "name": "Otra SL", "tax_id": "B87654323", "invoice_series": "FAC-OTRA"},
        headers=auth,
    ).json()["company"]

    client.post("/api/v1/events", json={
        "agent_name": "AgentBillingOps", "action": "create_invoice",
        "payload": {"amount_eur": 50.0, "client_name": "Default Entity Client"},
    }, headers=auth)
    client.post("/api/v1/events", json={
        "agent_name": "AgentBillingOps", "action": "create_invoice",
        "payload": {"amount_eur": 60.0, "client_name": "Other Entity Client"},
        "entity_id": other["entity_id"],
    }, headers=auth)

    resp = client.get(f"/api/v1/admin/invoices?entity_id={other['entity_id']}", headers=auth)
    assert resp.status_code == 200
    names = [i["client_name"] for i in resp.json()["invoices"]]
    assert "Other Entity Client" in names
    assert "Default Entity Client" not in names


def test_ledger_endpoint_entity_id_filter(client: TestClient) -> None:
    auth = _admin_auth(client)
    other = client.post(
        "/api/v1/admin/companies",
        json={"entity_type": "empresa", "name": "Ledger SL", "tax_id": "B11223344", "invoice_series": "FAC-L"},
        headers=auth,
    ).json()["company"]

    client.post("/api/v1/events", json={
        "agent_name": "AgentAccountingAssistantES", "action": "classify_transaction",
        "payload": {"amount_eur": 30.0, "client_name": "Ledger Client"},
        "entity_id": other["entity_id"],
    }, headers=auth)

    resp = client.get(f"/api/v1/admin/ledger?entity_id={other['entity_id']}", headers=auth)
    assert resp.status_code == 200
    assert any(e["client_name"] == "Ledger Client" for e in resp.json()["ledger_entries"])


def test_submit_event_with_entity_id_scopes_invoice(client: TestClient) -> None:
    auth = _admin_auth(client)
    other = client.post(
        "/api/v1/admin/companies",
        json={"entity_type": "empresa", "name": "Scoped SL", "tax_id": "B99998882", "invoice_series": "FAC-S"},
        headers=auth,
    ).json()["company"]

    resp = client.post(
        "/api/v1/admin/events",
        json={
            "agent_name": "AgentBillingOps", "action": "create_invoice",
            "payload": {"amount_eur": 40.0, "client_name": "Scoped Client"},
            "entity_id": other["entity_id"],
        },
        headers=auth,
    )
    assert resp.status_code == 200
    invoice_id = resp.json()["output"]["invoice_id"]

    invoice_resp = client.get(f"/api/v1/admin/invoices?entity_id={other['entity_id']}", headers=auth)
    invoice = next(i for i in invoice_resp.json()["invoices"] if i["invoice_id"] == invoice_id)
    assert invoice["invoice_number"].startswith("FAC-S-")


def test_homepage_activation_state_fetch(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers the same endpoints app.jsx polls on mount to show 'Activa' on the grid."""
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    import apps.interface.api as api_module

    reg = _register_client(client, "grid-state@example.com")
    client_id = reg["client"]["client_id"]
    auth = {"Authorization": f"Bearer {reg['token']}"}

    api_module.runtime.store.save_google_creds(
        client_id=client_id,
        refresh_token="reftok",
        access_token="tok",
        token_expiry=None,
        google_email="biz@example.com",
        location_id=None,
    )
    monkeypatch.setattr(api_module._n8n, "duplicate_template", lambda **kwargs: "wf-fake-2")

    activate = client.post("/client/automations/google_reviews/activate", headers=auth)
    assert activate.status_code == 200

    autos = client.get("/client/automations", headers=auth).json()
    active_types = [a["automation_type"] for a in autos["active"] if a["status"] == "active"]
    assert active_types == ["google_reviews"]

    status = client.get("/client/google/status", headers=auth).json()
    assert status["connected"] is True

    # Regression: manual deactivate (power-user path inside /client) still works.
    deact = client.delete("/client/automations/google_reviews", headers=auth)
    assert deact.status_code == 200
    autos_after = client.get("/client/automations", headers=auth).json()
    assert all(a["status"] != "active" for a in autos_after["active"])
