"""Bucle simulado: reseña → borrador en /client → aceptar, editar o rechazar.

La publicación a Google no sale de estos tests: ``trigger_publish_reply`` está mockeado.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("MANUALZERO_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("ZEROMANUAL_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("MANUALZERO_WEBHOOK_SECRET", "test-webhook-secret")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "draft-loop.db"))
    import importlib
    import apps.interface.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


def _activate(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, str]:
    import apps.interface.api as api_module

    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    reg = client.post(
        "/client/register",
        json={"name": "Reviews Biz", "email": "loop@example.com", "password": "secret123"},
    )
    assert reg.status_code == 200
    body = reg.json()
    client_id = body["client"]["client_id"]
    auth = {"Authorization": f"Bearer {body['token']}"}
    api_module.runtime.store.save_google_creds(
        client_id=client_id,
        refresh_token="reftok",
        access_token="tok",
        token_expiry=None,
        google_email="biz@example.com",
        location_id="accounts/1/locations/1",
    )
    monkeypatch.setattr(api_module._n8n, "duplicate_template", lambda **kwargs: "wf-reviews-1")
    activated = client.post("/client/automations/google_reviews/activate", headers=auth)
    assert activated.status_code == 200
    return auth, client_id


def _push(client: TestClient, client_id: str, review_id: str, reply: str) -> dict:
    resp = client.post(
        "/internal/automations/google_reviews/drafts",
        headers={"X-Webhook-Secret": "test-webhook-secret"},
        json={
            "client_id": client_id,
            "review_id": review_id,
            "reviewer_name": "Ana",
            "rating": "FIVE",
            "source_text": "Muy bueno",
            "suggested_reply": reply,
        },
    )
    assert resp.status_code == 200
    return resp.json()


def test_simulated_review_accept_edit_and_reject(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate(client, monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append(payload),
    )

    pushed = _push(client, client_id, "rev-accept", "Gracias Ana")
    draft_id = pushed["draft"]["draft_id"]
    assert pushed["draft"]["status"] == "pending"
    assert calls == []

    listed = client.get("/client/automations/google_reviews/drafts?status=pending", headers=auth)
    assert listed.status_code == 200
    pending = listed.json()["drafts"]
    assert len(pending) == 1
    assert pending[0]["draft_id"] == draft_id
    assert pending[0]["suggested_reply"] == "Gracias Ana"
    assert pending[0]["review_id"] == "rev-accept"

    accepted = client.post(
        f"/client/drafts/{draft_id}/approve",
        headers=auth,
        json={"final_reply": "Gracias Ana"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["draft"]["status"] == "approved"
    assert calls == [
        {
            "draft_id": draft_id,
            "client_id": client_id,
            "business_id": calls[0]["business_id"] if calls else None,
            "review_id": "rev-accept",
            "final_reply": "Gracias Ana",
        }
    ]
    assert calls[0]["final_reply"] == "Gracias Ana"

    edited_push = _push(client, client_id, "rev-edit", "Texto sugerido")
    edited = client.post(
        f"/client/drafts/{edited_push['draft']['draft_id']}/approve",
        headers=auth,
        json={"final_reply": "Texto editado por el cliente"},
    )
    assert edited.status_code == 200
    assert edited.json()["draft"]["status"] == "edited"
    assert edited.json()["draft"]["final_reply"] == "Texto editado por el cliente"
    assert calls[-1]["review_id"] == "rev-edit"
    assert calls[-1]["final_reply"] == "Texto editado por el cliente"

    rejected_push = _push(client, client_id, "rev-reject", "No enviar")
    before = len(calls)
    rejected = client.post(
        f"/client/drafts/{rejected_push['draft']['draft_id']}/reject",
        headers=auth,
    )
    assert rejected.status_code == 200
    assert rejected.json()["draft"]["status"] == "rejected"
    assert len(calls) == before

    again = client.post(
        f"/client/drafts/{rejected_push['draft']['draft_id']}/reject",
        headers=auth,
    )
    assert again.status_code == 400
    assert len(calls) == before

    history = client.get("/client/automations/google_reviews/drafts", headers=auth)
    statuses = {row["review_id"]: row["status"] for row in history.json()["drafts"]}
    assert statuses == {
        "rev-accept": "approved",
        "rev-edit": "edited",
        "rev-reject": "rejected",
    }


def test_repeat_push_is_idempotent_and_does_not_republish(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate(client, monkeypatch)
    business_id = api_module.runtime.store.ensure_default_business(client_id)["business_id"]
    api_module.runtime.store.update_automation_settings(
        client_id, business_id, "google_reviews", "auto"
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append(payload),
    )

    first = _push(client, client_id, "rev-same", "Gracias")
    second = _push(client, client_id, "rev-same", "Gracias otra vez")
    assert first["draft"]["draft_id"] == second["draft"]["draft_id"]
    assert second["draft"]["status"] == "auto_sent"
    assert second["draft"]["suggested_reply"] == "Gracias"
    assert len(calls) == 1

    listed = client.get("/client/automations/google_reviews/drafts", headers=auth)
    assert len(listed.json()["drafts"]) == 1


def test_empty_approve_does_not_publish(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate(client, monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append(payload),
    )
    pushed = _push(client, client_id, "rev-empty", "Borrador")
    resp = client.post(
        f"/client/drafts/{pushed['draft']['draft_id']}/approve",
        headers=auth,
        json={"final_reply": "   "},
    )
    assert resp.status_code == 400
    assert calls == []
    still = client.get("/client/automations/google_reviews/drafts?status=pending", headers=auth)
    assert len(still.json()["drafts"]) == 1


def test_client_ui_offers_edit_accept_and_reject() -> None:
    html = Path("apps/interface/client.html").read_text(encoding="utf-8")
    assert "Puedes editar el texto" in html
    assert 'class="draft-text"' in html
    assert "/approve" in html
    assert "/reject" in html
    assert 'data-action="approve"' in html
    assert 'data-action="reject"' in html
    assert "Aprobar y publicar" in html
    assert "Aceptar todas (" in html
    assert "Respuestas automáticas" in html
    assert "Buscar por nombre" in html
    assert "Aprobada por ti" in html
    assert "Editada por ti" in html
    assert "Automática" in html
    assert "¿Activar respuestas automáticas?" in html
    assert "Activar y publicar pendientes" in html
    assert "topbar-brand-mark" in html
    assert 'reply_mode' in html
    assert "Se publicarán en Google" in html
