from __future__ import annotations

import copy
import os
import uuid
from typing import Any

import httpx


class N8nClient:
    """n8n API + webhook helpers for per-client automation workflows.

    google_reviews template contract (node names):
    - ``Generate AI Draft`` — LLM node whose output is pushed to ZeroManual.
    - ``Post Reply to Google`` (optional) — publishes the approved reply; when present,
      the injected ``Publish Reply Webhook`` is wired into it.
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
    ) -> str:
        """Copy a template workflow, inject client credentials, activate it, and return the new workflow ID.

        ``business_id`` scopes the workflow to a single business/location — required so a
        client with multiple Google Business locations gets one independent workflow (and
        webhook paths) per business instead of colliding on the same paths.
        """
        tpl = self.get_workflow(template_id)
        # The n8n create-workflow API rejects any body field it doesn't recognize
        # (400 "must NOT have additional properties"), so only pass through the
        # fields it actually accepts rather than the full GET /workflows/{id} shape.
        wf_name_suffix = f"{client_id}_{business_id}" if business_id else client_id
        wf = {
            "name": f"{template_id}_{wf_name_suffix}",
            "nodes": copy.deepcopy(tpl.get("nodes", [])),
            "connections": copy.deepcopy(tpl.get("connections", {})),
            "settings": copy.deepcopy(tpl.get("settings", {})),
            "staticData": {
                "refresh_token": refresh_token,
                "location_id": location_id,
                "client_name": client_name,
                "business_id": business_id,
            },
        }
        webhook_suffix = f"{client_id.lower()}-{business_id.lower()}" if business_id else client_id.lower()
        self._uniquify_webhooks(wf, webhook_suffix)
        if automation_type == "google_reviews":
            self._inject_draft_push_node(wf, client_id, automation_type, business_id)
            self._inject_publish_reply_webhook(wf, client_id, business_id)
        created = self.create_workflow(wf)
        wf_id = str(created["id"])
        self.activate_workflow(wf_id)
        return wf_id

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
