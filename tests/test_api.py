from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ZEROMANUAL_WEBHOOK_SECRET", "whsec")
    monkeypatch.delenv("ZEROMANUAL_OPS_URL", raising=False)
    monkeypatch.delenv("ZEROMANUAL_OPS_API_KEY", raising=False)
    import importlib
    import apps.interface.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "zeromanual-commercial"
    assert body["ops_bridge"] is False


def test_ops_routes_removed(client: TestClient) -> None:
    assert client.get("/api/v1/agents").status_code == 404
    assert client.get("/api/v1/invoices").status_code == 404
    assert client.get("/api/v1/approvals").status_code == 404


def test_client_register_and_login(client: TestClient) -> None:
    resp = client.post(
        "/client/register",
        json={"name": "Acme SL", "email": "a@acme.test", "password": "secret123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["client"]["email"] == "a@acme.test"
    assert data["token"]

    login = client.post(
        "/client/login",
        json={"email": "a@acme.test", "password": "secret123"},
    )
    assert login.status_code == 200
    token = login.json()["token"]
    me = client.get("/client/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["client"]["name"] == "Acme SL"


def test_admin_clients_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/admin/clients").status_code == 401


def test_admin_login_users_clients(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.interface.api as api_module

    # Capture seeded admin password by creating store with known password via create_user after wipe
    store = api_module.store
    users = store.list_users()
    assert users
    # Reset admin password for test
    store.delete_user(users[0]["user_id"])
    store.create_user("admin", "", "admin-test-pass", "admin")

    login = client.post("/auth/login", json={"username": "admin", "password": "admin-test-pass"})
    assert login.status_code == 200
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    users_resp = client.get("/api/v1/admin/users", headers=headers)
    assert users_resp.status_code == 200
    assert any(u["username"] == "admin" for u in users_resp.json()["users"])

    create = client.post(
        "/api/v1/admin/clients",
        json={"name": "Negocio", "email": "n@test.com", "password": "x"},
        headers=headers,
    )
    assert create.status_code == 200
    listed = client.get("/api/v1/admin/clients", headers=headers)
    assert listed.status_code == 200
    assert any(c["email"] == "n@test.com" for c in listed.json()["clients"])


def test_webhook_draft(client: TestClient) -> None:
    reg = client.post(
        "/client/register",
        json={"name": "B", "email": "b@test.com", "password": "pw"},
    )
    client_id = reg.json()["client"]["client_id"]
    resp = client.post(
        "/internal/automations/google_reviews/drafts",
        headers={"X-Webhook-Secret": "whsec"},
        json={
            "client_id": client_id,
            "suggested_reply": "Gracias",
            "source_text": "Genial",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["draft"]["status"] == "pending"
