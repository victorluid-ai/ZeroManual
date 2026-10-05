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
    client_id: str | None = None,
) -> dict[str, Any]:
    """Flat keys plus a ``global`` mirror.

    n8n's ``$getWorkflowStaticData('global')`` reads ``staticData.global`` only.
    ``$workflow`` in HTTP expressions exposes id/name/active, not staticData.

    ``client_id`` is not a secret. The baked ``Build Draft Payload`` node reads
    it from ``staticData.global`` so the portal POST works without rewriting the
    template body on every copy.
    """
    payload = {
        "refresh_token": refresh_token,
        "location_id": location_id,
        "client_name": client_name,
        "business_id": business_id,
        "client_id": client_id,
    }
    return {**payload, "global": dict(payload)}


def _body_rejects_parent_folder(text: str) -> bool:
    lowered = (text or "").lower()
    return "parentfolderid" in lowered or "additional propert" in lowered


class N8nClient:
    """n8n API + webhook helpers for per-client automation workflows.

    google_reviews template contract (node names):
    - ``Generate AI Draft`` — shapes the review plus the model reply.
    - ``Push Draft to ZeroManual`` — POSTs that draft to the portal. Baked into
      the template after ``Build Draft Payload``. Injection adds it only when
      the copy does not already have the node.
    - ``Publish Reply Webhook`` — inbound path ``publish-reply``. On each client
      copy the path becomes ``publish-reply-{client}-{business}``, which is
      what ``trigger_publish_reply`` calls. Wired to ``Post Reply to Google``.
    - ``Post Reply to Google`` — publishes the approved reply inside n8n.
      ZeroManual does not call the Google API itself.

    New copies are named ``Cliente_NegocioNN_YYYYMMDD`` and placed in the folder
    ``Zeromanual`` when the projects/folders API allows it. A 401, 403, or 404
    on that API skips the folder and still clones the workflow.
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
                client_id=client_id,
            ),
        }
        webhook_suffix = f"{client_id.lower()}-{business_id.lower()}" if business_id else client_id.lower()
        self._uniquify_webhooks(wf, webhook_suffix)
        if automation_type == "google_reviews":
            self._inject_draft_push_node(wf, client_id, automation_type, business_id)
            self._inject_publish_reply_webhook(wf, client_id, business_id)
        created = self._submit_workflow(wf, folder_id) if folder_id else self.create_workflow(wf)
        wf_id = str(created["id"])
        self.activate_workflow(wf_id)
        return wf_id

    def ensure_client_folder(self) -> str | None:
        """Return the Zeromanual folder id, or None when placement is skipped.

        401, 403, and 404 from the n8n projects or folders API are logged by
        the resolver and do not abort activation.
        """
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

    def _append_main_edge(self, wf: dict, source: str, target: str) -> None:
        conns = wf.setdefault("connections", {})
        source_conn = conns.setdefault(source, {"main": [[]]})
        main = source_conn.setdefault("main", [[]])
        if not main:
            main.append([])
        branch = main[0] if main[0] is not None else []
        main[0] = branch
        if any(isinstance(edge, dict) and edge.get("node") == target for edge in branch):
            return
        branch.append({"index": 0, "node": target, "type": "main"})

    def _ensure_push_auth(self, node: dict) -> None:
        """Attach the n8n header credential when configured.

        The template sends ``X-Webhook-Secret`` from ``$env.ZEROMANUAL_WEBHOOK_SECRET``
        so a copy works without embedding the secret. If ``N8N_WEBHOOK_CRED_ID`` is
        set, that credential replaces the env header so the two do not collide.
        """
        cred_id = os.getenv("N8N_WEBHOOK_CRED_ID", "")
        if not cred_id:
            return
        params = node.setdefault("parameters", {})
        params["authentication"] = "genericCredentialType"
        params["genericAuthType"] = "httpHeaderAuth"
        node["credentials"] = {
            "httpHeaderAuth": {"id": cred_id, "name": "ZeroManual Webhook Secret"}
        }
        header_block = params.get("headerParameters") or {}
        headers = [
            header
            for header in (header_block.get("parameters") or [])
            if header.get("name") != "X-Webhook-Secret"
        ]
        if headers:
            params["headerParameters"] = {"parameters": headers}
            params["sendHeaders"] = True
        else:
            params.pop("headerParameters", None)
            params["sendHeaders"] = False

    def _inject_draft_push_node(
        self, wf: dict, client_id: str, automation_type: str, business_id: str | None
    ) -> None:
        """POST the AI draft to ZeroManual after 'Generate AI Draft'.

        The shipped template already contains ``Push Draft to ZeroManual``.
        Adding another node would POST the same review twice, so this only
        fills the node in for older graphs and attaches header auth.
        """
        nodes = wf.get("nodes", [])
        if not any(n.get("name") == "Generate AI Draft" for n in nodes):
            return
        existing = next((n for n in nodes if n.get("name") == "Push Draft to ZeroManual"), None)
        if existing is not None:
            self._ensure_push_auth(existing)
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
        self._append_main_edge(wf, "Generate AI Draft", "Push Draft to ZeroManual")

    def _inject_publish_reply_webhook(
        self, wf: dict, client_id: str, business_id: str | None
    ) -> None:
        """Webhook ZeroManual calls after approval / auto-send.

        The template bakes ``Publish Reply Webhook`` → ``Post Reply to Google``.
        ``_uniquify_webhooks`` turns the path ``publish-reply`` into
        ``publish-reply-{client}-{business}`` before this runs. If the node is
        already present, only the downstream edge is repaired.
        """
        nodes = wf.get("nodes", [])
        post_name = "Post Reply to Google"
        if any(n.get("name") == "Publish Reply Webhook" for n in nodes):
            if any(n.get("name") == post_name for n in nodes):
                self._append_main_edge(wf, "Publish Reply Webhook", post_name)
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
        if any(n.get("name") == post_name for n in nodes):
            self._append_main_edge(wf, "Publish Reply Webhook", post_name)
