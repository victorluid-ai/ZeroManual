from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, audit_path: str = "runtime/audit-log.jsonl") -> None:
        self._path = Path(audit_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, agent_name: str, event_id: str, status: str, details: dict[str, Any]) -> None:
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "agent_name": agent_name,
            "event_id": event_id,
            "status": status,
            "details": details,
        }
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=True) + "\n")
