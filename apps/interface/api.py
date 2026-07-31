from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apps.integrations.google_oauth import GoogleOAuthHelper
from apps.integrations.google_business import GoogleBusinessClient, GoogleBusinessError
from apps.integrations.n8n_client import N8nClient
from apps.integrations import stripe_payments
from apps.interface.payments import activate_automation_for_client, register_payment_routes
from apps.orchestrator.runtime import OrchestratorRuntime
from apps.zeromanual_env import zm_env

app = FastAPI(title="ZeroManual Web API", version="0.2.0")
runtime = OrchestratorRuntime()
_n8n = N8nClient()
_google_oauth = GoogleOAuthHelper()
_google_business = GoogleBusinessClient()


def get_admin_user(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        user = runtime.store.get_session_user(token)
        if user is not None:
            return user
    raise HTTPException(status_code=401, detail="Autenticación requerida")


def get_client_user(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        client = runtime.store.get_client_session(token)
        if client is not None:
            return client
    raise HTTPException(status_code=401, detail="Autenticación requerida")


def verify_webhook_secret(x_webhook_secret: str | None = Header(default=None)) -> None:
    secret = runtime.settings.webhook_secret
    if not secret or x_webhook_secret != secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    email: str = ""
    password: str
    role: str = "admin"


class ClientLoginRequest(BaseModel):
    email: str
    password: str


class ClientRegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class DraftPushRequest(BaseModel):
    client_id: str
    business_id: str | None = None
    review_id: str | None = None
    reviewer_name: str | None = None
    rating: str | None = None
    source_text: str | None = None
    suggested_reply: str


class DraftResolveRequest(BaseModel):
    final_reply: str | None = None


class AutomationSettingsRequest(BaseModel):
    reply_mode: str


class PendingAutomationRequest(BaseModel):
    automation_type: str


# ---- Simple in-memory login rate limiting ----
_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 300.0


def _rate_limit_key(request: Request, identifier: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{identifier.lower()}"


def _check_login_rate_limit(key: str) -> None:
    now = time.time()
    attempts = _LOGIN_ATTEMPTS[key]
    attempts[:] = [t for t in attempts if now - t < _LOGIN_WINDOW_SECONDS]
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.",
        )


def _record_failed_login(key: str) -> None:
    _LOGIN_ATTEMPTS[key].append(time.time())


def _clear_login_attempts(key: str) -> None:
    _LOGIN_ATTEMPTS.pop(key, None)


def _resolve_business_id(client_id: str, business_id: str | None) -> str:
    """Resolve the business a request applies to.

    Explicit ``business_id`` is validated for ownership. When omitted, falls back to
    (and lazily creates) the client's default/only business so single-location
    clients never have to think about business selection.
    """
    if business_id:
        business = runtime.store.get_business_for_client(client_id, business_id)
        if business is None:
            raise HTTPException(status_code=404, detail="Negocio no encontrado")
        return business_id
    return runtime.store.ensure_default_business(client_id)["business_id"]


def _sync_businesses_from_google(client_id: str) -> list[dict]:
    """Best-effort refresh of a client's businesses/locations from Google."""
    creds = runtime.store.get_google_creds(client_id)
    if not creds:
        return runtime.store.list_businesses(client_id)
    try:
        businesses, token_update = _google_business.list_businesses_for_creds(creds)
    except GoogleBusinessError:
        return runtime.store.list_businesses(client_id)
    if token_update:
        runtime.store.update_google_access_token(
            client_id, token_update["access_token"], token_update["token_expiry"]
        )
    if businesses:
        return runtime.store.sync_businesses(client_id, businesses)
    return runtime.store.list_businesses(client_id)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def zeroman_site() -> str:
    page = Path(__file__).parent.parent / "web" / "zeroman" / "index.html"
    return page.read_text(encoding="utf-8")


@app.get("/admin", response_class=HTMLResponse)
def admin_portal() -> str:
    page = Path(__file__).with_name("admin.html")
    return page.read_text(encoding="utf-8")


@app.post("/auth/login")
def login(req: LoginRequest, request: Request) -> dict:
    key = _rate_limit_key(request, req.username)
    _check_login_rate_limit(key)
    user = runtime.store.authenticate_user(req.username, req.password)
    if user is None:
        _record_failed_login(key)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    _clear_login_attempts(key)
    token = runtime.store.create_session(user["user_id"])
    return {"token": token, "user": user}


@app.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        runtime.store.delete_session(authorization.removeprefix("Bearer "))
    return {"ok": True}


@app.get("/auth/me")
def me(user: dict = Depends(get_admin_user)) -> dict:
    return {"user": user}


@app.get("/api/v1/admin/users")
def admin_list_users(user: dict = Depends(get_admin_user)) -> dict:
    return {"users": runtime.store.list_users()}


@app.post("/api/v1/admin/users")
def admin_create_user(req: CreateUserRequest, user: dict = Depends(get_admin_user)) -> dict:
    try:
        new_user = runtime.store.create_user(req.username, req.email, req.password, req.role)
        return {"user": new_user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/api/v1/admin/users/{user_id}")
def admin_delete_user(user_id: str, user: dict = Depends(get_admin_user)) -> dict:
    if user["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")
    runtime.store.delete_user(user_id)
    return {"ok": True}


@app.get("/api/v1/admin/clients")
def admin_list_clients(user: dict = Depends(get_admin_user)) -> dict:
    return {"clients": runtime.store.list_clients()}


@app.post("/api/v1/admin/clients")
def admin_create_client(req: ClientRegisterRequest, user: dict = Depends(get_admin_user)) -> dict:
    try:
        client = runtime.store.create_client(req.name, req.email, req.password)
        return {"client": client}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/api/v1/admin/clients/{client_id}")
def admin_delete_client(client_id: str, user: dict = Depends(get_admin_user)) -> dict:
    runtime.store.delete_client(client_id)
    return {"ok": True}


@app.get("/client", response_class=HTMLResponse)
def client_portal() -> str:
    page = Path(__file__).with_name("client.html")
    if not page.is_file():
        return "<html><body><h1>Portal Cliente</h1><p>En construcción.</p></body></html>"
    return page.read_text(encoding="utf-8")


@app.post("/client/login")
def client_login(req: ClientLoginRequest, request: Request) -> dict:
    key = _rate_limit_key(request, req.email)
    _check_login_rate_limit(key)
    client = runtime.store.authenticate_client(req.email, req.password)
    if client is None:
        _record_failed_login(key)
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    _clear_login_attempts(key)
    token = runtime.store.create_client_session(client["client_id"])
    return {"token": token, "client": client}


@app.post("/client/logout")
def client_logout(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        runtime.store.delete_client_session(authorization.removeprefix("Bearer "))
    return {"ok": True}


@app.get("/client/me")
def client_me(client: dict = Depends(get_client_user)) -> dict:
    return {"client": client}


@app.get("/client/google/connect")
def google_connect(client: dict = Depends(get_client_user)) -> dict:
    url = _google_oauth.get_authorization_url(client["client_id"])
    return {"redirect_url": url}


@app.get("/client/google/callback")
def google_callback(code: str, state: str) -> RedirectResponse:
    try:
        client_id, tokens = _google_oauth.exchange_code(code, state)
        google_email = _google_oauth.get_user_email(tokens.get("access_token", ""))
        expiry: str | None = None
        if "expires_in" in tokens:
            expiry = (
                datetime.now(timezone.utc) + timedelta(seconds=int(tokens["expires_in"]))
            ).isoformat()
        runtime.store.save_google_creds(
            client_id=client_id,
            refresh_token=tokens.get("refresh_token", ""),
            access_token=tokens.get("access_token"),
            token_expiry=expiry,
            google_email=google_email,
            location_id=None,
        )
        _sync_businesses_from_google(client_id)
    except Exception as exc:
        logging.getLogger(__name__).exception("Google OAuth callback failed: %s", exc)
        return RedirectResponse("/client?error=oauth_failed")

    pending_type = runtime.store.get_pending_automation(client_id)
    if pending_type:
        runtime.store.clear_pending_automation(client_id)
        pending_client = runtime.store.get_client_by_id(client_id)
        client_name = pending_client["name"] if pending_client else client_id
        try:
            activate_automation_for_client(
                store=runtime.store,
                n8n=_n8n,
                client_id=client_id,
                client_name=client_name,
                automation_type=pending_type,
            )
            return RedirectResponse(f"/client?activated={pending_type}")
        except Exception:
            return RedirectResponse("/client?connected=1")
    return RedirectResponse("/client?connected=1")


@app.get("/client/businesses")
def list_client_businesses(client: dict = Depends(get_client_user)) -> dict:
    """List every Google Business location detected for this client's account."""
    businesses = _sync_businesses_from_google(client["client_id"])
    return {"businesses": businesses}


@app.get("/client/google/status")
def google_status(client: dict = Depends(get_client_user)) -> dict:
    creds = runtime.store.get_google_creds(client["client_id"])
    return {
        "connected": creds is not None,
        "google_email": creds["google_email"] if creds else None,
        "location_id": creds["location_id"] if creds else None,
        "connected_at": creds["connected_at"] if creds else None,
    }


@app.delete("/client/google/disconnect")
def google_disconnect(client: dict = Depends(get_client_user)) -> dict:
    runtime.store.delete_google_creds(client["client_id"])
    return {"connected": False}


@app.get("/client/accounts/status")
def accounts_status(client: dict = Depends(get_client_user)) -> dict:
    """Aggregated connection status for third-party accounts in the client portal."""
    google = runtime.store.get_google_creds(client["client_id"])
    return {
        "accounts": [
            {
                "provider": "google",
                "label": "Google Business",
                "connected": google is not None,
                "account_label": (google or {}).get("google_email"),
                "connected_at": (google or {}).get("connected_at"),
                "connectable": True,
            },
            {
                "provider": "instagram",
                "label": "Instagram",
                "connected": False,
                "account_label": None,
                "connected_at": None,
                "connectable": False,
            },
            {
                "provider": "tiktok",
                "label": "TikTok",
                "connected": False,
                "account_label": None,
                "connected_at": None,
                "connectable": False,
            },
            {
                "provider": "email",
                "label": "Correo",
                "connected": False,
                "account_label": None,
                "connected_at": None,
                "connectable": False,
            },
        ]
    }


@app.get("/client/automations")
def list_client_automations(client: dict = Depends(get_client_user)) -> dict:
    available = list(json.loads(os.getenv("N8N_TEMPLATE_IDS", "{}")).keys())
    active = runtime.store.list_client_automations(client["client_id"])
    return {"available": available, "active": active}


@app.post("/client/automations/{automation_type}/activate")
def activate_client_automation(
    automation_type: str,
    business_id: str | None = None,
    client: dict = Depends(get_client_user),
) -> dict:
    if business_id:
        if runtime.store.get_business_for_client(client["client_id"], business_id) is None:
            raise HTTPException(status_code=404, detail="Negocio no encontrado")
    try:
        return activate_automation_for_client(
            store=runtime.store,
            n8n=_n8n,
            client_id=client["client_id"],
            client_name=client["name"],
            automation_type=automation_type,
            business_id=business_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/client/pending-automation")
def set_pending_automation(
    req: PendingAutomationRequest, client: dict = Depends(get_client_user)
) -> dict:
    runtime.store.set_pending_automation(client["client_id"], req.automation_type)
    return {"ok": True}


@app.delete("/client/automations/{automation_type}")
def deactivate_client_automation(
    automation_type: str,
    business_id: str | None = None,
    client: dict = Depends(get_client_user),
) -> dict:
    client_id = client["client_id"]
    resolved_business_id = _resolve_business_id(client_id, business_id)
    automation = runtime.store.get_automation(client_id, resolved_business_id, automation_type)
    if automation and automation.get("n8n_workflow_id"):
        try:
            _n8n.delete_workflow(automation["n8n_workflow_id"])
        except Exception:
            pass
    runtime.store.deactivate_automation(client_id, resolved_business_id, automation_type)

    stripe_cancelled = False
    sub = runtime.store.get_subscription(client_id, automation_type)
    stripe_sub_id = (sub or {}).get("stripe_subscription_id") if sub else None
    if stripe_sub_id and stripe_payments.stripe_enabled():
        try:
            stripe_payments.cancel_subscription(stripe_sub_id)
            stripe_cancelled = True
        except Exception as exc:
            logging.getLogger(__name__).exception(
                "Stripe cancel failed for %s/%s: %s", client_id, automation_type, exc
            )
            raise HTTPException(
                status_code=503,
                detail=f"Automatización desactivada localmente, pero Stripe no canceló: {exc}",
            ) from exc
        # Same Stripe sub may cover several automations (multi-item cart).
        for linked in runtime.store.list_subscriptions_by_stripe_id(stripe_sub_id):
            runtime.store.upsert_subscription(
                client_id=linked["client_id"],
                automation_type=linked["automation_type"],
                status="canceled",
                billing_interval=linked.get("billing_interval") or "monthly",
                provider=linked.get("provider") or "stripe",
                stripe_subscription_id=stripe_sub_id,
            )
            if linked["automation_type"] != automation_type:
                for other in runtime.store.list_automations_by_type(
                    linked["client_id"], linked["automation_type"]
                ):
                    runtime.store.deactivate_automation(
                        linked["client_id"], other["business_id"], linked["automation_type"]
                    )
    elif sub:
        runtime.store.upsert_subscription(
            client_id=client_id,
            automation_type=automation_type,
            status="canceled",
            billing_interval=sub.get("billing_interval") or "monthly",
            provider=sub.get("provider") or "dev",
            stripe_subscription_id=sub.get("stripe_subscription_id"),
        )

    return {"status": "inactive", "stripe_cancelled": stripe_cancelled}


def _publish_draft_via_n8n(draft: dict, final_reply: str) -> None:
    """Trigger n8n to post the reply to Google. Raises on HTTP failure."""
    business_id = draft.get("business_id") or runtime.store.ensure_default_business(
        draft["client_id"]
    )["business_id"]
    _n8n.trigger_publish_reply(
        draft["client_id"],
        business_id,
        {
            "draft_id": draft["draft_id"],
            "client_id": draft["client_id"],
            "business_id": business_id,
            "review_id": draft.get("review_id"),
            "final_reply": final_reply,
        },
    )


@app.get("/client/automations/{automation_type}/settings")
def get_automation_settings(
    automation_type: str,
    business_id: str | None = None,
    client: dict = Depends(get_client_user),
) -> dict:
    resolved_business_id = _resolve_business_id(client["client_id"], business_id)
    auto = runtime.store.get_automation(client["client_id"], resolved_business_id, automation_type)
    if auto is None:
        raise HTTPException(status_code=404, detail="Automatización no encontrada")
    return {
        "automation_type": automation_type,
        "business_id": resolved_business_id,
        "reply_mode": auto.get("reply_mode") or "approval",
        "status": auto.get("status"),
    }


@app.put("/client/automations/{automation_type}/settings")
def update_automation_settings(
    automation_type: str,
    body: AutomationSettingsRequest,
    business_id: str | None = None,
    client: dict = Depends(get_client_user),
) -> dict:
    resolved_business_id = _resolve_business_id(client["client_id"], business_id)
    try:
        updated = runtime.store.update_automation_settings(
            client["client_id"], resolved_business_id, automation_type, body.reply_mode
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Automatización no encontrada")
    return {
        "automation_type": automation_type,
        "business_id": resolved_business_id,
        "reply_mode": updated.get("reply_mode") or "approval",
        "status": updated.get("status"),
    }


@app.get("/client/automations/google_reviews/reviews")
def list_google_reviews(
    page_token: str | None = None,
    business_id: str | None = None,
    client: dict = Depends(get_client_user),
) -> dict:
    """List live Google Business Profile reviews for the connected account."""
    client_id = client["client_id"]
    creds = runtime.store.get_google_creds(client_id)
    if creds is None:
        raise HTTPException(
            status_code=400,
            detail="Conecta primero tu cuenta de Google Business",
        )
    resolved_business_id = _resolve_business_id(client_id, business_id)
    business = runtime.store.get_business(resolved_business_id)
    location_override = (business or {}).get("location_id")
    if location_override and not location_override.startswith("accounts/"):
        # Placeholder/legacy business rows may hold a bare id or none at all —
        # fall back to normal resolution rather than sending a bogus name to Google.
        location_override = None
    try:
        payload, location, token_update = _google_business.fetch_reviews_for_creds(
            creds, page_size=50, page_token=page_token, location_override=location_override
        )
    except GoogleBusinessError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if token_update:
        runtime.store.update_google_access_token(
            client_id, token_update["access_token"], token_update["token_expiry"]
        )
    if location and location != creds.get("location_id"):
        runtime.store.update_google_location_id(client_id, location)

    drafts = runtime.store.list_drafts(client_id, "google_reviews", business_id=resolved_business_id)
    by_review: dict[str, dict] = {}
    for d in drafts:
        rid = d.get("review_id")
        if rid and rid not in by_review:
            by_review[str(rid)] = d

    for rev in payload["reviews"]:
        rid = str(rev.get("review_id") or "")
        draft = by_review.get(rid)
        # Also match full resource name suffixes
        if draft is None and rid:
            for key, d in by_review.items():
                if key.endswith(rid) or rid.endswith(key.rsplit("/", 1)[-1]):
                    draft = d
                    break
        rev["draft"] = (
            {
                "draft_id": draft["draft_id"],
                "status": draft["status"],
                "suggested_reply": draft.get("suggested_reply"),
                "final_reply": draft.get("final_reply"),
            }
            if draft
            else None
        )

    payload["business_id"] = resolved_business_id
    return payload


@app.post("/internal/automations/{automation_type}/drafts")
def push_automation_draft(
    automation_type: str, body: DraftPushRequest, _: None = Depends(verify_webhook_secret)
) -> dict:
    business_id = body.business_id or runtime.store.ensure_default_business(body.client_id)["business_id"]
    draft = runtime.store.create_draft(
        client_id=body.client_id,
        automation_type=automation_type,
        suggested_reply=body.suggested_reply,
        business_id=business_id,
        review_id=body.review_id,
        reviewer_name=body.reviewer_name,
        rating=body.rating,
        source_text=body.source_text,
    )
    auto = runtime.store.get_automation(body.client_id, business_id, automation_type)
    reply_mode = (auto or {}).get("reply_mode") or "approval"
    if reply_mode == "auto":
        try:
            _publish_draft_via_n8n(draft, body.suggested_reply)
            draft = runtime.store.resolve_draft(
                draft["draft_id"], "auto_sent", body.suggested_reply
            )
        except Exception as exc:
            logging.getLogger(__name__).exception(
                "Auto-publish failed for draft %s: %s", draft["draft_id"], exc
            )
            draft = runtime.store.resolve_draft(draft["draft_id"], "failed", body.suggested_reply)
            return {"status": "failed", "draft": draft, "error": str(exc)}
    return {"status": "ok", "draft": draft}


@app.get("/client/automations/{automation_type}/drafts")
def list_client_drafts(
    automation_type: str,
    status: str | None = None,
    business_id: str | None = None,
    client: dict = Depends(get_client_user),
) -> dict:
    drafts = runtime.store.list_drafts(client["client_id"], automation_type, status, business_id=business_id)
    return {"drafts": drafts}


@app.post("/client/drafts/{draft_id}/approve")
def approve_client_draft(
    draft_id: str, body: DraftResolveRequest, client: dict = Depends(get_client_user)
) -> dict:
    draft = runtime.store.get_draft(draft_id)
    if draft is None or draft["client_id"] != client["client_id"]:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    if draft.get("status") != "pending":
        raise HTTPException(status_code=400, detail="El borrador ya fue resuelto")
    final_reply = body.final_reply if body.final_reply is not None else draft["suggested_reply"]
    status = "edited" if final_reply != draft["suggested_reply"] else "approved"
    try:
        _publish_draft_via_n8n(draft, final_reply)
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "Publish failed for draft %s: %s", draft_id, exc
        )
        runtime.store.resolve_draft(draft_id, "failed", final_reply)
        raise HTTPException(
            status_code=503, detail=f"No se pudo publicar en Google: {exc}"
        ) from exc
    updated = runtime.store.resolve_draft(draft_id, status, final_reply)
    return {"draft": updated}


@app.post("/client/drafts/{draft_id}/reject")
def reject_client_draft(draft_id: str, client: dict = Depends(get_client_user)) -> dict:
    draft = runtime.store.get_draft(draft_id)
    if draft is None or draft["client_id"] != client["client_id"]:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    updated = runtime.store.resolve_draft(draft_id, "rejected", None)
    return {"draft": updated}


@app.post("/client/register")
def client_register(req: ClientRegisterRequest) -> dict:
    try:
        client = runtime.store.create_client(req.name, req.email, req.password)
        token = runtime.store.create_client_session(client["client_id"])
        return {"token": token, "client": client}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


_zeroman_dir = Path(__file__).parent.parent / "web" / "zeroman"
app.mount("/assets", StaticFiles(directory=str(_zeroman_dir)), name="zeroman-assets")

register_payment_routes(app, runtime=runtime, n8n=_n8n, get_client_user=get_client_user)


if __name__ == "__main__":
    import uvicorn

    host = zm_env("INTERFACE_HOST", "0.0.0.0")
    port = int(zm_env("INTERFACE_PORT", "8090"))
    uvicorn.run("apps.interface.api:app", host=host, port=port, reload=False)
