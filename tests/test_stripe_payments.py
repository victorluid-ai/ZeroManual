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


# 2026-01-01 00:00:00 UTC → 01/01/2026 en Europe/Madrid.
PERIOD_END = 1_767_225_600
# Periodo que devuelve modify(cancel_at_period_end=False). Distinto a PERIOD_END.
OPEN_PERIOD_END = PERIOD_END + 2_678_400


def _basil_subscription(
    sub_id: str,
    *,
    status: str = "active",
    scheduled: bool = True,
    cancel_at: int | None = PERIOD_END,
    trial_end: int | None = None,
    item_end: int | None = PERIOD_END,
) -> dict:
    """Webhook 2025-05-28.basil: current_period_end en la raíz es null."""
    return {
        "id": sub_id,
        "status": status,
        "cancel_at_period_end": scheduled,
        "cancel_at": cancel_at if scheduled else None,
        "trial_end": trial_end,
        "current_period_end": None,
        "items": {
            "object": "list",
            "data": [{"id": "si_1", "current_period_end": item_end}],
        },
    }


def _endive_subscription(
    sub_id: str,
    *,
    status: str = "active",
    scheduled: bool = True,
    cancel_at: int | None = PERIOD_END,
    trial_end: int | None = None,
    item_end: int | None = PERIOD_END,
) -> dict:
    """Respuesta de modify en 2026-09-30.endive.

    Subscription ya no tiene current_period_end. La fecha sigue en cancel_at
    y en items.data[0].current_period_end.
    """
    payload = {
        "id": sub_id,
        "status": status,
        "cancel_at_period_end": scheduled,
        "cancel_at": cancel_at if scheduled else None,
        "items": {
            "object": "list",
            "data": [{"id": "si_1", "current_period_end": item_end}],
        },
    }
    if trial_end is not None:
        payload["trial_end"] = trial_end
    return payload


def _install_fake_stripe(
    monkeypatch: pytest.MonkeyPatch, *, form: str = "endive", **shape: object
):
    import sys
    import types

    calls: list[tuple] = []
    builder = _endive_subscription if form == "endive" else _basil_subscription

    class Subscription:
        @staticmethod
        def modify(sub_id, **kwargs):
            calls.append(("modify", sub_id, dict(kwargs)))
            scheduled = bool(kwargs.get("cancel_at_period_end"))
            payload_shape = dict(shape)
            open_end = payload_shape.pop("open_item_end", None)
            if not scheduled and open_end is not None:
                payload_shape["item_end"] = open_end
                payload_shape["cancel_at"] = None
            return builder(sub_id, scheduled=scheduled, **payload_shape)

        @staticmethod
        def cancel(sub_id, **kwargs):
            calls.append(("cancel", sub_id, dict(kwargs)))
            raise AssertionError("Subscription.cancel no debe usarse")

    module = types.ModuleType("stripe")
    module.Subscription = Subscription
    module.api_key = None
    module.error = types.SimpleNamespace(SignatureVerificationError=Exception)
    monkeypatch.setitem(sys.modules, "stripe", module)
    return calls


def test_access_until_reads_basil_webhook_and_endive_modify() -> None:
    from apps.integrations.stripe_payments import (
        format_access_until,
        subscription_access_until_unix,
    )

    basil = _basil_subscription(
        "sub_basil", cancel_at=PERIOD_END, item_end=PERIOD_END + 86_400
    )
    assert basil["current_period_end"] is None
    assert subscription_access_until_unix(basil) == PERIOD_END
    assert format_access_until(PERIOD_END) == "01/01/2026"

    basil_item = _basil_subscription("sub_basil_item", cancel_at=None, item_end=PERIOD_END)
    basil_item["cancel_at"] = None
    assert subscription_access_until_unix(basil_item) == PERIOD_END

    endive = _endive_subscription(
        "sub_endive", cancel_at=PERIOD_END, item_end=PERIOD_END + 86_400
    )
    assert "current_period_end" not in endive
    assert subscription_access_until_unix(endive) == PERIOD_END

    endive_item = _endive_subscription(
        "sub_endive_item", scheduled=False, cancel_at=None, item_end=OPEN_PERIOD_END
    )
    assert endive_item["cancel_at"] is None
    assert subscription_access_until_unix(endive_item) == OPEN_PERIOD_END

    root_only = {
        "cancel_at": None,
        "current_period_end": PERIOD_END,
        "items": {"data": [{}]},
    }
    assert subscription_access_until_unix(root_only) == PERIOD_END


def test_api_version_is_the_stripe_16_default() -> None:
    import stripe
    from stripe._api_version import _ApiVersion

    from apps.integrations.stripe_payments import STRIPE_API_VERSION, _stripe_module

    assert stripe.VERSION == "16.0.0"
    assert _ApiVersion.CURRENT == "2026-09-30.endive"
    assert STRIPE_API_VERSION == _ApiVersion.CURRENT
    module = _stripe_module()
    assert module.api_version == "2026-09-30.endive"
    assert module is stripe


def test_cancel_subscription_modifies_at_period_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    import apps.integrations.stripe_payments as sp

    calls = _install_fake_stripe(monkeypatch, status="trialing", trial_end=PERIOD_END)
    remote = sp.cancel_subscription("sub_trial")
    assert calls == [("modify", "sub_trial", {"cancel_at_period_end": True})]
    assert remote["status"] == "trialing"
    assert "current_period_end" not in remote
    assert remote["cancel_at"] == PERIOD_END
    assert remote["trial_end"] == PERIOD_END
    assert remote["items"]["data"][0]["current_period_end"] == PERIOD_END
    assert sp.subscription_access_until_unix(remote) == PERIOD_END
    assert sp._stripe_module().api_version == "2026-09-30.endive"


def test_reactivate_subscription_clears_period_end_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    import apps.integrations.stripe_payments as sp

    calls = _install_fake_stripe(
        monkeypatch, status="active", open_item_end=OPEN_PERIOD_END
    )
    remote = sp.reactivate_subscription("sub_back")
    assert calls == [("modify", "sub_back", {"cancel_at_period_end": False})]
    assert remote["cancel_at"] is None
    assert remote["status"] == "active"
    assert "current_period_end" not in remote
    assert sp.subscription_access_until_unix(remote) == OPEN_PERIOD_END


def _seed_paid_automation(client: TestClient, email: str, *, status: str = "trialing") -> tuple[dict, dict]:
    import apps.interface.api as api_module

    reg = _register(client, email)
    client_id = reg["client"]["client_id"]
    store = api_module.runtime.store
    business_id = store.ensure_default_business(client_id)["business_id"]
    store.upsert_subscription(
        client_id=client_id,
        automation_type="google_reviews",
        status=status,
        stripe_subscription_id="sub_to_cancel",
    )
    store.activate_automation(client_id, business_id, "google_reviews", "wf-1")
    return reg, store


def test_schedule_cancel_keeps_trial_and_automation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    calls = _install_fake_stripe(
        monkeypatch,
        status="trialing",
        trial_end=PERIOD_END,
        open_item_end=OPEN_PERIOD_END,
    )

    reg, store = _seed_paid_automation(client, "unsub@example.com", status="trialing")
    client_id = reg["client"]["client_id"]
    auth = {"Authorization": f"Bearer {reg['token']}"}

    resp = client.post("/client/subscriptions/google_reviews/cancel", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "trialing"
    assert body["cancel_at_period_end"] is True
    assert body["access_until"] == "01/01/2026"
    assert body["automation_active"] is True
    assert calls == [("modify", "sub_to_cancel", {"cancel_at_period_end": True})]

    assert store.has_active_subscription(client_id, "google_reviews")
    business_id = store.ensure_default_business(client_id)["business_id"]
    auto = store.get_automation(client_id, business_id, "google_reviews")
    assert auto["status"] == "active"
    row = store.get_subscription(client_id, "google_reviews")
    assert row["status"] == "trialing"
    assert row["cancel_at_period_end"] == 1
    assert row["current_period_end"] == str(PERIOD_END)

    listed = client.get("/client/subscriptions", headers=auth)
    shown = listed.json()["subscriptions"][0]
    assert shown["access_until"] == "01/01/2026"
    assert shown["cancel_at_period_end"] is True

    again = client.post("/client/subscriptions/google_reviews/reactivate", headers=auth)
    assert again.status_code == 200
    assert again.json()["cancel_at_period_end"] is False
    assert again.json()["status"] == "trialing"
    assert calls[1] == ("modify", "sub_to_cancel", {"cancel_at_period_end": False})
    assert store.get_automation(client_id, business_id, "google_reviews")["status"] == "active"
    cleared = client.get("/client/subscriptions", headers=auth).json()["subscriptions"][0]
    assert cleared["cancel_at_period_end"] is False
    assert cleared["access_until"] is None
    assert store.get_subscription(client_id, "google_reviews")["current_period_end"] == str(
        OPEN_PERIOD_END
    )


def test_subscription_updated_does_not_deactivate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRET", "whsec_test")
    import apps.integrations.stripe_payments as sp
    import apps.interface.api as api_module

    reg, store = _seed_paid_automation(client, "updated@example.com", status="active")
    client_id = reg["client"]["client_id"]
    business_id = store.ensure_default_business(client_id)["business_id"]

    scheduled = {
        "type": "customer.subscription.updated",
        "data": {
            "object": _basil_subscription(
                "sub_to_cancel", status="active", cancel_at=None, item_end=PERIOD_END
            )
        },
    }
    scheduled["data"]["object"]["cancel_at"] = None
    monkeypatch.setattr(sp, "construct_webhook_event", lambda payload, sig: scheduled)
    resp = client.post(
        "/internal/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert resp.status_code == 200
    assert store.get_automation(client_id, business_id, "google_reviews")["status"] == "active"
    assert store.has_active_subscription(client_id, "google_reviews")
    row = store.get_subscription(client_id, "google_reviews")
    assert row["cancel_at_period_end"] == 1
    assert row["current_period_end"] == str(PERIOD_END)
    assert row["status"] == "active"


@pytest.mark.parametrize("raw_status", ["unpaid", "canceled", "incomplete_expired"])
def test_subscription_updated_terminal_status_deactivates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, raw_status: str
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRET", "whsec_test")
    import apps.integrations.stripe_payments as sp
    import apps.interface.api as api_module

    reg, store = _seed_paid_automation(client, f"{raw_status}@example.com", status="active")
    client_id = reg["client"]["client_id"]
    business_id = store.ensure_default_business(client_id)["business_id"]
    terminal = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_to_cancel",
                "status": raw_status,
                "cancel_at_period_end": False,
                "cancel_at": None,
                "current_period_end": None,
                "items": {"data": [{"current_period_end": None}]},
            }
        },
    }
    monkeypatch.setattr(sp, "construct_webhook_event", lambda payload, sig: terminal)
    resp = client.post(
        "/internal/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )
    assert resp.status_code == 200
    assert store.get_automation(client_id, business_id, "google_reviews")["status"] == "inactive"
    assert not store.has_active_subscription(client_id, "google_reviews")
    expected = "canceled" if raw_status == "incomplete_expired" else raw_status
    assert store.get_subscription(client_id, "google_reviews")["status"] == expected


def _post_subscription_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, event: dict
):
    import apps.integrations.stripe_payments as sp

    monkeypatch.setattr(sp, "construct_webhook_event", lambda payload, sig: event)
    return client.post(
        "/internal/stripe/webhook",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=fake"},
    )


def test_late_updated_after_deleted_stays_canceled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRET", "whsec_test")

    reg, store = _seed_paid_automation(client, "late-updated@example.com", status="active")
    client_id = reg["client"]["client_id"]
    business_id = store.ensure_default_business(client_id)["business_id"]

    deleted = {
        "type": "customer.subscription.deleted",
        "created": 300,
        "data": {"object": {"id": "sub_to_cancel", "status": "canceled"}},
    }
    assert _post_subscription_event(client, monkeypatch, deleted).status_code == 200
    assert store.get_subscription(client_id, "google_reviews")["status"] == "canceled"
    assert store.get_subscription(client_id, "google_reviews")["stripe_event_created"] == 300
    assert store.get_automation(client_id, business_id, "google_reviews")["status"] == "inactive"

    late = {
        "type": "customer.subscription.updated",
        "created": 200,
        "data": {
            "object": _basil_subscription(
                "sub_to_cancel", status="active", scheduled=False, cancel_at=None
            )
        },
    }
    assert _post_subscription_event(client, monkeypatch, late).status_code == 200
    row = store.get_subscription(client_id, "google_reviews")
    assert row["status"] == "canceled"
    assert row["stripe_event_created"] == 300
    assert store.get_automation(client_id, business_id, "google_reviews")["status"] == "inactive"

    newer = {
        "type": "customer.subscription.updated",
        "created": 400,
        "data": {
            "object": _basil_subscription(
                "sub_to_cancel", status="active", scheduled=False, cancel_at=None
            )
        },
    }
    assert _post_subscription_event(client, monkeypatch, newer).status_code == 200
    row = store.get_subscription(client_id, "google_reviews")
    assert row["status"] == "canceled"
    assert row["stripe_event_created"] == 400
    assert store.get_automation(client_id, business_id, "google_reviews")["status"] == "inactive"


def test_cancel_and_reactivate_webhooks_out_of_order(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRET", "whsec_test")

    reg, store = _seed_paid_automation(client, "out-of-order@example.com", status="active")
    client_id = reg["client"]["client_id"]
    business_id = store.ensure_default_business(client_id)["business_id"]
    store.mark_subscriptions_by_stripe_id(
        "sub_to_cancel", "active", current_period_end=str(OPEN_PERIOD_END)
    )

    reactivate = {
        "type": "customer.subscription.updated",
        "created": 200,
        "data": {
            "object": _endive_subscription(
                "sub_to_cancel",
                status="active",
                scheduled=False,
                cancel_at=None,
                item_end=PERIOD_END,
            )
        },
    }
    assert _post_subscription_event(client, monkeypatch, reactivate).status_code == 200
    row = store.get_subscription(client_id, "google_reviews")
    assert row["cancel_at_period_end"] == 0
    assert row["stripe_event_created"] == 200
    assert row["current_period_end"] == str(OPEN_PERIOD_END)

    older_cancel = {
        "type": "customer.subscription.updated",
        "created": 100,
        "data": {
            "object": _basil_subscription(
                "sub_to_cancel", status="active", cancel_at=PERIOD_END, item_end=PERIOD_END
            )
        },
    }
    assert _post_subscription_event(client, monkeypatch, older_cancel).status_code == 200
    row = store.get_subscription(client_id, "google_reviews")
    assert row["status"] == "active"
    assert row["cancel_at_period_end"] == 0
    assert row["current_period_end"] == str(OPEN_PERIOD_END)
    assert row["stripe_event_created"] == 200
    assert store.get_automation(client_id, business_id, "google_reviews")["status"] == "active"
    assert store.has_active_subscription(client_id, "google_reviews")


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
    assert items[0]["price_data"]["currency"] == "eur"
    assert items[0]["price_data"]["unit_amount"] == 29000
    assert items[0]["price_data"]["recurring"]["interval"] == "year"


def _complete_session(client_id: str, *, status: str = "complete", payment_status: str = "unpaid") -> dict:
    return {
        "id": "cs_return_1",
        "status": status,
        "payment_status": payment_status,
        "customer": "cus_return",
        "subscription": "sub_return",
        "metadata": {
            "client_id": client_id,
            "automation_types": "google_reviews",
            "billing_interval": "monthly",
        },
        "client_reference_id": client_id,
    }


def test_checkout_success_skips_login_and_prepares_google(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pago confirmado: la respuesta no pinta el login ni pasa por /login."""
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    import apps.integrations.stripe_payments as sp
    import apps.interface.api as api_module

    reg = _register(client, "return@example.com")
    client_id = reg["client"]["client_id"]
    monkeypatch.setattr(
        sp,
        "retrieve_checkout_session",
        lambda session_id, settings=None: _complete_session(client_id),
    )

    resp = client.get(
        "/client/checkout/success",
        params={"session_id": "cs_return_1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert resp.url.path == "/client/checkout/continue"
    assert resp.history
    for hop in resp.history:
        location = hop.headers.get("location", "")
        assert "/login" not in location
        assert "/client?" not in location
        assert "connect=google" not in location
    body = resp.text
    assert "Preparando tu cuenta" in body
    assert 'id="view-login"' not in body
    assert 'id="inp-password"' not in body
    assert 'id="login-overlay"' not in body
    assert "/login" not in body
    assert "/client/google/connect" in body

    store = api_module.runtime.store
    assert store.get_subscription(client_id, "google_reviews")["status"] == "trialing"
    assert store.get_pending_automation(client_id) == "google_reviews"


@pytest.mark.parametrize(
    "session_id,session",
    [
        ("", None),
        ("cs_open", {"status": "open", "payment_status": "unpaid"}),
        ("cs_missing", RuntimeError("No such checkout.session")),
    ],
)
def test_checkout_success_invalid_does_not_reach_continue_or_login(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_id: str,
    session: dict | Exception | None,
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    import apps.integrations.stripe_payments as sp

    def retrieve(sid: str, settings=None):
        if isinstance(session, Exception):
            raise session
        return session or {}

    monkeypatch.setattr(sp, "retrieve_checkout_session", retrieve)
    resp = client.get(
        "/client/checkout/success",
        params={"session_id": session_id},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location == "/client?checkout=error"
    assert "/login" not in location
    assert "checkout/continue" not in location


def test_line_items_price_ids_are_currency_scoped() -> None:
    from apps.integrations.stripe_payments import StripeSettings, _line_items, _line_items_for_pairs

    legacy = StripeSettings(
        secret_key="sk",
        webhook_secret="",
        publishable_key="",
        public_url="http://localhost",
        trial_days=14,
        price_ids={"google_reviews:monthly": "price_legacy_usd"},
    )
    usd = _line_items(legacy, ["google_reviews"], "monthly", "usd")
    assert usd[0]["price"] == "price_legacy_usd"
    eur = _line_items(legacy, ["google_reviews"], "monthly", "eur")
    assert "price" not in eur[0]
    assert eur[0]["price_data"]["currency"] == "eur"
    assert eur[0]["price_data"]["unit_amount"] == 2900

    scoped = StripeSettings(
        secret_key="sk",
        webhook_secret="",
        publishable_key="",
        public_url="http://localhost",
        trial_days=14,
        price_ids={
            "google_reviews:monthly": "price_legacy_usd",
            "google_reviews:monthly:eur": "price_eur",
        },
    )
    assert _line_items(scoped, ["google_reviews"], "monthly", "eur")[0]["price"] == "price_eur"

    pairs = [("google_reviews", "biz-1"), ("google_reviews", "biz-2")]
    blended = _line_items_for_pairs(legacy, pairs, "monthly", "eur")
    assert blended[0]["quantity"] == 2
    assert blended[0]["price_data"]["currency"] == "eur"
    # 2900 + round(2900 * 0.8) = 5220; blended unit = round(5220 / 2) = 2610
    assert blended[0]["price_data"]["unit_amount"] == 2610
    usd_pairs = _line_items_for_pairs(legacy, pairs, "monthly", "usd")
    assert usd_pairs[0]["price"] == "price_legacy_usd"
    assert usd_pairs[0]["quantity"] == 2


def _fake_stripe(
    monkeypatch: pytest.MonkeyPatch,
    created: dict,
    *,
    locked: str | None = None,
    retrieve_error: str | None = None,
):
    import sys
    import types

    class FakeCustomer:
        @staticmethod
        def retrieve(cid):
            if retrieve_error:
                raise RuntimeError(retrieve_error)
            return {"id": cid, "deleted": False, "currency": locked}

        @staticmethod
        def search(**kwargs):
            return {"data": []}

        @staticmethod
        def create(**kwargs):
            return {"id": "cus_new", "currency": locked}

    class FakeSession:
        @staticmethod
        def create(**kwargs):
            created.clear()
            created.update(kwargs)
            return {"id": "cs_test_currency", "url": "https://checkout.stripe.com/c/pay/cs_test_currency"}

    fake = types.ModuleType("stripe")
    fake.Customer = FakeCustomer
    fake.checkout = types.SimpleNamespace(Session=FakeSession)
    fake.api_key = None
    monkeypatch.setitem(sys.modules, "stripe", fake)


def test_checkout_default_currency_builds_eur_price_data(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("ZEROMANUAL_PUBLIC_URL", "http://localhost:8090")
    created: dict = {}
    _fake_stripe(monkeypatch, created)

    reg = _register(client, "eur-default@example.com")
    resp = client.post(
        "/client/checkout/session",
        headers={"Authorization": f"Bearer {reg['token']}"},
        json={"automation_types": ["google_reviews"], "billing_interval": "monthly"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "eur"
    assert body["checkout_url"].startswith("https://checkout.stripe.com/")
    item = created["line_items"][0]
    assert item["price_data"]["currency"] == "eur"
    assert item["price_data"]["unit_amount"] == 2900
    assert item["price_data"]["recurring"]["interval"] == "month"
    assert created["metadata"]["currency"] == "eur"


def test_checkout_usd_builds_usd_price_data(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    created: dict = {}
    _fake_stripe(monkeypatch, created)

    reg = _register(client, "usd-choice@example.com")
    resp = client.post(
        "/client/checkout/session",
        headers={"Authorization": f"Bearer {reg['token']}"},
        json={
            "automation_types": ["instagram_posts"],
            "billing_interval": "yearly",
            "currency": "USD",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["currency"] == "usd"
    item = created["line_items"][0]
    assert item["price_data"]["currency"] == "usd"
    assert item["price_data"]["unit_amount"] == 39000
    assert item["price_data"]["recurring"]["interval"] == "year"


def test_checkout_rejects_unknown_currency(client: TestClient) -> None:
    reg = _register(client, "bad-currency@example.com")
    resp = client.post(
        "/client/checkout/session",
        headers={"Authorization": f"Bearer {reg['token']}"},
        json={"automation_types": ["google_reviews"], "currency": "gbp"},
    )
    assert resp.status_code == 400
    assert "eur" in resp.json()["detail"]


@pytest.mark.parametrize("currency_field", [None, "", "missing"])
def test_checkout_omitted_currency_uses_locked_usd(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, currency_field: str | None
) -> None:
    """A portal checkout sends no currency. A Customer already on USD stays on USD."""
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    created: dict = {}
    _fake_stripe(monkeypatch, created, locked="usd")

    label = {None: "null", "": "blank", "missing": "missing"}[currency_field]
    reg = _register(client, f"locked-omit-{label}@example.com")
    payload: dict = {"automation_types": ["google_reviews"], "billing_interval": "monthly"}
    if currency_field != "missing":
        payload["currency"] = currency_field
    resp = client.post(
        "/client/checkout/session",
        headers={"Authorization": f"Bearer {reg['token']}"},
        json=payload,
    )
    assert resp.status_code == 200
    assert resp.json()["currency"] == "usd"
    item = created["line_items"][0]
    assert item["price_data"]["currency"] == "usd"
    assert item["price_data"]["unit_amount"] == 2900


def test_checkout_customer_retrieve_failure_is_generic(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Customer.retrieve errors use the existing checkout failure, not a 409."""
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    created: dict = {}
    _fake_stripe(monkeypatch, created, retrieve_error="stripe unavailable")

    reg = _register(client, "retrieve-down@example.com")
    resp = client.post(
        "/client/checkout/session",
        headers={"Authorization": f"Bearer {reg['token']}"},
        json={"automation_types": ["google_reviews"]},
    )
    assert resp.status_code == 503
    assert "No se pudo iniciar el pago" in resp.json()["detail"]
    assert created == {}


def test_checkout_refuses_currency_change_on_locked_customer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stripe locks a Customer to one currency. Do not create a second Customer."""
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    import apps.interface.api as api_module

    created: dict = {}
    _fake_stripe(monkeypatch, created, locked="usd")
    reg = _register(client, "locked-usd@example.com")
    client_id = reg["client"]["client_id"]
    api_module.runtime.store.set_stripe_customer_id(client_id, "cus_already_usd")

    resp = client.post(
        "/client/checkout/session",
        headers={"Authorization": f"Bearer {reg['token']}"},
        json={"automation_types": ["google_reviews"], "currency": "eur"},
    )
    assert resp.status_code == 409
    assert "USD" in resp.json()["detail"]
    assert created == {}
    assert api_module.runtime.store.get_client_by_id(client_id)["stripe_customer_id"] == "cus_already_usd"


def test_checkout_success_free_mode_stays_on_error(client: TestClient) -> None:
    resp = client.get(
        "/client/checkout/success",
        params={"session_id": "cs_dev"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/client?checkout=error"


def _stripe_signature(payload: bytes, secret: str) -> str:
    import hashlib
    import hmac
    import time

    timestamp = int(time.time())
    signed = f"{timestamp}.{payload.decode()}"
    digest = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_webhook_accepts_primary_or_extra_signing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import apps.integrations.stripe_payments as sp

    payload = b'{"id":"evt_test","object":"event"}'
    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRET", "whsec_old")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRETS", "whsec_new")
    monkeypatch.setenv("MANUALZERO_STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setenv("MANUALZERO_STRIPE_WEBHOOK_SECRETS", "")

    primary = sp.construct_webhook_event(payload, _stripe_signature(payload, "whsec_old"))
    extra = sp.construct_webhook_event(payload, _stripe_signature(payload, "whsec_new"))
    assert primary["id"] == "evt_test"
    assert extra["id"] == "evt_test"

    with pytest.raises(Exception):
        sp.construct_webhook_event(payload, _stripe_signature(payload, "whsec_other"))


def test_webhook_without_any_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.integrations.stripe_payments as sp

    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_WEBHOOK_SECRETS", "")
    monkeypatch.setenv("MANUALZERO_STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setenv("MANUALZERO_STRIPE_WEBHOOK_SECRETS", "")
    with pytest.raises(RuntimeError, match="WEBHOOK_SECRET"):
        sp.construct_webhook_event(b"{}", "t=1,v1=dead")


def test_checkout_urls_follow_allowlisted_host_not_only_public_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("ZEROMANUAL_PUBLIC_URL", "https://app.srv1255804.hstgr.cloud")
    created: dict = {}
    _fake_stripe(monkeypatch, created)

    reg = _register(client, "host-checkout@example.com")
    auth = {"Authorization": f"Bearer {reg['token']}"}
    resp = client.post(
        "/client/checkout/session",
        headers={**auth, "x-forwarded-host": "exmanual.com"},
        json={"automation_types": ["google_reviews"], "billing_interval": "monthly"},
    )
    assert resp.status_code == 200
    assert created["success_url"] == (
        "https://exmanual.com/client/checkout/success?session_id={CHECKOUT_SESSION_ID}"
    )
    assert created["cancel_url"] == "https://exmanual.com/?checkout=cancelled"

    created.clear()
    resp = client.post(
        "/client/checkout/session",
        headers={**auth, "x-forwarded-host": "app.srv1255804.hstgr.cloud"},
        json={"automation_types": ["google_reviews"], "billing_interval": "monthly"},
    )
    assert resp.status_code == 200
    assert created["success_url"].startswith("https://app.srv1255804.hstgr.cloud/client/checkout/success")
    assert created["cancel_url"] == "https://app.srv1255804.hstgr.cloud/?checkout=cancelled"

    created.clear()
    resp = client.post(
        "/client/checkout/session",
        headers={**auth, "x-forwarded-host": "evil.example"},
        json={"automation_types": ["google_reviews"], "billing_interval": "monthly"},
    )
    assert resp.status_code == 200
    assert created["success_url"].startswith(
        "https://app.srv1255804.hstgr.cloud/client/checkout/success"
    )


def test_billing_portal_return_url_follows_browser_host(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("ZEROMANUAL_PUBLIC_URL", "https://exmanual.com")
    import apps.integrations.stripe_payments as sp
    import apps.interface.api as api_module

    captured: dict = {}

    def fake_portal(*, stripe_customer_id: str, return_url: str | None = None, settings=None):
        captured["customer"] = stripe_customer_id
        captured["return_url"] = return_url
        return {"portal_url": "https://billing.stripe.com/p/session/test"}

    monkeypatch.setattr(sp, "create_billing_portal_session", fake_portal)
    reg = _register(client, "portal-host@example.com")
    api_module.runtime.store.set_stripe_customer_id(reg["client"]["client_id"], "cus_portal")
    resp = client.post(
        "/client/billing/portal",
        headers={
            "Authorization": f"Bearer {reg['token']}",
            "x-forwarded-host": "app.srv1255804.hstgr.cloud",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["portal_url"].startswith("https://billing.stripe.com/")
    assert captured["return_url"] == "https://app.srv1255804.hstgr.cloud/client"
    assert captured["customer"] == "cus_portal"

