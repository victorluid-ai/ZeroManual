from __future__ import annotations

import json
from typing import Any

from apps.orchestrator.runtime import OrchestratorRuntime

_runtime = OrchestratorRuntime()

def process_event(raw_event: dict[str, Any]) -> dict[str, Any]:
    return _runtime.process_event(raw_event)


if __name__ == "__main__":
    sample_event = {
        "event_id": "evt-001",
        "source": "api",
        "agent_name": "AgentBillingOps",
        "action": "create_invoice",
        "payload": {"amount_eur": 250.0},
    }
    print(json.dumps(process_event(sample_event), indent=2))
