"""Tests for Stripe checkout + subscription gating."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")
    # Empty (not deleted): load_dotenv() must not reintroduce keys from .env.
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("MANUALZERO_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setenv("MANUALZERO_STRIPE_WEBHOOK_SECRET", "")


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
    store.activate_automation(client_id, store.ensure_default_business(client_id)["business_id"], "google_reviews", "wf-1")

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
    business_id = store.ensure_default_business(client_id)["business_id"]
    auto = store.get_automation(client_id, business_id, "google_reviews")
    assert auto["status"] == "inactive"


def test_stripe_object_helpers_normalize_metadata() -> None:
    from apps.integrations.stripe_payments import parse_session_metadata, stripe_id, stripe_object_to_dict

    class FakeStripe:
        def to_dict(self):
            return {
                "id": "cs_1",
                "client_reference_id": "CLI-ABC",
                "metadata": {
                    "client_id": "CLI-ABC",
                    "automation_types": "google_reviews",
                    "billing_interval": "monthly",
                },
                "customer": "cus_1",
            }

        def __getattr__(self, item):
            raise AttributeError(item)

    client_id, types, interval = parse_session_metadata(FakeStripe())
    assert client_id == "CLI-ABC"
    assert types == ["google_reviews"]
    assert interval == "monthly"
    assert stripe_id("cus_1") == "cus_1"
    assert stripe_id({"id": "cus_2"}) == "cus_2"
    assert stripe_object_to_dict(FakeStripe())["id"] == "cs_1"


def test_unsubscribe_cancels_stripe_subscription(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    import apps.integrations.stripe_payments as sp
    import apps.interface.api as api_module

    calls: list[str] = []

    def fake_cancel(sub_id: str, **kwargs):
        calls.append(sub_id)
        return {"id": sub_id, "status": "canceled"}

    monkeypatch.setattr(sp, "cancel_subscription", fake_cancel)

    reg = _register(client, "unsub@example.com")
    client_id = reg["client"]["client_id"]
    auth = {"Authorization": f"Bearer {reg['token']}"}
    store = api_module.runtime.store
    store.upsert_subscription(
        client_id=client_id,
        automation_type="google_reviews",
        status="trialing",
        stripe_subscription_id="sub_to_cancel",
    )
    store.activate_automation(client_id, store.ensure_default_business(client_id)["business_id"], "google_reviews", "wf-1")

    resp = client.delete("/client/automations/google_reviews", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "inactive"
    assert body["stripe_cancelled"] is True
    assert calls == ["sub_to_cancel"]
    assert not store.has_active_subscription(client_id, "google_reviews")


def test_checkout_persists_stripe_customer_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    import apps.integrations.stripe_payments as sp
    import apps.interface.api as api_module

    monkeypatch.setattr(
        sp,
        "create_checkout_session",
        lambda **kwargs: {
            "session_id": "cs_new",
            "checkout_url": "https://checkout.stripe.com/c/pay/cs_new",
            "automation_types": kwargs["automation_types"],
            "billing_interval": "monthly",
            "stripe_customer_id": "cus_persistent",
        },
    )

    reg = _register(client, "persist@example.com")
    client_id = reg["client"]["client_id"]
    auth = {"Authorization": f"Bearer {reg['token']}"}
    resp = client.post(
        "/client/checkout/session",
        headers=auth,
        json={"automation_types": ["google_reviews"]},
    )
    assert resp.status_code == 200
    assert api_module.runtime.store.get_client_by_id(client_id)["stripe_customer_id"] == "cus_persistent"


def test_ensure_stripe_customer_reuses_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.integrations.stripe_payments as sp

    class FakeCustomerAPI:
        @staticmethod
        def retrieve(cid):
            return {"id": cid, "deleted": False}

        @staticmethod
        def search(**kwargs):
            return {"data": []}

        @staticmethod
        def create(**kwargs):
            return {"id": "cus_brand_new"}

    class FakeStripe:
        Customer = FakeCustomerAPI

    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setitem(__import__("sys").modules, "stripe", FakeStripe())

    # Force import path used inside ensure_stripe_customer
    import stripe as stripe_mod  # noqa: F401 — may be real; patch via monkeypatch on sp flow

    monkeypatch.setattr(
        sp,
        "ensure_stripe_customer",
        sp.ensure_stripe_customer,
    )

    # Call with existing id — retrieve succeeds → reuse
    # We patch stripe import inside the function by injecting module
    import types
    fake_module = types.ModuleType("stripe")
    fake_module.Customer = FakeCustomerAPI
    fake_module.api_key = None
    monkeypatch.setitem(__import__("sys").modules, "stripe", fake_module)

    cid = sp.ensure_stripe_customer(
        client_id="CLI-1",
        client_email="a@b.com",
        stripe_customer_id="cus_existing",
        settings=sp.StripeSettings(
            secret_key="sk_test",
            webhook_secret="",
            publishable_key="",
            public_url="http://localhost",
            trial_days=14,
            price_ids={},
        ),
    )
    assert cid == "cus_existing"

    # Missing customer → create
    class MissingCustomerAPI:
        @staticmethod
        def retrieve(cid):
            raise RuntimeError("No such customer: 'cus_gone'")

        @staticmethod
        def search(**kwargs):
            return {"data": []}

        @staticmethod
        def create(**kwargs):
            assert kwargs["metadata"]["zeromanual_client_id"] == "CLI-2"
            return {"id": "cus_created"}

    fake_module.Customer = MissingCustomerAPI
    cid2 = sp.ensure_stripe_customer(
        client_id="CLI-2",
        client_email="c@d.com",
        stripe_customer_id="cus_gone",
        settings=sp.StripeSettings(
            secret_key="sk_test",
            webhook_secret="",
            publishable_key="",
            public_url="http://localhost",
            trial_days=14,
            price_ids={},
        ),
    )
    assert cid2 == "cus_created"


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

