"""Tests for Stripe checkout + subscription gating."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")
    monkeypatch.delenv("ZEROMANUAL_STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("MANUALZERO_STRIPE_SECRET_KEY", raising=False)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "test.db"))
    import importlib
    import apps.interface.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


def _register(client: TestClient, email: str = "pay@example.com") -> dict:
    resp = client.post(
        "/client/register",
        json={"name": "Pay Biz", "email": email, "password": "secret123"},
    )
    assert resp.status_code == 200
    return resp.json()


def test_checkout_session_free_mode_grants_subscription(client: TestClient) -> None:
    reg = _register(client)
    auth = {"Authorization": f"Bearer {reg['token']}"}
    resp = client.post(
        "/client/checkout/session",
        headers=auth,
        json={"automation_types": ["google_reviews"], "billing_interval": "monthly"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "free"
    assert body["checkout_url"] is None

    subs = client.get("/client/subscriptions", headers=auth)
    assert subs.status_code == 200
    rows = subs.json()["subscriptions"]
    assert len(rows) == 1
    assert rows[0]["automation_type"] == "google_reviews"
    assert rows[0]["status"] == "active"
    assert rows[0]["provider"] == "dev"


def test_checkout_rejects_unknown_automation(client: TestClient) -> None:
    reg = _register(client, "bad@example.com")
    auth = {"Authorization": f"Bearer {reg['token']}"}
    resp = client.post(
        "/client/checkout/session",
        headers=auth,
        json={"automation_types": ["not_a_real_type"]},
    )
    assert resp.status_code == 400


def test_checkout_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/client/checkout/session",
        json={"automation_types": ["google_reviews"]},
    )
    assert resp.status_code == 401


def test_activate_gated_when_stripe_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    import apps.integrations.stripe_payments as sp

    # Re-read settings pick up env; stripe_enabled uses zm_env live.
    assert sp.stripe_enabled()

    reg = _register(client, "gated@example.com")
    auth = {"Authorization": f"Bearer {reg['token']}"}
    resp = client.post("/client/automations/google_reviews/activate", headers=auth)
    assert resp.status_code == 400
    assert "Suscripción" in resp.json()["detail"]


def test_stripe_checkout_session_redirect(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("ZEROMANUAL_PUBLIC_URL", "http://localhost:8090")

    import apps.integrations.stripe_payments as sp

    monkeypatch.setattr(
        sp,
        "create_checkout_session",
        lambda **kwargs: {
            "session_id": "cs_test_1",
            "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_1",
            "automation_types": kwargs["automation_types"],
            "billing_interval": "monthly",
        },
    )

    reg = _register(client, "stripe@example.com")
    auth = {"Authorization": f"Bearer {reg['token']}"}
    resp = client.post(
        "/client/checkout/session",
        headers=auth,
        json={"automation_types": ["google_reviews"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "stripe"
    assert body["checkout_url"].startswith("https://checkout.stripe.com/")


def test_stripe_webhook_grants_subscription(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRET", "whsec_test")

    import apps.integrations.stripe_payments as sp
    import apps.interface.api as api_module

    reg = _register(client, "hook@example.com")
    client_id = reg["client"]["client_id"]

    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_hook",
                "customer": "cus_123",
                "subscription": "sub_123",
                "payment_status": "paid",
                "metadata": {
                    "client_id": client_id,
                    "automation_types": "google_reviews",
                    "billing_interval": "monthly",
                },
                "client_reference_id": client_id,
            }
        },
    }
    monkeypatch.setattr(sp, "construct_webhook_event", lambda payload, sig: fake_event)

    resp = client.post(
        "/internal/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert resp.status_code == 200
    assert resp.json()["received"] is True

    store = api_module.runtime.store
    assert store.has_active_subscription(client_id, "google_reviews")
    client_row = store.get_client_by_id(client_id)
    assert client_row["stripe_customer_id"] == "cus_123"


def test_subscription_cancel_deactivates_automation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRET", "whsec_test")

    import apps.integrations.stripe_payments as sp
    import apps.interface.api as api_module

    reg = _register(client, "cancel@example.com")
    client_id = reg["client"]["client_id"]
    store = api_module.runtime.store
    store.upsert_subscription(
        client_id=client_id,
        automation_type="google_reviews",
        status="active",
        stripe_subscription_id="sub_cancel",
    )
    store.activate_automation(client_id, "google_reviews", "wf-1")

    fake_event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_cancel", "status": "canceled"}},
    }
    monkeypatch.setattr(sp, "construct_webhook_event", lambda payload, sig: fake_event)

    resp = client.post(
        "/internal/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert resp.status_code == 200
    assert not store.has_active_subscription(client_id, "google_reviews")
    auto = store.get_automation(client_id, "google_reviews")
    assert auto["status"] == "inactive"


def test_catalog_validate_and_line_items() -> None:
    from apps.integrations.stripe_payments import (
        StripeSettings,
        validate_automation_types,
        _line_items,
    )

    assert validate_automation_types(["google_reviews", "google_reviews"]) == ["google_reviews"]
    with pytest.raises(ValueError):
        validate_automation_types([])

    cfg = StripeSettings(
        secret_key="sk",
        webhook_secret="",
        publishable_key="",
        public_url="http://localhost",
        trial_days=14,
        price_ids={},
    )
    items = _line_items(cfg, ["google_reviews"], "yearly")
    assert items[0]["price_data"]["unit_amount"] == 29000
    assert items[0]["price_data"]["recurring"]["interval"] == "year"
