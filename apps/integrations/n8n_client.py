from __future__ import annotations

import copy
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from apps.integrations.google_business import require_gbp_location_id
from apps.integrations.n8n_folders import N8nFolderResolver

_MADRID = ZoneInfo("Europe/Madrid")
_NAME_MAX = 128


def sanitize_workflow_name_part(value: str | None, fallback: str) -> str:
    """Keep Unicode letters and digits. Drop spaces and symbols."""
    kept = "".join(ch for ch in (value or "") if ch.isalnum())
    return kept or fallback


def negocio_segment(ordinal: int) -> str:
    """Stable label: Negocio01, Negocio02, … Never a street or brand name."""
    number = ordinal if ordinal and ordinal > 0 else 1
    return f"Negocio{number:02d}"


def negocio_ordinal(businesses: list[dict[str, Any]] | None, business_id: str | None) -> int:
    """1-based index of ``business_id`` among the client's businesses.

    Sort is ``created_at`` then ``business_id``. A client with zero or one
    business always gets 1 (``Negocio01``), even when the display name is a street.
    The same business_id keeps its index while the set of rows does not lose an
    earlier sibling. Deleting an older business can renumber the rest on the
    next activation.
    """
    ordered = sorted(
        businesses or [],
        key=lambda row: (str(row.get("created_at") or ""), str(row.get("business_id") or "")),
    )
    if len(ordered) <= 1:
        return 1
    for index, row in enumerate(ordered, start=1):
        if business_id and row.get("business_id") == business_id:
            return index
    return len(ordered) + 1


def build_client_workflow_name(
    client_name: str,
    *,
    ordinal: int = 1,
    activated_at: datetime | None = None,
) -> str:
    """``NombreCliente_NegocioNN_YYYYMMDD`` in Europe/Madrid."""
    cliente = sanitize_workflow_name_part(client_name, "Cliente")
    segment = negocio_segment(ordinal)
    when = activated_at or datetime.now(_MADRID)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    fecha = when.astimezone(_MADRID).strftime("%Y%m%d")
    suffix = f"_{segment}_{fecha}"
    if len(cliente) + len(suffix) > _NAME_MAX:
        cliente = cliente[: _NAME_MAX - len(suffix)] or "Cliente"
    return f"{cliente}{suffix}"


def client_static_data(
    *,
    refresh_token: str,
    location_id: str | None,
    client_name: str,
    business_id: str | None,
) -> dict[str, Any]:
    """Flat keys plus a ``global`` mirror.

    n8n's ``$getWorkflowStaticData('global')`` reads ``staticData.global`` only.
    ``$workflow`` in HTTP expressions exposes id/name/active, not staticData.
    """
    payload = {
        "refresh_token": refresh_token,
        "location_id": location_id,
        "client_name": client_name,
        "business_id": business_id,
    }
    return {**payload, "global": dict(payload)}


def _body_rejects_parent_folder(text: str) -> bool:
    lowered = (text or "").lower()
    return "parentfolderid" in lowered or "additional propert" in lowered


class N8nClient:
    """n8n API + webhook helpers for per-client automation workflows.

    google_reviews template contract (node names):
    - ``Generate AI Draft`` — LLM node whose output is pushed to ZeroManual.
    - ``Post Reply to Google`` (optional) — publishes the approved reply; when present,
      the injected ``Publish Reply Webhook`` is wired into it.

    New copies are named ``Cliente_NegocioNN_YYYYMMDD`` and placed in the folder
    ``Zeromanual``.
    """

    def __init__(self) -> None:
        self._base = os.getenv("N8N_API_URL", "http://localhost:5678/api/v1")
        self._headers = {
            "X-N8N-API-KEY": os.getenv("N8N_API_KEY", ""),
            "Content-Type": "application/json",
        }

    def get_workflow(self, workflow_id: str) -> dict:
        r = httpx.get(
            f"{self._base}/workflows/{workflow_id}",
            headers=self._headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def create_workflow(self, workflow_def: dict) -> dict:
        r = httpx.post(
            f"{self._base}/workflows",
            headers=self._headers,
            json=workflow_def,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def activate_workflow(self, workflow_id: str) -> None:
        r = httpx.post(
            f"{self._base}/workflows/{workflow_id}/activate",
            headers=self._headers,
            timeout=10,
        )
        r.raise_for_status()

    def delete_workflow(self, workflow_id: str) -> None:
        r = httpx.delete(
            f"{self._base}/workflows/{workflow_id}",
            headers=self._headers,
            timeout=10,
        )
        if r.status_code != 404:
            r.raise_for_status()

    @staticmethod
    def publish_reply_path(client_id: str, business_id: str) -> str:
        return f"publish-reply-{client_id.lower()}-{business_id.lower()}"

    def duplicate_template(
        self,
        template_id: str,
        client_id: str,
        client_name: str,
        refresh_token: str,
        location_id: str | None,
        automation_type: str | None = None,
        business_id: str | None = None,
        business_ordinal: int | None = None,
        activated_at: datetime | None = None,
    ) -> str:
        """Copy a template workflow, inject client credentials, activate it, and return the new workflow ID.

        ``business_id`` scopes the workflow to a single business/location — required so a
        client with multiple Google Business locations gets one independent workflow (and
        webhook paths) per business instead of colliding on the same paths.

        ``business_ordinal`` selects the NegocioNN segment (1 → Negocio01). A missing
        ordinal is treated as 1. The calendar date is Europe/Madrid.
        """
        if automation_type == "google_reviews":
            location_id = require_gbp_location_id(location_id)
        folder_id = self.ensure_client_folder()
        tpl = self.get_workflow(template_id)
        # The n8n create-workflow API rejects any body field it doesn't recognize
        # (400 "must NOT have additional properties"), so only pass through the
        # fields it actually accepts rather than the full GET /workflows/{id} shape.
        ordinal = 1 if not business_ordinal or business_ordinal < 1 else business_ordinal
        wf = {
            "name": build_client_workflow_name(
                client_name, ordinal=ordinal, activated_at=activated_at
            ),
            "nodes": copy.deepcopy(tpl.get("nodes", [])),
            "connections": copy.deepcopy(tpl.get("connections", {})),
            "settings": copy.deepcopy(tpl.get("settings", {})),
            "staticData": client_static_data(
                refresh_token=refresh_token,
                location_id=location_id,
                client_name=client_name,
                business_id=business_id,
            ),
        }
        webhook_suffix = f"{client_id.lower()}-{business_id.lower()}" if business_id else client_id.lower()
        self._uniquify_webhooks(wf, webhook_suffix)
        if automation_type == "google_reviews":
            self._inject_draft_push_node(wf, client_id, automation_type, business_id)
            self._inject_publish_reply_webhook(wf, client_id, business_id)
        created = self._submit_workflow(wf, folder_id)
        wf_id = str(created["id"])
        self.activate_workflow(wf_id)
        return wf_id

    def ensure_client_folder(self) -> str:
        """Return the id of the n8n folder named exactly Zeromanual."""
        return N8nFolderResolver(self._base, self._headers).ensure_folder()

    def _submit_workflow(self, wf: dict, folder_id: str) -> dict:
        """Create the workflow inside ``folder_id``.

        Prefer ``parentFolderId`` on POST. If this n8n rejects that field, create
        at the project root and PUT the same body with ``parentFolderId``. A failed
        move deletes the copy so it is not left outside Zeromanual.
        """
        payload = dict(wf)
        payload["parentFolderId"] = folder_id
        response = httpx.post(
            f"{self._base}/workflows",
            headers=self._headers,
            json=payload,
            timeout=15,
        )
        if response.status_code == 400 and _body_rejects_parent_folder(response.text):
            created = self.create_workflow(wf)
            wf_id = str(created["id"])
            if not self._move_workflow_to_folder(wf_id, wf, folder_id):
                self.delete_workflow(wf_id)
                raise RuntimeError(
                    "n8n rechazó mover el workflow a la carpeta Zeromanual; se eliminó la copia."
                )
            return created
        response.raise_for_status()
        return response.json()

    def _move_workflow_to_folder(self, workflow_id: str, wf: dict, folder_id: str) -> bool:
        body = {
            "name": wf.get("name"),
            "nodes": wf.get("nodes") or [],
            "connections": wf.get("connections") or {},
            "settings": wf.get("settings") or {},
            "staticData": wf.get("staticData") or {},
            "parentFolderId": folder_id,
        }
        response = httpx.put(
            f"{self._base}/workflows/{workflow_id}",
            headers=self._headers,
            json=body,
            timeout=15,
        )
        return response.is_success

    def trigger_publish_reply(
        self, client_id: str, business_id: str, payload: dict[str, Any]
    ) -> None:
        """POST approved/auto reply to the client+business's publish-reply webhook in n8n."""
        base = os.getenv("N8N_WEBHOOK_BASE_URL", "http://localhost:5678/webhook").rstrip("/")
        url = f"{base}/{self.publish_reply_path(client_id, business_id)}"
        r = httpx.post(url, json=payload, timeout=30)
        r.raise_for_status()

    def _uniquify_webhooks(self, wf: dict, suffix: str) -> None:
        """n8n requires webhook paths/ids to be unique across active workflows. The template's
        webhook node(s) use a fixed path, so activating a second client's duplicate conflicts
        with the first ('There is a conflict with one of the webhooks.'). Give each client's
        copy its own path and a fresh webhookId."""
        for node in wf.get("nodes", []):
            if node.get("type") != "n8n-nodes-base.webhook":
                continue
            params = node.setdefault("parameters", {})
            base_path = params.get("path", "webhook")
            params["path"] = f"{base_path}-{suffix}"
            node["webhookId"] = str(uuid.uuid4())

    def _inject_draft_push_node(
        self, wf: dict, client_id: str, automation_type: str, business_id: str | None
    ) -> None:
        """Add a node that POSTs the AI-generated draft to ZeroManual after 'Generate AI Draft',
        so the client can review/approve it from the client portal instead of only by email."""
        nodes = wf.get("nodes", [])
        if not any(n.get("name") == "Generate AI Draft" for n in nodes):
            return
        public_url = os.getenv("ZEROMANUAL_PUBLIC_URL", "http://localhost:8090").rstrip("/")
        cred_id = os.getenv("N8N_WEBHOOK_CRED_ID", "")
        push_node: dict = {
            "id": "node-push-zeromanual-draft",
            "name": "Push Draft to ZeroManual",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1104, 480],
            "parameters": {
                "method": "POST",
                "url": f"{public_url}/internal/automations/{automation_type}/drafts",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": (
                    "={{ JSON.stringify({"
                    f"client_id: {client_id!r}, "
                    f"business_id: {business_id!r}, "
                    "review_id: $json.review_name, "
                    "reviewer_name: $json.reviewer_name, "
                    "rating: $json.starRating, "
                    "source_text: $json.review_text, "
                    "suggested_reply: ($json.message && $json.message.content) "
                    "|| ($json.choices && $json.choices[0] && $json.choices[0].message.content) || ''"
                    "}) }}"
                ),
                "options": {},
            },
        }
        if cred_id:
            push_node["parameters"]["authentication"] = "genericCredentialType"
            push_node["parameters"]["genericAuthType"] = "httpHeaderAuth"
            push_node["credentials"] = {
                "httpHeaderAuth": {"id": cred_id, "name": "ZeroManual Webhook Secret"}
            }
        nodes.append(push_node)
        wf["nodes"] = nodes
        conns = wf.setdefault("connections", {})
        gen_conn = conns.setdefault("Generate AI Draft", {"main": [[]]})
        gen_conn["main"][0].append({"index": 0, "node": "Push Draft to ZeroManual", "type": "main"})

    def _inject_publish_reply_webhook(
        self, wf: dict, client_id: str, business_id: str | None
    ) -> None:
        """Inject a webhook ZeroManual calls after approval / auto-send to publish on Google.

        Expected downstream node name: ``Post Reply to Google``. If missing, the webhook
        is still added so the path exists; the template owner must wire it.
        """
        nodes = wf.get("nodes", [])
        if any(n.get("name") == "Publish Reply Webhook" for n in nodes):
            return
        path = self.publish_reply_path(client_id, business_id or "default")
        webhook: dict = {
            "id": "node-publish-reply-webhook",
            "name": "Publish Reply Webhook",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [400, 700],
            "webhookId": str(uuid.uuid4()),
            "parameters": {
                "httpMethod": "POST",
                "path": path,
                "responseMode": "onReceived",
                "options": {},
            },
        }
        nodes.append(webhook)
        wf["nodes"] = nodes
        post_name = "Post Reply to Google"
        if any(n.get("name") == post_name for n in nodes):
            conns = wf.setdefault("connections", {})
            wh_conn = conns.setdefault("Publish Reply Webhook", {"main": [[]]})
            wh_conn["main"][0].append({"index": 0, "node": post_name, "type": "main"})
