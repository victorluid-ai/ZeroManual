"""Rename one n8n workflow. Does not delete workflows and does not print secrets.

Renames workflow ``1d0ZyxxIU3cPSlXg`` to ``CDV_Negocio01_<YYYYMMDD>``.
The date is ``client_automations.activated_at`` for that workflow id, read
only. If that value is missing, the date is the workflow ``createdAt`` from
n8n, converted to Europe/Madrid. It is not the day the rename runs.

Reads ``N8N_API_URL`` and ``N8N_API_KEY`` from the environment. Does not read
``.env`` and does not write the database.

    python scripts/n8n_rename_cdv_workflow.py
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import httpx

from apps.integrations.n8n_client import activation_calendar_date

WORKFLOW_ID = "1d0ZyxxIU3cPSlXg"
FORBIDDEN_WORKFLOW_IDS = frozenset({"ePhhOcDT7ew5q74A", "74hUH1G0aTgGBrZT"})


def _resolve_db_path(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    for key in ("ZEROMANUAL_DB_PATH", "MANUALZERO_DB_PATH"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return "runtime/zeromanual.db"


def lookup_activated_at(workflow_id: str, db_path: str | None = None) -> str | None:
    """Read ``activated_at`` for ``workflow_id``. Does not create or write the database."""
    path = _resolve_db_path(db_path)
    if not path or not os.path.isfile(path):
        return None
    uri = f"{Path(path).resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            """
            SELECT activated_at FROM client_automations
            WHERE n8n_workflow_id = ?
              AND activated_at IS NOT NULL
              AND TRIM(activated_at) != ''
            ORDER BY activated_at DESC
            LIMIT 1
            """,
            (workflow_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not row or row[0] is None:
        return None
    return str(row[0])


def target_workflow_name(
    when: datetime | str | None = None,
    *,
    activated_at: datetime | str | None = None,
    created_at: datetime | str | None = None,
) -> str:
    chosen = activated_at if activated_at is not None else when
    fecha = activation_calendar_date(chosen, created_at)
    return f"CDV_Negocio01_{fecha}"


def assert_workflow_allowed(workflow_id: str) -> None:
    if workflow_id in FORBIDDEN_WORKFLOW_IDS:
        raise SystemExit(f"Ese workflow no se renombra: {workflow_id}")
    if workflow_id != WORKFLOW_ID:
        raise SystemExit(f"Este comando solo renombra {WORKFLOW_ID}")


def rename_workflow(workflow_id: str, name: str, db_path: str | None = None) -> None:
    assert_workflow_allowed(workflow_id)
    base = os.environ.get("N8N_API_URL", "").rstrip("/")
    api_key = os.environ.get("N8N_API_KEY", "")
    if not base or not api_key:
        raise SystemExit("Faltan N8N_API_URL o N8N_API_KEY en el entorno")
    headers = {"X-N8N-API-KEY": api_key, "Content-Type": "application/json"}
    got = httpx.get(f"{base}/workflows/{workflow_id}", headers=headers, timeout=20)
    if got.status_code >= 400:
        raise SystemExit(f"n8n respondió HTTP {got.status_code} al leer el workflow")
    current = got.json()
    resolved = name or target_workflow_name(
        activated_at=lookup_activated_at(workflow_id, db_path),
        created_at=current.get("createdAt") or current.get("created_at"),
    )
    payload = {
        "name": resolved,
        "nodes": current.get("nodes") or [],
        "connections": current.get("connections") or {},
        "settings": current.get("settings") or {},
        "staticData": current.get("staticData") or {},
    }
    put = httpx.put(
        f"{base}/workflows/{workflow_id}",
        headers=headers,
        json=payload,
        timeout=20,
    )
    if put.status_code >= 400:
        raise SystemExit(f"n8n respondió HTTP {put.status_code} al renombrar el workflow")
    print(f"Workflow {workflow_id} renombrado a {resolved}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Renombra el workflow CDV de n8n")
    parser.add_argument("--workflow-id", default=WORKFLOW_ID)
    parser.add_argument("--name", default="")
    args = parser.parse_args(argv)
    rename_workflow(args.workflow_id, args.name)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        print("No se pudo renombrar el workflow", file=sys.stderr)
        raise SystemExit(1) from None
