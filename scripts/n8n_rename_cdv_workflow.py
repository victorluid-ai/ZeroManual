"""Rename one n8n workflow. Does not delete workflows and does not print secrets.

Renames workflow ``1d0ZyxxIU3cPSlXg`` to ``CDV_Negocio01_<YYYYMMDD>`` using the
calendar date in Europe/Madrid. Refuses the known duplicate workflow ids.

Reads ``N8N_API_URL`` and ``N8N_API_KEY`` from the environment. Does not read
``.env`` and does not touch the ZeroManual database.

    python scripts/n8n_rename_cdv_workflow.py
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

WORKFLOW_ID = "1d0ZyxxIU3cPSlXg"
FORBIDDEN_WORKFLOW_IDS = frozenset({"ePhhOcDT7ew5q74A", "74hUH1G0aTgGBrZT"})
_MADRID = ZoneInfo("Europe/Madrid")


def target_workflow_name(when: datetime | None = None) -> str:
    moment = when or datetime.now(_MADRID)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_MADRID)
    fecha = moment.astimezone(_MADRID).strftime("%Y%m%d")
    return f"CDV_Negocio01_{fecha}"


def assert_workflow_allowed(workflow_id: str) -> None:
    if workflow_id in FORBIDDEN_WORKFLOW_IDS:
        raise SystemExit(f"Ese workflow no se renombra: {workflow_id}")
    if workflow_id != WORKFLOW_ID:
        raise SystemExit(f"Este comando solo renombra {WORKFLOW_ID}")


def rename_workflow(workflow_id: str, name: str) -> None:
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
    payload = {
        "name": name,
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
    print(f"Workflow {workflow_id} renombrado a {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Renombra el workflow CDV de n8n")
    parser.add_argument("--workflow-id", default=WORKFLOW_ID)
    parser.add_argument("--name", default="")
    args = parser.parse_args(argv)
    name = args.name or target_workflow_name()
    rename_workflow(args.workflow_id, name)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        print("No se pudo renombrar el workflow", file=sys.stderr)
        raise SystemExit(1) from None
