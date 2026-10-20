"""Baja de suscripción al final del periodo y webhooks de Stripe."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from apps.integrations import stripe_payments

_STATUS_MAP = {
    "active": "active",
    "trialing": "trialing",
    "past_due": "past_due",
    "canceled": "canceled",
    "unpaid": "unpaid",
    "incomplete": "incomplete",
    "incomplete_expired": "canceled",
    "paused": "paused",
}

# Master apagaba la automatización cuando el status mapeado era canceled o
# unpaid. incomplete_expired se mapea a canceled, así que también apaga.
_DEACTIVATE_STATUSES = frozenset({"unpaid", "canceled", "incomplete_expired"})


def owned_stripe_subscription(store: Any, client_id: str, automation_type: str) -> tuple[dict, str]:
    sub = store.get_subscription(client_id, automation_type)
    if not sub:
        raise HTTPException(status_code=404, detail="No hay suscripción")
    stripe_sub_id = str(sub.get("stripe_subscription_id") or "")
    if not stripe_sub_id:
        raise HTTPException(status_code=400, detail="Esta suscripción no está en Stripe")
    if sub.get("status") not in ("active", "trialing", "paid", "past_due"):
        raise HTTPException(status_code=400, detail="La suscripción no está activa")
    linked = store.list_subscriptions_by_stripe_id(stripe_sub_id)
    if any(row["client_id"] != client_id for row in linked):
        raise HTTPException(status_code=403, detail="Suscripción de otro cliente")
    return sub, stripe_sub_id


def schedule_cancel(store: Any, client_id: str, automation_type: str) -> dict:
    """Programa la baja. No apaga la automatización."""
    sub, stripe_sub_id = owned_stripe_subscription(store, client_id, automation_type)
    try:
        remote = stripe_payments.cancel_subscription(stripe_sub_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"No se pudo programar la baja: {exc}"
        ) from exc
    status = stripe_payments.access_status_after_schedule(
        remote.get("status"), str(sub.get("status") or "active")
    )
    end_unix = stripe_payments.subscription_access_until_unix(remote)
    store.mark_subscriptions_by_stripe_id(
        stripe_sub_id,
        status,
        current_period_end=str(end_unix) if end_unix else None,
        cancel_at_period_end=True,
    )
    return {
        "status": status,
        "cancel_at_period_end": True,
        "access_until": stripe_payments.format_access_until(end_unix),
        "automation_active": True,
    }


def reactivate(store: Any, client_id: str, automation_type: str) -> dict:
    """Anula la baja programada. La suscripción vuelve a renovarse."""
    sub, stripe_sub_id = owned_stripe_subscription(store, client_id, automation_type)
    try:
        remote = stripe_payments.reactivate_subscription(stripe_sub_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"No se pudo reactivar la suscripción: {exc}"
        ) from exc
    status = stripe_payments.access_status_after_schedule(
        remote.get("status"), str(sub.get("status") or "active")
    )
    end_unix = stripe_payments.subscription_access_until_unix(remote)
    store.mark_subscriptions_by_stripe_id(
        stripe_sub_id,
        status,
        current_period_end=str(end_unix) if end_unix else None,
        cancel_at_period_end=False,
    )
    return {
        "status": status,
        "cancel_at_period_end": False,
        "access_until": None,
        "automation_active": True,
    }


def deactivate_paid_automations(store: Any, stripe_subscription_id: str) -> None:
    for sub in store.list_subscriptions_by_stripe_id(stripe_subscription_id):
        for auto in store.list_automations_by_type(sub["client_id"], sub["automation_type"]):
            store.deactivate_automation(
                sub["client_id"], auto["business_id"], sub["automation_type"]
            )


def _event_created(value: Any) -> int | None:
    if value is None or value is False or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def apply_subscription_webhook(
    store: Any,
    event_type: str,
    data_object: dict[str, Any],
    event_created: Any = None,
) -> None:
    """Sincroniza la suscripción.

    ``deleted`` apaga la automatización. ``updated`` también la apaga si el
    status es ``unpaid``, ``canceled`` o ``incomplete_expired``. Un cambio
    solo de ``cancel_at_period_end`` (la suscripción sigue active o trialing)
    no la apaga. Un ``updated`` no saca una fila de ``canceled``.

    Se guarda ``event.created`` del último evento aplicado y se ignora
    cualquiera estrictamente más antiguo. El mismo ``created`` sí se aplica.
    """
    sub_id = stripe_payments.stripe_id(data_object.get("id"))
    if not sub_id:
        return
    created = _event_created(event_created)
    if not store.subscription_event_is_current(sub_id, created):
        return
    if event_type == "customer.subscription.updated" and any(
        row.get("status") == "canceled"
        for row in store.list_subscriptions_by_stripe_id(sub_id)
    ):
        store.mark_subscriptions_by_stripe_id(
            sub_id, "canceled", stripe_event_created=created
        )
        return
    if event_type == "customer.subscription.deleted":
        store.mark_subscriptions_by_stripe_id(
            sub_id, "canceled", cancel_at_period_end=False, stripe_event_created=created
        )
        deactivate_paid_automations(store, sub_id)
        return
    if event_type != "customer.subscription.updated":
        return
    raw_status = str(data_object.get("status") or "active")
    mapped = _STATUS_MAP.get(raw_status, raw_status)
    scheduled = data_object.get("cancel_at_period_end")
    flag = bool(scheduled) if "cancel_at_period_end" in data_object else None
    end_unix = stripe_payments.subscription_access_until_unix(data_object) if flag else None
    store.mark_subscriptions_by_stripe_id(
        sub_id,
        mapped,
        current_period_end=str(end_unix) if end_unix else None,
        cancel_at_period_end=flag,
        stripe_event_created=created,
    )
    if raw_status in _DEACTIVATE_STATUSES:
        deactivate_paid_automations(store, sub_id)
