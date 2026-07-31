"""Stripe Checkout + subscription routes for the commercial client portal."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from apps.integrations import stripe_payments

logger = logging.getLogger(__name__)


class CheckoutSessionRequest(BaseModel):
    automation_types: list[str]
    billing_interval: str = "monthly"
    # Optional (automation_type, business_id) pairs for multi-business checkout.
    # When provided, takes precedence over automation_types for line-item building
    # and enables the multi-business discount.
    business_pairs: list[list[str]] | None = None


def activate_automation_for_client(
    *,
    store: Any,
    n8n: Any,
    client_id: str,
    client_name: str,
    automation_type: str,
    business_id: str | None = None,
) -> dict:
    if stripe_payments.stripe_enabled() and not store.has_active_subscription(
        client_id, automation_type
    ):
        raise ValueError("Suscripción requerida. Completa el pago antes de activar.")
    templates = json_template_ids()
    if automation_type not in templates:
        raise ValueError(f"Tipo de automatización desconocido: {automation_type}")
    creds = store.get_google_creds(client_id)
    if not creds:
        raise ValueError("Conecta primero tu cuenta de Google Business")
    resolved_business_id = business_id or store.ensure_default_business(client_id)["business_id"]
    existing = store.get_automation(client_id, resolved_business_id, automation_type)
    if existing and existing.get("status") == "active":
        return {
            "status": "active",
            "workflow_id": existing["n8n_workflow_id"],
            "automation": existing,
            "business_id": resolved_business_id,
        }
    template_id = templates[automation_type]
    if not template_id:
        raise RuntimeError("Template no configurado aún")
    business = store.get_business(resolved_business_id)
    location_id = (business or {}).get("location_id") or creds.get("location_id")
    try:
        wf_id = n8n.duplicate_template(
            template_id=template_id,
            client_id=client_id,
            client_name=client_name,
            refresh_token=creds["refresh_token"],
            location_id=location_id,
            automation_type=automation_type,
            business_id=resolved_business_id,
        )
    except Exception as exc:
        raise RuntimeError(f"Error al activar en n8n: {exc}") from exc
    record = store.activate_automation(client_id, resolved_business_id, automation_type, wf_id)
    return {
        "status": "active",
        "workflow_id": wf_id,
        "automation": record,
        "business_id": resolved_business_id,
    }


def json_template_ids() -> dict[str, str]:
    import json

    return json.loads(os.getenv("N8N_TEMPLATE_IDS", "{}"))


def grant_subscriptions_from_checkout(
    store: Any,
    *,
    client_id: str,
    automation_types: list[str],
    billing_interval: str,
    stripe_customer_id: str | None,
    stripe_subscription_id: str | None,
    checkout_session_id: str | None,
    status: str = "trialing",
) -> None:
    if stripe_customer_id:
        store.set_stripe_customer_id(client_id, stripe_customer_id)
    for automation_type in automation_types:
        store.upsert_subscription(
            client_id=client_id,
            automation_type=automation_type,
            status=status,
            billing_interval=billing_interval,
            provider="stripe",
            stripe_subscription_id=stripe_subscription_id,
            stripe_checkout_session_id=checkout_session_id,
        )


def post_payment_redirect(
    *,
    store: Any,
    n8n: Any,
    client_id: str,
    automation_types: list[str],
    business_pairs: list[tuple[str, str]] | None = None,
) -> RedirectResponse:
    client = store.get_client_by_id(client_id)
    if client is None:
        return RedirectResponse(url="/client?checkout=error", status_code=303)
    creds = store.get_google_creds(client_id)
    if not creds:
        if automation_types:
            store.set_pending_automation(client_id, automation_types[0])
        return RedirectResponse(url="/client?checkout=paid&connect=google", status_code=303)
    activated: list[str] = []
    if business_pairs:
        for automation_type, business_id in business_pairs:
            try:
                activate_automation_for_client(
                    store=store,
                    n8n=n8n,
                    client_id=client_id,
                    client_name=client["name"],
                    automation_type=automation_type,
                    business_id=business_id,
                )
                activated.append(automation_type)
            except Exception as exc:
                logger.warning(
                    "Post-payment activate failed for %s/%s/%s: %s",
                    client_id, automation_type, business_id, exc,
                )
    else:
        for automation_type in automation_types:
            try:
                activate_automation_for_client(
                    store=store,
                    n8n=n8n,
                    client_id=client_id,
                    client_name=client["name"],
                    automation_type=automation_type,
                )
                activated.append(automation_type)
            except Exception as exc:
                logger.warning("Post-payment activate failed for %s/%s: %s", client_id, automation_type, exc)
    if activated:
        return RedirectResponse(
            url=f"/client?activated={activated[0]}&checkout=paid",
            status_code=303,
        )
    return RedirectResponse(url="/client?checkout=paid", status_code=303)


def register_payment_routes(
    app: FastAPI,
    *,
    runtime: Any,
    n8n: Any,
    get_client_user: Callable[..., dict],
) -> None:
    store = runtime.store

    @app.post("/client/checkout/session")
    def create_client_checkout_session(
        req: CheckoutSessionRequest, client: dict = Depends(get_client_user)
    ) -> dict:
        business_pairs: list[tuple[str, str]] | None = None
        if req.business_pairs:
            try:
                business_pairs = [(pair[0], pair[1]) for pair in req.business_pairs]
                # Ownership check — a client may only buy for their own businesses.
                for _automation_type, business_id in business_pairs:
                    if store.get_business_for_client(client["client_id"], business_id) is None:
                        raise HTTPException(status_code=404, detail="Negocio no encontrado")
                business_pairs = stripe_payments.validate_checkout_pairs(business_pairs)
                types = sorted({t for t, _ in business_pairs})
            except (IndexError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            try:
                types = stripe_payments.validate_automation_types(req.automation_types)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        interval = "yearly" if req.billing_interval == "yearly" else "monthly"
        cfg = stripe_payments.load_stripe_settings()

        if not stripe_payments.stripe_enabled(cfg):
            for automation_type in types:
                store.upsert_subscription(
                    client_id=client["client_id"],
                    automation_type=automation_type,
                    status="active",
                    billing_interval=interval,
                    provider="dev",
                )
            return {
                "mode": "free",
                "checkout_url": None,
                "automation_types": types,
                "billing_interval": interval,
            }

        stored = store.get_client_by_id(client["client_id"]) or {}
        try:
            session = stripe_payments.create_checkout_session(
                client_id=client["client_id"],
                client_email=client["email"],
                client_name=client.get("name") or stored.get("name") or "",
                automation_types=types,
                billing_interval=interval,
                stripe_customer_id=stored.get("stripe_customer_id") or None,
                settings=cfg,
                business_pairs=business_pairs,
            )
        except Exception as exc:
            logger.exception("Stripe checkout session failed")
            raise HTTPException(
                status_code=503, detail=f"No se pudo iniciar el pago: {exc}"
            ) from exc

        # Persist durable Stripe Customer id (created once, reused forever).
        if session.get("stripe_customer_id"):
            store.set_stripe_customer_id(client["client_id"], session["stripe_customer_id"])

        return {
            "mode": "stripe",
            "checkout_url": session["checkout_url"],
            "session_id": session["session_id"],
            "automation_types": types,
            "billing_interval": interval,
        }

    @app.get("/client/checkout/success")
    def client_checkout_success(session_id: str = "") -> RedirectResponse:
        if not session_id:
            return RedirectResponse(url="/client?checkout=error", status_code=303)
        cfg = stripe_payments.load_stripe_settings()
        if not stripe_payments.stripe_enabled(cfg):
            return RedirectResponse(url="/client?checkout=error", status_code=303)
        try:
            session = stripe_payments.retrieve_checkout_session(session_id, settings=cfg)
            if session.get("status") != "complete":
                return RedirectResponse(url="/client?checkout=error", status_code=303)
            client_id, types, interval = stripe_payments.parse_session_metadata(session)
            business_pairs = stripe_payments.parse_session_business_pairs(session)
            payment_status = session.get("payment_status") or ""
            status = "active" if payment_status == "paid" else "trialing"
            grant_subscriptions_from_checkout(
                store,
                client_id=client_id,
                automation_types=types,
                billing_interval=interval,
                stripe_customer_id=stripe_payments.stripe_id(session.get("customer")),
                stripe_subscription_id=stripe_payments.stripe_id(session.get("subscription")),
                checkout_session_id=session_id,
                status=status,
            )
            return post_payment_redirect(
                store=store,
                n8n=n8n,
                client_id=client_id,
                automation_types=types,
                business_pairs=business_pairs or None,
            )
        except Exception as exc:
            logger.exception("Checkout success handling failed: %s", exc)
            return RedirectResponse(url="/client?checkout=error", status_code=303)

    @app.post("/client/billing/portal")
    def client_billing_portal(client: dict = Depends(get_client_user)) -> dict:
        stored = store.get_client_by_id(client["client_id"]) or {}
        customer_id = stored.get("stripe_customer_id")
        if not customer_id:
            raise HTTPException(status_code=400, detail="No hay cliente de Stripe asociado")
        try:
            return stripe_payments.create_billing_portal_session(stripe_customer_id=customer_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/client/subscriptions")
    def list_client_subscriptions(client: dict = Depends(get_client_user)) -> dict:
        return {"subscriptions": store.list_client_subscriptions(client["client_id"])}

    @app.post("/internal/stripe/webhook")
    async def stripe_webhook(request: Request) -> dict:
        payload = await request.body()
        signature = request.headers.get("stripe-signature", "")
        try:
            event = stripe_payments.construct_webhook_event(payload, signature)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Webhook inválido: {exc}") from exc

        event_type = event["type"]
        data_object = stripe_payments.stripe_object_to_dict(event["data"]["object"])

        if event_type == "checkout.session.completed":
            try:
                client_id, types, interval = stripe_payments.parse_session_metadata(data_object)
                payment_status = data_object.get("payment_status") or ""
                status = "active" if payment_status == "paid" else "trialing"
                grant_subscriptions_from_checkout(
                    store,
                    client_id=client_id,
                    automation_types=types,
                    billing_interval=interval,
                    stripe_customer_id=stripe_payments.stripe_id(data_object.get("customer")),
                    stripe_subscription_id=stripe_payments.stripe_id(
                        data_object.get("subscription")
                    ),
                    checkout_session_id=stripe_payments.stripe_id(data_object.get("id")),
                    status=status,
                )
            except Exception as exc:
                logger.exception("stripe checkout.session.completed failed: %s", exc)
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        elif event_type in (
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            sub_id = stripe_payments.stripe_id(data_object.get("id"))
            raw_status = data_object.get("status") or "canceled"
            if event_type == "customer.subscription.deleted":
                raw_status = "canceled"
            mapped = {
                "active": "active",
                "trialing": "trialing",
                "past_due": "past_due",
                "canceled": "canceled",
                "unpaid": "unpaid",
                "incomplete": "incomplete",
                "incomplete_expired": "canceled",
                "paused": "paused",
            }.get(raw_status, raw_status)
            if sub_id:
                store.mark_subscriptions_by_stripe_id(sub_id, mapped)
                if mapped in ("canceled", "unpaid"):
                    for sub in store.list_subscriptions_by_stripe_id(sub_id):
                        for auto in store.list_automations_by_type(
                            sub["client_id"], sub["automation_type"]
                        ):
                            store.deactivate_automation(
                                sub["client_id"], auto["business_id"], sub["automation_type"]
                            )

        elif event_type == "invoice.payment_failed":
            sub_id = stripe_payments.stripe_id(data_object.get("subscription"))
            if sub_id:
                store.mark_subscriptions_by_stripe_id(sub_id, "past_due")

        return {"received": True}
