from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apps.commercial.config import load_commercial_settings
from apps.commercial.store import DataStore
from apps.integrations.google_oauth import GoogleOAuthHelper
from apps.integrations.n8n_client import N8nClient
from apps.integrations.ops_bridge import OpsCenterBridge
from apps.zeromanual_env import zm_env

logger = logging.getLogger(__name__)

app = FastAPI(title="ZeroManual Commercial API", version="0.2.0")
settings = load_commercial_settings()
store = DataStore(settings.db_path)
_n8n = N8nClient()
_google_oauth = GoogleOAuthHelper()
_ops = OpsCenterBridge()


def get_admin_user(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        user = store.get_session_user(token)
        if user is not None:
            return user
    raise HTTPException(status_code=401, detail="Autenticación requerida")


def get_client_user(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        client = store.get_client_session(token)
        if client is not None:
            return client
    raise HTTPException(status_code=401, detail="Autenticación requerida")


def verify_webhook_secret(x_webhook_secret: str | None = Header(default=None)) -> None:
    secret = settings.webhook_secret
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


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "zeromanual-commercial",
        "ops_bridge": _ops.enabled,
    }


@app.get("/", response_class=HTMLResponse)
def zeroman_site() -> str:
    page = Path(__file__).parent.parent / "web" / "zeroman" / "index.html"
    return page.read_text(encoding="utf-8")


@app.get("/admin", response_class=HTMLResponse)
def admin_portal() -> str:
    return Path(__file__).with_name("admin.html").read_text(encoding="utf-8")


@app.get("/ui")
def ui_redirect() -> RedirectResponse:
    ops = settings.ops_url or "http://localhost:8091"
    return RedirectResponse(f"{ops}/ui")


@app.post("/auth/login")
def login(req: LoginRequest) -> dict:
    user = store.authenticate_user(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token = store.create_session(user["user_id"])
    return {"token": token, "user": user}


@app.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        store.delete_session(authorization.removeprefix("Bearer "))
    return {"ok": True}


@app.get("/auth/me")
def me(user: dict = Depends(get_admin_user)) -> dict:
    return {"user": user}


@app.get("/api/v1/admin/users")
def admin_list_users(user: dict = Depends(get_admin_user)) -> dict:
    return {"users": store.list_users()}


@app.post("/api/v1/admin/users")
def admin_create_user(req: CreateUserRequest, user: dict = Depends(get_admin_user)) -> dict:
    try:
        new_user = store.create_user(req.username, req.email, req.password, req.role)
        return {"user": new_user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/api/v1/admin/users/{user_id}")
def admin_delete_user(user_id: str, user: dict = Depends(get_admin_user)) -> dict:
    if user["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")
    store.delete_user(user_id)
    return {"ok": True}


@app.get("/api/v1/admin/clients")
def admin_list_clients(user: dict = Depends(get_admin_user)) -> dict:
    clients = store.list_clients()
    enriched = []
    for c in clients:
        autos = store.list_client_automations(c["client_id"])
        creds = store.get_google_creds(c["client_id"])
        enriched.append(
            {
                **c,
                "automations": autos,
                "google_connected": creds is not None,
                "google_email": creds.get("google_email") if creds else None,
            }
        )
    return {"clients": enriched, "ops_url": settings.ops_url or None}


@app.post("/api/v1/admin/clients")
def admin_create_client(req: ClientRegisterRequest, user: dict = Depends(get_admin_user)) -> dict:
    try:
        client = store.create_client(req.name, req.email, req.password)
        return {"client": client}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/api/v1/admin/clients/{client_id}")
def admin_delete_client(client_id: str, user: dict = Depends(get_admin_user)) -> dict:
    store.delete_client(client_id)
    return {"ok": True}


@app.get("/client", response_class=HTMLResponse)
def client_portal() -> str:
    page = Path(__file__).with_name("client.html")
    if not page.is_file():
        return "<html><body><h1>Portal Cliente</h1><p>En construcción.</p></body></html>"
    return page.read_text(encoding="utf-8")


@app.post("/client/login")
def client_login(req: ClientLoginRequest) -> dict:
    client = store.authenticate_client(req.email, req.password)
    if client is None:
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    token = store.create_client_session(client["client_id"])
    return {"token": token, "client": client}


@app.post("/client/logout")
def client_logout(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        store.delete_client_session(authorization.removeprefix("Bearer "))
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
        store.save_google_creds(
            client_id=client_id,
            refresh_token=tokens.get("refresh_token", ""),
            access_token=tokens.get("access_token"),
            token_expiry=expiry,
            google_email=google_email,
            location_id=None,
        )
        return RedirectResponse("/client?connected=1")
    except Exception:
        logger.exception("Google OAuth callback failed")
        return RedirectResponse("/client?error=oauth_failed")


@app.get("/client/google/status")
def google_status(client: dict = Depends(get_client_user)) -> dict:
    creds = store.get_google_creds(client["client_id"])
    return {
        "connected": creds is not None,
        "google_email": creds["google_email"] if creds else None,
        "location_id": creds["location_id"] if creds else None,
        "connected_at": creds["connected_at"] if creds else None,
    }


@app.get("/client/automations")
def list_client_automations(client: dict = Depends(get_client_user)) -> dict:
    available = list(json.loads(os.getenv("N8N_TEMPLATE_IDS", "{}")).keys())
    active = store.list_client_automations(client["client_id"])
    return {"available": available, "active": active}


@app.post("/client/automations/{automation_type}/activate")
def activate_client_automation(
    automation_type: str, client: dict = Depends(get_client_user)
) -> dict:
    templates = json.loads(os.getenv("N8N_TEMPLATE_IDS", "{}"))
    if automation_type not in templates:
        raise HTTPException(status_code=400, detail=f"Tipo de automatización desconocido: {automation_type}")
    creds = store.get_google_creds(client["client_id"])
    if not creds:
        raise HTTPException(status_code=400, detail="Conecta primero tu cuenta de Google Business")
    template_id = templates[automation_type]
    if not template_id:
        raise HTTPException(status_code=503, detail="Template no configurado aún")
    try:
        wf_id = _n8n.duplicate_template(
            template_id=template_id,
            client_id=client["client_id"],
            client_name=client["name"],
            refresh_token=creds["refresh_token"],
            location_id=creds.get("location_id"),
            automation_type=automation_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Error al activar en n8n: {exc}") from exc
    record = store.activate_automation(client["client_id"], automation_type, wf_id)
    _ops.notify_automation_activated(client, automation_type, wf_id)
    return {"status": "active", "workflow_id": wf_id, "automation": record}


@app.delete("/client/automations/{automation_type}")
def deactivate_client_automation(
    automation_type: str, client: dict = Depends(get_client_user)
) -> dict:
    automation = store.get_automation(client["client_id"], automation_type)
    if automation and automation.get("n8n_workflow_id"):
        try:
            _n8n.delete_workflow(automation["n8n_workflow_id"])
        except Exception:
            pass
    store.deactivate_automation(client["client_id"], automation_type)
    return {"status": "inactive"}


@app.post("/internal/automations/{automation_type}/drafts")
def push_automation_draft(
    automation_type: str, body: DraftPushRequest, _: None = Depends(verify_webhook_secret)
) -> dict:
    draft = store.create_draft(
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
    drafts = store.list_drafts(client["client_id"], automation_type, status)
    return {"drafts": drafts}


@app.post("/client/drafts/{draft_id}/approve")
def approve_client_draft(
    draft_id: str, body: DraftResolveRequest, client: dict = Depends(get_client_user)
) -> dict:
    draft = store.get_draft(draft_id)
    if draft is None or draft["client_id"] != client["client_id"]:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    final_reply = body.final_reply if body.final_reply is not None else draft["suggested_reply"]
    status = "edited" if final_reply != draft["suggested_reply"] else "approved"
    updated = store.resolve_draft(draft_id, status, final_reply)
    return {"draft": updated}


@app.post("/client/drafts/{draft_id}/reject")
def reject_client_draft(draft_id: str, client: dict = Depends(get_client_user)) -> dict:
    draft = store.get_draft(draft_id)
    if draft is None or draft["client_id"] != client["client_id"]:
        raise HTTPException(status_code=404, detail="Borrador no encontrado")
    updated = store.resolve_draft(draft_id, "rejected", None)
    return {"draft": updated}


@app.post("/client/register")
def client_register(req: ClientRegisterRequest) -> dict:
    try:
        client = store.create_client(req.name, req.email, req.password)
        token = store.create_client_session(client["client_id"])
        _ops.notify_client_registered(client)
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
