from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apps.integrations.google_oauth import GoogleOAuthHelper
from apps.integrations.n8n_client import N8nClient
from apps.orchestrator.runtime import OrchestratorRuntime
from apps.zeromanual_env import zm_env

app = FastAPI(title="ZeroManual Web API", version="0.2.0")
runtime = OrchestratorRuntime()
_n8n = N8nClient()
_google_oauth = GoogleOAuthHelper()


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
    review_id: str | None = None
    reviewer_name: str | None = None
    rating: str | None = None
    source_text: str | None = None
    suggested_reply: str


class DraftResolveRequest(BaseModel):
    final_reply: str | None = None


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
    except Exception as exc:
        logging.getLogger(__name__).exception("Google OAuth callback failed: %s", exc)
        return RedirectResponse("/client?error=oauth_failed")

    pending_type = runtime.store.get_pending_automation(client_id)
    if pending_type:
        runtime.store.clear_pending_automation(client_id)
        pending_client = runtime.store.get_client_by_id(client_id)
        client_name = pending_client["name"] if pending_client else client_id
        try:
            _activate_automation_for_client(client_id, client_name, pending_type)
            return RedirectResponse(f"/client?activated={pending_type}")
        except Exception:
            return RedirectResponse("/client?connected=1")
    return RedirectResponse("/client?connected=1")


@app.get("/client/google/status")
def google_status(client: dict = Depends(get_client_user)) -> dict:
    creds = runtime.store.get_google_creds(client["client_id"])
    return {
        "connected": creds is not None,
        "google_email": creds["google_email"] if creds else None,
        "location_id": creds["location_id"] if creds else None,
        "connected_at": creds["connected_at"] if creds else None,
    }


@app.get("/client/automations")
def list_client_automations(client: dict = Depends(get_client_user)) -> dict:
    available = list(json.loads(os.getenv("N8N_TEMPLATE_IDS", "{}")).keys())
    active = runtime.store.list_client_automations(client["client_id"])
    return {"available": available, "active": active}


def _activate_automation_for_client(client_id: str, client_name: str, automation_type: str) -> dict:
    templates = json.loads(os.getenv("N8N_TEMPLATE_IDS", "{}"))
    if automation_type not in templates:
        raise ValueError(f"Tipo de automatización desconocido: {automation_type}")
    existing = runtime.store.get_automation(client_id, automation_type)
    if existing and existing.get("status") == "active":
        return {"status": "active", "workflow_id": existing["n8n_workflow_id"], "automation": existing}
    creds = runtime.store.get_google_creds(client_id)
    if not creds:
        raise ValueError("Conecta primero tu cuenta de Google Business")
    template_id = templates[automation_type]
    if not template_id:
        raise RuntimeError("Template no configurado aún")
    try:
        wf_id = _n8n.duplicate_template(
            template_id=template_id,
            client_id=client_id,
            client_name=client_name,
            refresh_token=creds["refresh_token"],
            location_id=creds.get("location_id"),
            automation_type=automation_type,
        )
    except Exception as exc:
        raise RuntimeError(f"Error al activar en n8n: {exc}") from exc
    record = runtime.store.activate_automation(client_id, automation_type, wf_id)
    return {"status": "active", "workflow_id": wf_id, "automation": record}


@app.post("/client/automations/{automation_type}/activate")
def activate_client_automation(
    automation_type: str, client: dict = Depends(get_client_user)
) -> dict:
    try:
        return _activate_automation_for_client(client["client_id"], client["name"], automation_type)
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
    automation_type: str, client: dict = Depends(get_client_user)
) -> dict:
    automation = runtime.store.get_automation(client["client_id"], automation_type)
    if automation and automation.get("n8n_workflow_id"):
        try:
            _n8n.delete_workflow(automation["n8n_workflow_id"])
        except Exception:
            pass
    runtime.store.deactivate_automation(client["client_id"], automation_type)
    return {"status": "inactive"}


@app.post("/internal/automations/{automation_type}/drafts")
def push_automation_draft(
    automation_type: str, body: DraftPushRequest, _: None = Depends(verify_webhook_secret)
) -> dict:
    draft = runtime.store.create_draft(
        client_id=body.client_id,
        automation_type=automation_type,
        suggested_reply=body.suggested_reply,
        review_id=body.review_id,
        reviewer_name=body.reviewer_name,
        rating=body.rating,
        source_text=body.source_text,
    )
    return {"status": "ok", "draft": draft}


@app.get("/client/automations/{automation_type}/drafts")
def list_client_drafts(
    automation_type: str, status: str | None = None, client: dict = Depends(get_client_user)
) -> dict:
    drafts = runtime.store.list_drafts(client["client_id"], automation_type, status)
    return {"drafts": drafts}


@app.post("/client/drafts/{draft_id}/approve")
def approve_client_draft(
    draft_id: str, body: DraftResolveRequest, client: dict = Depends(get_client_user)
) -> dict:
    draft = runtime.store.get_draft(draft_id)
    if draft is None or draft["client_id"] != client["client_id"]:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    final_reply = body.final_reply if body.final_reply is not None else draft["suggested_reply"]
    status = "edited" if final_reply != draft["suggested_reply"] else "approved"
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


if __name__ == "__main__":
    import uvicorn

    host = zm_env("INTERFACE_HOST", "0.0.0.0")
    port = int(zm_env("INTERFACE_PORT", "8090"))
    uvicorn.run("apps.interface.api:app", host=host, port=port, reload=False)
