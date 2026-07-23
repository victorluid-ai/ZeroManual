from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from apps.integrations.accounting_export import AccountingExporter
from apps.zeromanual_env import zm_env
from apps.integrations.google_oauth import GoogleOAuthHelper
from apps.integrations.n8n_client import N8nClient
from apps.integrations.settings import load_integration_settings
from apps.interface.nl import NaturalLanguageInterpreter
from apps.orchestrator.runtime import OrchestratorRuntime
from apps.triggers.config import load_trigger_settings
from apps.triggers.dispatcher import TriggerDispatcher

app = FastAPI(title="ZeroManual Platform API", version="0.1.0")
runtime = OrchestratorRuntime()
nl_interpreter = NaturalLanguageInterpreter()
_n8n = N8nClient()
_google_oauth = GoogleOAuthHelper()


def verify_api_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    # Fails closed: an unset ZEROMANUAL_API_KEY must never mean "no auth
    # required". A valid admin session bearer token is still accepted.
    key = runtime.settings.api_key
    if key and x_api_key == key:
        return
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        if runtime.store.get_session_user(token) is not None:
            return
    raise HTTPException(status_code=401, detail="Invalid API key")


def get_admin_user(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        user = runtime.store.get_session_user(token)
        if user is not None:
            return user
    raise HTTPException(status_code=401, detail="Autenticación requerida")


class EventRequest(BaseModel):
    agent_name: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "zeromanual_ui"
    event_id: str | None = None


class ApproveRequest(BaseModel):
    approved_by: str = "owner"


class RejectRequest(BaseModel):
    rejected_by: str = "owner"
    reason: str = "Rejected by operator."


class NaturalLanguageRequest(BaseModel):
    message: str
    source: str = "zeromanual_nl"
    event_id: str | None = None


class PurgePIIRequest(BaseModel):
    older_than_days: int = 365


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



@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/agents")
def list_agents() -> dict[str, Any]:
    return {"agents": runtime.list_agents()}


@app.post("/api/v1/events")
def submit_event(event: EventRequest, _: None = Depends(verify_api_key)) -> dict[str, Any]:
    event_data = event.model_dump()
    if not event_data["event_id"]:
        event_data["event_id"] = str(uuid4())
    return runtime.process_event(event_data)


@app.post("/api/v1/natural-language")
def submit_natural_language(req: NaturalLanguageRequest, _: None = Depends(verify_api_key)) -> dict[str, Any]:
    interpreted = nl_interpreter.interpret(req.message)
    event_data = {
        "event_id": req.event_id or str(uuid4()),
        "source": req.source,
        "agent_name": interpreted["agent_name"],
        "action": interpreted["action"],
        "payload": interpreted.get("payload", {}),
    }
    result = runtime.process_event(event_data)
    return {
        "message": req.message,
        "interpreted_event": event_data,
        "result": result,
    }


@app.get("/api/v1/approvals")
def list_approvals(_: None = Depends(verify_api_key)) -> dict[str, Any]:
    return {"pending": runtime.list_pending_approvals()}


@app.get("/api/v1/invoices")
def list_invoices(limit: int = 50, _: None = Depends(verify_api_key)) -> dict[str, Any]:
    return {"invoices": runtime.list_invoices(limit=limit)}


@app.get("/api/v1/ledger")
def list_ledger(limit: int = 50, _: None = Depends(verify_api_key)) -> dict[str, Any]:
    return {"ledger_entries": runtime.store.list_ledger_entries(limit=limit)}


@app.get("/api/v1/clients/{client_name}/context")
def client_context(client_name: str, _: None = Depends(verify_api_key)) -> dict[str, Any]:
    return runtime.get_client_context(client_name)


@app.get("/api/v1/invoices/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: str, _: None = Depends(verify_api_key)) -> FileResponse:
    invoice = runtime.store.get_invoice(invoice_id)
    if invoice is None or not invoice.get("pdf_path"):
        raise HTTPException(status_code=404, detail="PDF no disponible para esta factura")
    pdf_path = Path(str(invoice["pdf_path"]))
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="Archivo PDF no encontrado en disco")
    filename = f"{invoice.get('invoice_number') or invoice_id}.pdf".replace("/", "-")
    return FileResponse(path=pdf_path, media_type="application/pdf", filename=filename)


@app.post("/api/v1/accounting/export")
def export_accounting(_: None = Depends(verify_api_key)) -> dict[str, Any]:
    settings = load_integration_settings()
    exporter = AccountingExporter(settings.company, settings.exports_dir)
    export_path = exporter.export_csv(
        invoices=runtime.list_invoices(limit=500),
        ledger_entries=runtime.store.list_ledger_entries(limit=500),
    )
    return {
        "status": "ok",
        "export_path": str(export_path),
        "download_url": f"/api/v1/accounting/export/{export_path.name}",
        "rows_hint": "CSV separado por ; (UTF-8 BOM) para Excel/asesoria",
    }


@app.get("/api/v1/accounting/export/{filename}")
def download_accounting_export(filename: str, _: None = Depends(verify_api_key)) -> FileResponse:
    settings = load_integration_settings()
    safe_name = Path(filename).name
    export_path = Path(settings.exports_dir) / safe_name
    if not export_path.is_file():
        raise HTTPException(status_code=404, detail="Export no encontrado")
    return FileResponse(
        path=export_path,
        media_type="text/csv",
        filename=safe_name,
    )



@app.get("/api/v1/triggers/status")
def triggers_status() -> dict[str, Any]:
    trigger_settings = load_trigger_settings()
    return {
        "email_enabled": trigger_settings.email.enabled,
        "email_folder": trigger_settings.email.imap_folder,
        "poll_interval_seconds": trigger_settings.email.poll_interval_seconds,
        "recent_activity": runtime.store.list_recent_triggers(limit=15),
    }


@app.post("/api/v1/triggers/run-once")
def triggers_run_once(_: None = Depends(verify_api_key)) -> dict[str, Any]:
    dispatcher = TriggerDispatcher(runtime=runtime)
    outcomes = dispatcher.run_cycle()
    return {"processed": len(outcomes), "outcomes": outcomes}


@app.post("/api/v1/maintenance/purge-pii")
def purge_pii(body: PurgePIIRequest, _: None = Depends(verify_api_key)) -> dict[str, Any]:
    result = runtime.store.purge_pii_older_than(body.older_than_days)
    return {"status": "ok", **result}


def _assert_known_operator(operator_id: str) -> None:
    ops = runtime.settings.operators
    if ops and operator_id not in ops:
        raise HTTPException(
            status_code=403,
            detail=f"Unknown operator '{operator_id}'. Add to ZEROMANUAL_OPERATORS in .env.",
        )


@app.post("/api/v1/approvals/{event_id}/approve")
def approve(event_id: str, body: ApproveRequest, _: None = Depends(verify_api_key)) -> dict[str, Any]:
    _assert_known_operator(body.approved_by)
    return runtime.approve(event_id=event_id, approved_by=body.approved_by)


@app.post("/api/v1/approvals/{event_id}/reject")
def reject(event_id: str, body: RejectRequest, _: None = Depends(verify_api_key)) -> dict[str, Any]:
    _assert_known_operator(body.rejected_by)
    return runtime.reject(event_id=event_id, rejected_by=body.rejected_by, reason=body.reason)


@app.get("/", response_class=HTMLResponse)
def zeroman_site() -> str:
    page = Path(__file__).parent.parent / "web" / "zeroman" / "index.html"
    return page.read_text(encoding="utf-8")


@app.get("/ui", response_class=HTMLResponse)
def ui_console() -> str:
    page = Path(__file__).with_name("ui.html")
    return page.read_text(encoding="utf-8")


@app.get("/admin", response_class=HTMLResponse)
def admin_portal() -> str:
    page = Path(__file__).with_name("admin.html")
    return page.read_text(encoding="utf-8")


# ---- Auth ----

@app.post("/auth/login")
def login(req: LoginRequest) -> dict:
    user = runtime.store.authenticate_user(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
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


# ---- Admin portal API (Bearer token auth) ----

@app.get("/api/v1/admin/agents")
def admin_list_agents(user: dict = Depends(get_admin_user)) -> dict:
    return {"agents": runtime.list_agents()}


@app.get("/api/v1/admin/approvals")
def admin_list_approvals(user: dict = Depends(get_admin_user)) -> dict:
    return {"pending": runtime.list_pending_approvals()}


@app.post("/api/v1/admin/approvals/{event_id}/approve")
def admin_approve(event_id: str, user: dict = Depends(get_admin_user)) -> dict:
    return runtime.approve(event_id=event_id, approved_by=user["username"])


@app.post("/api/v1/admin/approvals/{event_id}/reject")
def admin_reject(event_id: str, body: RejectRequest, user: dict = Depends(get_admin_user)) -> dict:
    return runtime.reject(event_id=event_id, rejected_by=user["username"], reason=body.reason)


@app.get("/api/v1/admin/invoices")
def admin_list_invoices(limit: int = 50, user: dict = Depends(get_admin_user)) -> dict:
    return {"invoices": runtime.list_invoices(limit=limit)}


@app.get("/api/v1/admin/ledger")
def admin_list_ledger(limit: int = 50, user: dict = Depends(get_admin_user)) -> dict:
    return {"ledger_entries": runtime.store.list_ledger_entries(limit=limit)}


@app.post("/api/v1/admin/events")
def admin_submit_event(event: EventRequest, user: dict = Depends(get_admin_user)) -> dict:
    event_data = event.model_dump()
    if not event_data["event_id"]:
        event_data["event_id"] = str(uuid4())
    return runtime.process_event(event_data)


@app.post("/api/v1/admin/natural-language")
def admin_nl(req: NaturalLanguageRequest, user: dict = Depends(get_admin_user)) -> dict:
    interpreted = nl_interpreter.interpret(req.message)
    event_data = {
        "event_id": req.event_id or str(uuid4()),
        "source": req.source,
        "agent_name": interpreted["agent_name"],
        "action": interpreted["action"],
        "payload": interpreted.get("payload", {}),
    }
    result = runtime.process_event(event_data)
    return {"message": req.message, "interpreted_event": event_data, "result": result}


@app.get("/api/v1/admin/users")
def admin_list_users(user: dict = Depends(get_admin_user)) -> dict:
    return {"users": runtime.store.list_users()}


@app.post("/api/v1/admin/users")
def admin_create_user(req: CreateUserRequest, user: dict = Depends(get_admin_user)) -> dict:
    try:
        new_user = runtime.store.create_user(req.username, req.email, req.password, req.role)
        return {"user": new_user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/v1/admin/users/{user_id}")
def admin_delete_user(user_id: str, user: dict = Depends(get_admin_user)) -> dict:
    if user["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")
    runtime.store.delete_user(user_id)
    return {"ok": True}


# ---- Client portal page ----

@app.get("/client", response_class=HTMLResponse)
def client_portal() -> str:
    page = Path(__file__).with_name("client.html")
    if not page.is_file():
        return "<html><body><h1>Portal Cliente</h1><p>En construcción.</p></body></html>"
    return page.read_text(encoding="utf-8")


# ---- Client auth ----

@app.post("/client/login")
def client_login(req: ClientLoginRequest) -> dict:
    client = runtime.store.authenticate_client(req.email, req.password)
    if client is None:
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
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


# ---- Google OAuth ----

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
        return RedirectResponse("/client?connected=1")
    except Exception:
        return RedirectResponse("/client?error=oauth_failed")


@app.get("/client/google/status")
def google_status(client: dict = Depends(get_client_user)) -> dict:
    creds = runtime.store.get_google_creds(client["client_id"])
    return {
        "connected": creds is not None,
        "google_email": creds["google_email"] if creds else None,
        "location_id": creds["location_id"] if creds else None,
        "connected_at": creds["connected_at"] if creds else None,
    }


# ---- Client automations ----

@app.get("/client/automations")
def list_client_automations(client: dict = Depends(get_client_user)) -> dict:
    available = list(json.loads(os.getenv("N8N_TEMPLATE_IDS", "{}")).keys())
    active = runtime.store.list_client_automations(client["client_id"])
    return {"available": available, "active": active}


@app.post("/client/automations/{automation_type}/activate")
def activate_client_automation(
    automation_type: str, client: dict = Depends(get_client_user)
) -> dict:
    templates = json.loads(os.getenv("N8N_TEMPLATE_IDS", "{}"))
    if automation_type not in templates:
        raise HTTPException(status_code=400, detail=f"Tipo de automatización desconocido: {automation_type}")
    creds = runtime.store.get_google_creds(client["client_id"])
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
        raise HTTPException(status_code=503, detail=f"Error al activar en n8n: {exc}")
    record = runtime.store.activate_automation(client["client_id"], automation_type, wf_id)
    return {"status": "active", "workflow_id": wf_id, "automation": record}


@app.delete("/client/automations/{automation_type}")
def deactivate_client_automation(
    automation_type: str, client: dict = Depends(get_client_user)
) -> dict:
    automation = runtime.store.get_automation(client["client_id"], automation_type)
    if automation and automation.get("n8n_workflow_id"):
        try:
            _n8n.delete_workflow(automation["n8n_workflow_id"])
        except Exception:
            pass  # best-effort; n8n may be offline
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
        raise HTTPException(status_code=400, detail=str(e))


# ---- Admin: client management ----

@app.get("/api/v1/admin/clients")
def admin_list_clients(user: dict = Depends(get_admin_user)) -> dict:
    return {"clients": runtime.store.list_clients()}


@app.post("/api/v1/admin/clients")
def admin_create_client(req: ClientRegisterRequest, user: dict = Depends(get_admin_user)) -> dict:
    try:
        client = runtime.store.create_client(req.name, req.email, req.password)
        return {"client": client}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/v1/admin/clients/{client_id}")
def admin_delete_client(client_id: str, user: dict = Depends(get_admin_user)) -> dict:
    runtime.store.delete_client(client_id)
    return {"ok": True}


_zeroman_dir = Path(__file__).parent.parent / "web" / "zeroman"
app.mount("/assets", StaticFiles(directory=str(_zeroman_dir)), name="zeroman-assets")


if __name__ == "__main__":
    import uvicorn

    host = zm_env("INTERFACE_HOST", "0.0.0.0")
    port = int(zm_env("INTERFACE_PORT", "8090"))
    uvicorn.run("apps.interface.api:app", host=host, port=port, reload=False)
