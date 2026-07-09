from __future__ import annotations

import copy
import os

import httpx


class N8nClient:
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

    def duplicate_template(
        self,
        template_id: str,
        client_id: str,
        client_name: str,
        refresh_token: str,
        location_id: str | None,
    ) -> str:
        """Copy a template workflow, inject client credentials, activate it, and return the new workflow ID."""
        tpl = self.get_workflow(template_id)
        wf = copy.deepcopy(tpl)
        for key in ("id", "createdAt", "updatedAt", "active"):
            wf.pop(key, None)
        wf["name"] = f"{template_id}_{client_id}"
        wf.setdefault("settings", {})["staticData"] = {
            "refresh_token": refresh_token,
            "location_id": location_id,
            "client_name": client_name,
        }
        created = self.create_workflow(wf)
        wf_id = str(created["id"])
        self.activate_workflow(wf_id)
        return wf_id
