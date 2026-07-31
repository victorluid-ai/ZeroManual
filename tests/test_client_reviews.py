from __future__ import annotations

import json
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
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "reviews.db"))
    import importlib
    import apps.interface.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


def _register(client: TestClient, email: str = "reviews@example.com") -> dict:
    resp = client.post(
        "/client/register",
        json={"name": "Reviews Biz", "email": email, "password": "secret123"},
    )
    assert resp.status_code == 200
    return resp.json()


def _activate_google_reviews(client: TestClient, api_module, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, str]:
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    reg = _register(client)
    client_id = reg["client"]["client_id"]
    auth = {"Authorization": f"Bearer {reg['token']}"}
    api_module.runtime.store.save_google_creds(
        client_id=client_id,
        refresh_token="reftok",
        access_token="tok",
        token_expiry=None,
        google_email="biz@example.com",
        location_id="loc-1",
    )
    monkeypatch.setattr(api_module._n8n, "duplicate_template", lambda **kwargs: "wf-reviews-1")
    resp = client.post("/client/automations/google_reviews/activate", headers=auth)
    assert resp.status_code == 200
    return auth, client_id


def test_reply_mode_settings_get_put(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.interface.api as api_module

    auth, _ = _activate_google_reviews(client, api_module, monkeypatch)

    got = client.get("/client/automations/google_reviews/settings", headers=auth)
    assert got.status_code == 200
    assert got.json()["reply_mode"] == "approval"

    bad = client.put(
        "/client/automations/google_reviews/settings",
        headers=auth,
        json={"reply_mode": "bogus"},
    )
    assert bad.status_code == 400

    put = client.put(
        "/client/automations/google_reviews/settings",
        headers=auth,
        json={"reply_mode": "auto"},
    )
    assert put.status_code == 200
    assert put.json()["reply_mode"] == "auto"

    got2 = client.get("/client/automations/google_reviews/settings", headers=auth)
    assert got2.json()["reply_mode"] == "auto"


def test_push_draft_approval_mode_stays_pending(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate_google_reviews(client, api_module, monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append({"cid": cid, "bid": bid, "payload": payload}),
    )

    resp = client.post(
        "/internal/automations/google_reviews/drafts",
        headers={"X-Webhook-Secret": "test-webhook-secret"},
        json={
            "client_id": client_id,
            "review_id": "rev-1",
            "reviewer_name": "Ana",
            "rating": "FIVE",
            "source_text": "Muy bueno",
            "suggested_reply": "¡Gracias Ana!",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["draft"]["status"] == "pending"
    assert calls == []

    listed = client.get("/client/automations/google_reviews/drafts?status=pending", headers=auth)
    assert listed.status_code == 200
    assert len(listed.json()["drafts"]) == 1


def test_push_draft_auto_mode_publishes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate_google_reviews(client, api_module, monkeypatch)
    business_id = api_module.runtime.store.ensure_default_business(client_id)["business_id"]
    api_module.runtime.store.update_automation_settings(
        client_id, business_id, "google_reviews", "auto"
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append({"cid": cid, "bid": bid, "payload": payload}),
    )

    resp = client.post(
        "/internal/automations/google_reviews/drafts",
        headers={"X-Webhook-Secret": "test-webhook-secret"},
        json={
            "client_id": client_id,
            "review_id": "rev-2",
            "reviewer_name": "Luis",
            "rating": "FOUR",
            "source_text": "Bien",
            "suggested_reply": "Gracias Luis",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft"]["status"] == "auto_sent"
    assert len(calls) == 1
    assert calls[0]["payload"]["final_reply"] == "Gracias Luis"
    assert calls[0]["payload"]["review_id"] == "rev-2"


def test_approve_draft_triggers_n8n(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate_google_reviews(client, api_module, monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append(payload),
    )

    draft = api_module.runtime.store.create_draft(
        client_id=client_id,
        automation_type="google_reviews",
        suggested_reply="Borrador original",
        review_id="rev-3",
        reviewer_name="Marta",
        rating="FIVE",
        source_text="Genial",
    )

    resp = client.post(
        f"/client/drafts/{draft['draft_id']}/approve",
        headers=auth,
        json={"final_reply": "Borrador editado"},
    )
    assert resp.status_code == 200
    assert resp.json()["draft"]["status"] == "edited"
    assert len(calls) == 1
    assert calls[0]["final_reply"] == "Borrador editado"
    assert calls[0]["draft_id"] == draft["draft_id"]


def test_reject_draft_does_not_call_n8n(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate_google_reviews(client, api_module, monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append(payload),
    )

    draft = api_module.runtime.store.create_draft(
        client_id=client_id,
        automation_type="google_reviews",
        suggested_reply="No enviar",
        review_id="rev-4",
    )

    resp = client.post(f"/client/drafts/{draft['draft_id']}/reject", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["draft"]["status"] == "rejected"
    assert calls == []


def test_n8n_inject_publish_reply_webhook() -> None:
    from apps.integrations.n8n_client import N8nClient

    n8n = N8nClient()
    wf = {
        "nodes": [
            {"name": "Generate AI Draft", "type": "n8n-nodes-base.openAi", "parameters": {}},
            {"name": "Post Reply to Google", "type": "n8n-nodes-base.httpRequest", "parameters": {}},
        ],
        "connections": {},
    }
    n8n._inject_publish_reply_webhook(wf, "CLI-ABC", "BIZ-1")
    names = {n["name"] for n in wf["nodes"]}
    assert "Publish Reply Webhook" in names
    wh = next(n for n in wf["nodes"] if n["name"] == "Publish Reply Webhook")
    assert wh["parameters"]["path"] == "publish-reply-cli-abc-biz-1"
    assert "Publish Reply Webhook" in wf["connections"]
    assert wf["connections"]["Publish Reply Webhook"]["main"][0][0]["node"] == "Post Reply to Google"


def test_list_google_reviews_requires_google(client: TestClient) -> None:
    reg = _register(client, "nogmb@example.com")
    auth = {"Authorization": f"Bearer {reg['token']}"}
    resp = client.get("/client/automations/google_reviews/reviews", headers=auth)
    assert resp.status_code == 400
    assert "Google" in resp.json()["detail"]


def test_list_google_reviews_merges_drafts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate_google_reviews(client, api_module, monkeypatch)
    business_id = api_module.runtime.store.ensure_default_business(client_id)["business_id"]
    api_module.runtime.store.create_draft(
        client_id=client_id,
        automation_type="google_reviews",
        suggested_reply="Gracias!",
        business_id=business_id,
        review_id="revABC",
        reviewer_name="Ana",
        rating="FIVE",
        source_text="Genial",
    )

    def fake_fetch(creds, page_size=50, page_token=None, location_override=None):
        payload = {
            "location_id": "accounts/1/locations/2",
            "average_rating": 5.0,
            "total_review_count": 1,
            "next_page_token": None,
            "reviews": [
                {
                    "review_id": "revABC",
                    "name": "accounts/1/locations/2/reviews/revABC",
                    "reviewer_name": "Ana",
                    "rating": 5,
                    "star_rating": "FIVE",
                    "comment": "Genial",
                    "create_time": "2026-01-01T00:00:00Z",
                    "update_time": "2026-01-01T00:00:00Z",
                    "reply_comment": None,
                    "reply_update_time": None,
                    "has_reply": False,
                }
            ],
        }
        return payload, "accounts/1/locations/2", None

    monkeypatch.setattr(api_module._google_business, "fetch_reviews_for_creds", fake_fetch)
    resp = client.get("/client/automations/google_reviews/reviews", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_review_count"] == 1
    assert body["reviews"][0]["draft"]["status"] == "pending"
    assert body["location_id"] == "accounts/1/locations/2"


def test_normalize_review() -> None:
    from apps.integrations.google_business import normalize_review

    raw = {
        "name": "accounts/1/locations/2/reviews/xyz",
        "reviewer": {"displayName": "Pepe"},
        "starRating": "FOUR",
        "comment": "Bien",
        "createTime": "2026-01-02T00:00:00Z",
        "reviewReply": {"comment": "Gracias", "updateTime": "2026-01-03T00:00:00Z"},
    }
    n = normalize_review(raw)
    assert n["review_id"] == "xyz"
    assert n["rating"] == 4
    assert n["has_reply"] is True
    assert n["reply_comment"] == "Gracias"


def test_friendly_google_error_service_disabled() -> None:
    from apps.integrations.google_business import friendly_google_error

    raw = json.dumps(
        {
            "error": {
                "code": 403,
                "message": "My Business Account Management API has not been used in project 1 before or it is disabled.",
                "status": "PERMISSION_DENIED",
                "details": [{"reason": "SERVICE_DISABLED"}],
            }
        }
    )
    msg = friendly_google_error(raw)
    assert "Google Cloud" in msg or "plataforma" in msg
    assert "SERVICE_DISABLED" not in msg
    assert "{" not in msg


def test_accounts_status_and_google_disconnect(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate_google_reviews(client, api_module, monkeypatch)

    status = client.get("/client/accounts/status", headers=auth)
    assert status.status_code == 200
    accounts = {a["provider"]: a for a in status.json()["accounts"]}
    assert accounts["google"]["connected"] is True
    assert accounts["instagram"]["connected"] is False
    assert accounts["instagram"]["connectable"] is False
    assert accounts["tiktok"]["connectable"] is False
    assert accounts["email"]["connectable"] is False

    disc = client.delete("/client/google/disconnect", headers=auth)
    assert disc.status_code == 200
    assert disc.json()["connected"] is False
    assert api_module.runtime.store.get_google_creds(client_id) is None

    status2 = client.get("/client/accounts/status", headers=auth)
    assert status2.json()["accounts"][0]["connected"] is False


def _register_with_two_businesses(
    client: TestClient, api_module, monkeypatch: pytest.MonkeyPatch, email: str = "multi@example.com"
) -> tuple[dict, str, list[dict]]:
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    reg = _register(client, email)
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
    monkeypatch.setattr(
        api_module._google_business,
        "list_businesses_for_creds",
        lambda creds: (
            [
                {
                    "google_account_id": "accounts/1",
                    "location_id": "accounts/1/locations/1",
                    "business_name": "Sucursal Centro",
                },
                {
                    "google_account_id": "accounts/1",
                    "location_id": "accounts/1/locations/2",
                    "business_name": "Sucursal Norte",
                },
            ],
            None,
        ),
    )
    resp = client.get("/client/businesses", headers=auth)
    assert resp.status_code == 200
    businesses = resp.json()["businesses"]
    assert len(businesses) == 2
    return auth, client_id, businesses


def test_list_businesses_discovers_multiple_locations(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id, businesses = _register_with_two_businesses(client, api_module, monkeypatch)
    names = {b["business_name"] for b in businesses}
    assert names == {"Sucursal Centro", "Sucursal Norte"}


def test_activate_automation_per_business_creates_separate_workflows(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id, businesses = _register_with_two_businesses(client, api_module, monkeypatch)
    biz1, biz2 = businesses[0]["business_id"], businesses[1]["business_id"]

    created_workflows: list[dict] = []

    def fake_duplicate(**kwargs):
        wf_id = f"wf-{kwargs.get('business_id')}"
        created_workflows.append(kwargs)
        return wf_id

    monkeypatch.setattr(api_module._n8n, "duplicate_template", fake_duplicate)

    r1 = client.post(
        f"/client/automations/google_reviews/activate?business_id={biz1}", headers=auth
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/client/automations/google_reviews/activate?business_id={biz2}", headers=auth
    )
    assert r2.status_code == 200

    assert r1.json()["workflow_id"] != r2.json()["workflow_id"]
    assert len(created_workflows) == 2
    assert {kw["business_id"] for kw in created_workflows} == {biz1, biz2}

    autos = client.get("/client/automations", headers=auth).json()["active"]
    active_biz_ids = {a["business_id"] for a in autos if a["status"] == "active"}
    assert active_biz_ids == {biz1, biz2}


def test_settings_and_drafts_are_scoped_per_business(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id, businesses = _register_with_two_businesses(client, api_module, monkeypatch)
    biz1, biz2 = businesses[0]["business_id"], businesses[1]["business_id"]
    monkeypatch.setattr(api_module._n8n, "duplicate_template", lambda **kwargs: f"wf-{kwargs.get('business_id')}")

    client.post(f"/client/automations/google_reviews/activate?business_id={biz1}", headers=auth)
    client.post(f"/client/automations/google_reviews/activate?business_id={biz2}", headers=auth)

    # Set biz1 to auto mode; biz2 should remain in approval mode.
    put = client.put(
        f"/client/automations/google_reviews/settings?business_id={biz1}",
        headers=auth,
        json={"reply_mode": "auto"},
    )
    assert put.status_code == 200
    assert put.json()["reply_mode"] == "auto"

    got2 = client.get(
        f"/client/automations/google_reviews/settings?business_id={biz2}", headers=auth
    )
    assert got2.json()["reply_mode"] == "approval"

    # Push a draft for biz1 -> should auto-publish; biz2 draft should stay pending.
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append({"cid": cid, "bid": bid, "payload": payload}),
    )

    resp1 = client.post(
        "/internal/automations/google_reviews/drafts",
        headers={"X-Webhook-Secret": "test-webhook-secret"},
        json={
            "client_id": client_id,
            "business_id": biz1,
            "review_id": "rev-biz1",
            "suggested_reply": "Gracias!",
        },
    )
    assert resp1.json()["draft"]["status"] == "auto_sent"
    assert len(calls) == 1
    assert calls[0]["bid"] == biz1

    resp2 = client.post(
        "/internal/automations/google_reviews/drafts",
        headers={"X-Webhook-Secret": "test-webhook-secret"},
        json={
            "client_id": client_id,
            "business_id": biz2,
            "review_id": "rev-biz2",
            "suggested_reply": "Muchas gracias!",
        },
    )
    assert resp2.json()["draft"]["status"] == "pending"
    assert len(calls) == 1  # no additional publish call for biz2

    # Drafts list scoped per business.
    drafts_biz1 = client.get(
        f"/client/automations/google_reviews/drafts?business_id={biz1}", headers=auth
    ).json()["drafts"]
    drafts_biz2 = client.get(
        f"/client/automations/google_reviews/drafts?business_id={biz2}", headers=auth
    ).json()["drafts"]
    assert {d["review_id"] for d in drafts_biz1} == {"rev-biz1"}
    assert {d["review_id"] for d in drafts_biz2} == {"rev-biz2"}


def test_deactivate_automation_only_affects_selected_business(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id, businesses = _register_with_two_businesses(client, api_module, monkeypatch)
    biz1, biz2 = businesses[0]["business_id"], businesses[1]["business_id"]
    monkeypatch.setattr(api_module._n8n, "duplicate_template", lambda **kwargs: f"wf-{kwargs.get('business_id')}")
    monkeypatch.setattr(api_module._n8n, "delete_workflow", lambda wf_id: None)

    client.post(f"/client/automations/google_reviews/activate?business_id={biz1}", headers=auth)
    client.post(f"/client/automations/google_reviews/activate?business_id={biz2}", headers=auth)

    resp = client.delete(f"/client/automations/google_reviews?business_id={biz1}", headers=auth)
    assert resp.status_code == 200

    autos = client.get("/client/automations", headers=auth).json()["active"]
    statuses = {a["business_id"]: a["status"] for a in autos}
    assert statuses[biz1] == "inactive"
    assert statuses[biz2] == "active"
