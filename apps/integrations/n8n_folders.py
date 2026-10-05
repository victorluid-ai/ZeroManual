"""Resolve the n8n folder named exactly Zeromanual (lookup by name, never a hardcoded id)."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

FOLDER_NAME = "Zeromanual"
FOLDER_API_MISSING = (
    "La API de n8n no permite resolver la carpeta «Zeromanual». "
    "Hace falta n8n >= 2.19 con GET/POST /api/v1/projects/{projectId}/folders "
    "y parentFolderId en POST o PUT /api/v1/workflows. "
    "No se crea el workflow fuera de esa carpeta."
)


class N8nFolderResolver:
    """Find or create the Zeromanual folder in the API key's project.

    Behavior: if the folder is missing it is created (only that name, no other
    writes). If the folders API is unavailable the call fails before any
    workflow is created.
    """

    def __init__(self, base_url: str, headers: dict[str, str]) -> None:
        self._base = base_url.rstrip("/")
        self._headers = headers

    def ensure_folder(self) -> str:
        project_id = os.getenv("N8N_PROJECT_ID", "").strip() or self._resolve_project_id()
        found = self._find_folder_id(project_id, FOLDER_NAME)
        if found:
            return found
        return self._create_folder(project_id, FOLDER_NAME)

    def _api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        return httpx.request(
            method,
            f"{self._base}{path}",
            headers=self._headers,
            params=params,
            json=json_body,
            timeout=15,
        )

    def _resolve_project_id(self) -> str:
        projects = self._list_projects()
        personal = [row for row in projects if row.get("type") == "personal" and row.get("id")]
        pool = personal or [row for row in projects if row.get("id")]
        if not pool:
            raise RuntimeError(
                "n8n no devolvió ningún proyecto; no se puede resolver la carpeta Zeromanual."
            )
        return str(pool[0]["id"])

    def _list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(20):
            params: dict[str, Any] | None = {"cursor": cursor} if cursor else None
            response = self._api("GET", "/projects", params=params)
            if response.status_code == 404:
                raise RuntimeError(FOLDER_API_MISSING)
            response.raise_for_status()
            body = response.json()
            if isinstance(body, list):
                return [row for row in body if isinstance(row, dict)]
            rows = []
            if isinstance(body, dict):
                rows = body.get("data")
                if rows is None:
                    rows = body.get("projects") or []
            projects.extend(row for row in rows or [] if isinstance(row, dict))
            cursor = body.get("nextCursor") if isinstance(body, dict) else None
            if not cursor:
                return projects
        return projects

    def _find_folder_id(self, project_id: str, name: str) -> str | None:
        skip = 0
        use_filter = True
        for _ in range(20):
            params: dict[str, Any] = {"skip": skip, "take": 100}
            if use_filter:
                params["filter"] = json.dumps({"name": name})
            response = self._api("GET", f"/projects/{project_id}/folders", params=params)
            if response.status_code == 404:
                raise RuntimeError(FOLDER_API_MISSING)
            if response.status_code == 400 and use_filter:
                use_filter = False
                continue
            response.raise_for_status()
            body = response.json()
            rows = body.get("data") if isinstance(body, dict) else body
            if not isinstance(rows, list):
                rows = []
            for row in rows:
                if isinstance(row, dict) and row.get("name") == name and row.get("id"):
                    return str(row["id"])
            count = body.get("count") if isinstance(body, dict) else None
            if len(rows) < 100 or (count is not None and skip + len(rows) >= int(count)):
                return None
            skip += 100
        return None

    def _create_folder(self, project_id: str, name: str) -> str:
        response = self._api(
            "POST",
            f"/projects/{project_id}/folders",
            json_body={"name": name},
        )
        if response.status_code in (400, 409):
            found = self._find_folder_id(project_id, name)
            if found:
                return found
        if response.status_code == 404:
            raise RuntimeError(FOLDER_API_MISSING)
        response.raise_for_status()
        payload = response.json() if response.content else {}
        folder_id = str((payload or {}).get("id") or "")
        if not folder_id:
            raise RuntimeError("n8n creó la carpeta Zeromanual pero la respuesta no incluye id.")
        return folder_id
