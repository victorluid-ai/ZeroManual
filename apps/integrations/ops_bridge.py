from __future__ import annotations

import logging
from typing import Any

import httpx

from apps.zeromanual_env import zm_env

logger = logging.getLogger(__name__)


class OpsCenterBridge:
    """Fire-and-forget HTTP bridge from ZeroManual commercial → OpsCenter."""

    def __init__(self) -> None:
        self.base_url = zm_env("OPS_URL", "").rstrip("/")
        self.api_key = zm_env("OPS_API_KEY", "")
        self.tenant_id = zm_env("OPS_TENANT_ID", "zeromanual")

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key)

    def emit_event(
        self,
        agent_name: str,
        action: str,
        payload: dict[str, Any],
        source: str = "zeromanual_bridge",
        event_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            logger.debug("OpsCenter bridge disabled (missing OPS_URL/OPS_API_KEY)")
            return None
        body: dict[str, Any] = {
            "agent_name": agent_name,
            "action": action,
            "payload": payload,
            "source": source,
            "tenant_id": self.tenant_id,
        }
        if event_id:
            body["event_id"] = event_id
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
            "X-Tenant-Id": self.tenant_id,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(f"{self.base_url}/api/v1/events", json=body, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("OpsCenter bridge emit failed for %s/%s", agent_name, action)
            return None

    def notify_client_registered(self, client: dict[str, Any]) -> None:
        self.emit_event(
            agent_name="AgentSalesPipeline",
            action="draft_proposal",
            payload={
                "lead_name": client.get("name"),
                "client_name": client.get("name"),
                "client_email": client.get("email"),
                "external_client_id": client.get("client_id"),
                "note": "Alta desde portal ZeroManual",
            },
            source="zeromanual_client_register",
        )

    def notify_automation_activated(
        self, client: dict[str, Any], automation_type: str, workflow_id: str
    ) -> None:
        self.emit_event(
            agent_name="AgentClientDeliveryManager",
            action="client_onboarding",
            payload={
                "client_name": client.get("name"),
                "client_email": client.get("email"),
                "external_client_id": client.get("client_id"),
                "automation_type": automation_type,
                "n8n_workflow_id": workflow_id,
            },
            source="zeromanual_automation_activate",
        )
