from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.integrations.google_business import (
    GBP_LOCATION_REQUIRED_MESSAGE,
    is_valid_gbp_location_id,
    require_gbp_location_id,
)
from apps.integrations.n8n_client import N8nClient


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("MANUALZERO_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("ZEROMANUAL_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("MANUALZERO_WEBHOOK_SECRET", "test-webhook-secret")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "gbp-location.db"))
    import importlib
    import apps.interface.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


def _register(client: TestClient, email: str) -> dict:
    resp = client.post(
        "/client/register",
        json={"name": "Reviews Biz", "email": email, "password": "secret123"},
    )
    assert resp.status_code == 200
    return resp.json()


def test_is_valid_gbp_location_id_rejects_placeholders_and_bare_ids() -> None:
    assert is_valid_gbp_location_id("accounts/123/locations/456") is True
    assert is_valid_gbp_location_id("default-CLI-ABC") is False
    assert is_valid_gbp_location_id("loc-1") is False
    assert is_valid_gbp_location_id("456") is False
    assert is_valid_gbp_location_id("accounts/123") is False
    assert is_valid_gbp_location_id(None) is False
    with pytest.raises(ValueError, match="ficha válida"):
        require_gbp_location_id("default-CLI-ABC")
    assert require_gbp_location_id("accounts/1/locations/2") == "accounts/1/locations/2"


def test_duplicate_template_rejects_invalid_gbp_location_before_n8n() -> None:
    n8n = N8nClient()
    with pytest.raises(ValueError, match="ficha válida") as exc_info:
        n8n.duplicate_template(
            template_id="tpl-1",
            client_id="CLI-1",
            client_name="Biz",
            refresh_token="rt",
            location_id="default-CLI-1",
            automation_type="google_reviews",
            business_id="BIZ-1",
        )
    assert str(exc_info.value) == GBP_LOCATION_REQUIRED_MESSAGE

    with pytest.raises(ValueError, match="ficha válida"):
        n8n.duplicate_template(
            template_id="tpl-1",
            client_id="CLI-1",
            client_name="Biz",
            refresh_token="rt",
            location_id="loc-99",
            automation_type="google_reviews",
            business_id="BIZ-1",
        )


def test_activate_rejects_placeholder_location_and_does_not_call_n8n(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    import apps.interface.api as api_module

    reg = _register(client, "placeholder-activate@example.com")
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
    placeholder = api_module.runtime.store.ensure_default_business(client_id)
    assert placeholder["location_id"].startswith("default-")

    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "duplicate_template",
        lambda **kwargs: calls.append(kwargs) or "wf-should-not-exist",
    )

    resp = client.post(
        f"/client/automations/google_reviews/activate?business_id={placeholder['business_id']}",
        headers=auth,
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "ficha válida" in detail
    assert "provisional" in detail
    assert calls == []


def test_activate_rejects_bare_location_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    import apps.interface.api as api_module

    reg = _register(client, "bare-activate@example.com")
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
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "duplicate_template",
        lambda **kwargs: calls.append(kwargs) or "wf-should-not-exist",
    )

    resp = client.post("/client/automations/google_reviews/activate", headers=auth)
    assert resp.status_code == 400
    assert "ficha válida" in resp.json()["detail"]
    assert calls == []


def test_activate_passes_valid_gbp_location_to_n8n(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    import apps.interface.api as api_module

    reg = _register(client, "valid-activate@example.com")
    client_id = reg["client"]["client_id"]
    auth = {"Authorization": f"Bearer {reg['token']}"}
    api_module.runtime.store.save_google_creds(
        client_id=client_id,
        refresh_token="reftok",
        access_token="tok",
        token_expiry=None,
        google_email="biz@example.com",
        location_id="accounts/9/locations/7",
    )
    captured: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "duplicate_template",
        lambda **kwargs: captured.append(kwargs) or "wf-ok",
    )

    resp = client.post("/client/automations/google_reviews/activate", headers=auth)
    assert resp.status_code == 200
    assert captured[0]["location_id"] == "accounts/9/locations/7"
    assert is_valid_gbp_location_id(captured[0]["location_id"])


def test_resolve_review_location_none_when_placeholder_and_multiple_synced(
    client: TestClient,
) -> None:
    import apps.interface.api as api_module

    reg = _register(client, "resolve-multi@example.com")
    client_id = reg["client"]["client_id"]
    api_module.runtime.store.save_google_creds(
        client_id=client_id,
        refresh_token="reftok",
        access_token="tok",
        token_expiry=None,
        google_email="biz@example.com",
        location_id=None,
    )
    placeholder = api_module.runtime.store.ensure_default_business(client_id)
    synced = [
        {
            "business_id": "BIZ-A",
            "location_id": "accounts/1/locations/1",
            "business_name": "Centro",
        },
        {
            "business_id": "BIZ-B",
            "location_id": "accounts/1/locations/2",
            "business_name": "Norte",
        },
    ]
    resolved = api_module._resolve_review_location(client_id, placeholder, synced)
    assert resolved is None


def test_list_google_reviews_placeholder_with_multiple_locations_errors(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Panel must not go silently empty when a placeholder coexists with several GBP locations."""
    import apps.interface.api as api_module

    reg = _register(client, "multi-placeholder@example.com")
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
    placeholder = api_module.runtime.store.ensure_default_business(client_id)
    assert placeholder["location_id"].startswith("default-")

    def fake_sync(client_id_arg: str):
        api_module.runtime.store.sync_businesses(
            client_id_arg,
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
        )
        return api_module.runtime.store.list_businesses(client_id_arg)

    fetch_calls: list[dict] = []

    def fake_fetch(creds, page_size=50, page_token=None, location_override=None):
        fetch_calls.append({"location_override": location_override})
        return (
            {
                "location_id": location_override,
                "average_rating": None,
                "total_review_count": 0,
                "next_page_token": None,
                "reviews": [],
            },
            location_override,
            None,
        )

    monkeypatch.setattr(api_module, "_sync_businesses_from_google", fake_sync)
    monkeypatch.setattr(api_module._google_business, "fetch_reviews_for_creds", fake_fetch)

    resp = client.get(
        f"/client/automations/google_reviews/reviews?business_id={placeholder['business_id']}",
        headers=auth,
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "ficha" in detail.lower()
    assert "negocio" in detail.lower()
    assert fetch_calls == []

    leftover = api_module.runtime.store.get_business(placeholder["business_id"])
    assert leftover["location_id"].startswith("default-")


def test_list_google_reviews_explicit_location_still_works_with_siblings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    reg = _register(client, "explicit-multi@example.com")
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
    api_module.runtime.store.ensure_default_business(client_id)
    synced = api_module.runtime.store.sync_businesses(
        client_id,
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
    )
    centro = next(b for b in synced if b["location_id"] == "accounts/1/locations/1")

    def fake_sync(client_id_arg: str):
        return api_module.runtime.store.list_businesses(client_id_arg)

    def fake_fetch(creds, page_size=50, page_token=None, location_override=None):
        assert location_override == "accounts/1/locations/1"
        return (
            {
                "location_id": "accounts/1/locations/1",
                "average_rating": 5.0,
                "total_review_count": 1,
                "next_page_token": None,
                "reviews": [
                    {
                        "review_id": "rev-centro",
                        "name": "accounts/1/locations/1/reviews/rev-centro",
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
            },
            "accounts/1/locations/1",
            None,
        )

    monkeypatch.setattr(api_module, "_sync_businesses_from_google", fake_sync)
    monkeypatch.setattr(api_module._google_business, "fetch_reviews_for_creds", fake_fetch)

    resp = client.get(
        f"/client/automations/google_reviews/reviews?business_id={centro['business_id']}",
        headers=auth,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_review_count"] == 1
    assert body["reviews"][0]["review_id"] == "rev-centro"


def test_google_callback_pending_without_valid_location_does_not_activate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    import apps.interface.api as api_module

    reg = _register(client, "pending-noloc@example.com")
    client_id = reg["client"]["client_id"]
    auth = {"Authorization": f"Bearer {reg['token']}"}
    client.post(
        "/client/pending-automation",
        json={"automation_type": "google_reviews"},
        headers=auth,
    )
    monkeypatch.setattr(
        api_module._google_oauth,
        "exchange_code",
        lambda code, state: (
            client_id,
            {"access_token": "tok", "refresh_token": "reftok", "expires_in": 3600},
        ),
    )
    monkeypatch.setattr(api_module._google_oauth, "get_user_email", lambda token: "biz@example.com")
    monkeypatch.setattr(
        api_module._google_business,
        "list_businesses_for_creds",
        lambda creds: ([], None),
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "duplicate_template",
        lambda **kwargs: calls.append(kwargs) or "wf-should-not-exist",
    )

    resp = client.get("/client/google/callback?code=abc&state=xyz", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "connected=1" in resp.headers.get("location", "")
    assert "activated=" not in resp.headers.get("location", "")
    assert calls == []


def test_google_callback_preserves_existing_refresh_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    reg = _register(client, "preserve-rt@example.com")
    client_id = reg["client"]["client_id"]
    api_module.runtime.store.save_google_creds(
        client_id=client_id,
        refresh_token="old-refresh-token",
        access_token="old-access",
        token_expiry=None,
        google_email="biz@example.com",
        location_id="accounts/1/locations/1",
    )
    monkeypatch.setattr(
        api_module._google_oauth,
        "exchange_code",
        lambda code, state: (
            client_id,
            {"access_token": "new-access", "expires_in": 3600},
        ),
    )
    monkeypatch.setattr(api_module._google_oauth, "get_user_email", lambda token: "biz@example.com")
    monkeypatch.setattr(
        api_module._google_business,
        "list_businesses_for_creds",
        lambda creds: (
            [
                {
                    "google_account_id": "accounts/1",
                    "location_id": "accounts/1/locations/1",
                    "business_name": "Mi negocio",
                }
            ],
            None,
        ),
    )

    resp = client.get("/client/google/callback?code=abc&state=xyz", follow_redirects=False)
    assert resp.status_code in (302, 307)
    creds = api_module.runtime.store.get_google_creds(client_id)
    assert creds is not None
    assert creds["refresh_token"] == "old-refresh-token"
    assert creds["access_token"] == "new-access"
