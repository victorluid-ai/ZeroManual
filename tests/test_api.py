from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "test.db"))
    import importlib
    import apps.interface.api as api_module
    importlib.reload(api_module)
    return TestClient(api_module.app)


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_admin_page_served(client: TestClient) -> None:
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert "Gestión web" in resp.text
    assert "Facturas" not in resp.text
    assert "Aprobaciones" not in resp.text


def test_ui_ops_console_removed(client: TestClient) -> None:
    resp = client.get("/ui")
    assert resp.status_code == 404


def test_ops_event_routes_removed(client: TestClient) -> None:
    assert client.get("/api/v1/agents").status_code == 404
    assert client.post("/api/v1/events", json={}).status_code == 404
    assert client.get("/api/v1/invoices").status_code == 404


def _admin_auth(client: TestClient) -> dict[str, str]:
    import apps.interface.api as api_module

    api_module._LOGIN_ATTEMPTS.clear()
    password = "admin-test-pass"
    store = api_module.runtime.store
    for u in list(store.list_users()):
        store.delete_user(u["user_id"])
    store.create_user("admin", "admin@test.local", password, "admin")
    resp = client.post("/auth/login", json={"username": "admin", "password": password})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _register_client(client: TestClient, email: str) -> dict:
    resp = client.post(
        "/client/register",
        json={"name": "Test Biz", "email": email, "password": "secret123"},
    )
    assert resp.status_code == 200
    return resp.json()


def test_client_register_login_me(client: TestClient) -> None:
    reg = _register_client(client, "a@example.com")
    assert "token" in reg
    auth = {"Authorization": f"Bearer {reg['token']}"}
    me = client.get("/client/me", headers=auth)
    assert me.status_code == 200
    assert me.json()["client"]["email"] == "a@example.com"


def test_pending_automation_requires_auth(client: TestClient) -> None:
    resp = client.post("/client/pending-automation", json={"automation_type": "google_reviews"})
    assert resp.status_code == 401


def test_activate_requires_google_connected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    reg = _register_client(client, "b@example.com")
    auth = {"Authorization": f"Bearer {reg['token']}"}
    resp = client.post("/client/automations/google_reviews/activate", headers=auth)
    assert resp.status_code == 400
    assert "Google" in resp.json()["detail"]


def test_google_callback_auto_activates_pending_automation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    import apps.interface.api as api_module

    reg = _register_client(client, "c@example.com")
    client_id = reg["client"]["client_id"]
    auth = {"Authorization": f"Bearer {reg['token']}"}
    client.post("/client/pending-automation", json={"automation_type": "google_reviews"}, headers=auth)

    monkeypatch.setattr(
        api_module._google_oauth,
        "exchange_code",
        lambda code, state: (client_id, {"access_token": "tok", "refresh_token": "reftok", "expires_in": 3600}),
    )
    monkeypatch.setattr(api_module._google_oauth, "get_user_email", lambda token: "biz@example.com")
    monkeypatch.setattr(api_module._n8n, "duplicate_template", lambda **kwargs: "wf-fake")

    resp = client.get("/client/google/callback?code=abc&state=xyz", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "activated=google_reviews" in resp.headers.get("location", "")


def test_google_callback_without_pending_automation_redirects_connected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    reg = _register_client(client, "d@example.com")
    client_id = reg["client"]["client_id"]
    monkeypatch.setattr(
        api_module._google_oauth,
        "exchange_code",
        lambda code, state: (client_id, {"access_token": "tok", "refresh_token": "reftok", "expires_in": 3600}),
    )
    monkeypatch.setattr(api_module._google_oauth, "get_user_email", lambda token: "biz@example.com")
    resp = client.get("/client/google/callback?code=abc&state=xyz", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "connected=1" in resp.headers.get("location", "")


def test_login_rate_limited_after_repeated_failures(client: TestClient) -> None:
    for _ in range(5):
        resp = client.post("/auth/login", json={"username": "admin", "password": "wrong-password"})
        assert resp.status_code == 401
    blocked = client.post("/auth/login", json={"username": "admin", "password": "wrong-password"})
    assert blocked.status_code == 429


def test_admin_users_and_clients_crud(client: TestClient) -> None:
    auth = _admin_auth(client)
    created = client.post(
        "/api/v1/admin/clients",
        json={"name": "Panadería", "email": "pana@example.com", "password": "secret123"},
        headers=auth,
    )
    assert created.status_code == 200
    client_id = created.json()["client"]["client_id"]

    listing = client.get("/api/v1/admin/clients", headers=auth)
    assert listing.status_code == 200
    assert any(c["client_id"] == client_id for c in listing.json()["clients"])

    deleted = client.delete(f"/api/v1/admin/clients/{client_id}", headers=auth)
    assert deleted.status_code == 200

    users = client.get("/api/v1/admin/users", headers=auth)
    assert users.status_code == 200
    assert any(u["username"] == "admin" for u in users.json()["users"])


def test_admin_companies_route_removed(client: TestClient) -> None:
    auth = _admin_auth(client)
    assert client.get("/api/v1/admin/companies", headers=auth).status_code == 404


def test_homepage_activation_state_fetch(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
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

    deact = client.delete("/client/automations/google_reviews", headers=auth)
    assert deact.status_code == 200
