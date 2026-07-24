from __future__ import annotations

from typing import Any

from apps.orchestrator.models import DEFAULT_ENTITY_ID
from apps.orchestrator.store import DataStore


class GovernanceTools:
    def __init__(self, store: DataStore) -> None:
        self.store = store

    def log_compliance_check(
        self,
        event_id: str,
        check_type: str,
        outcome: str,
        details: str = "",
        entity_id: str = DEFAULT_ENTITY_ID,
    ) -> dict[str, Any]:
        check_id = self.store.save_compliance_check(
            event_id=event_id,
            check_type=check_type,
            outcome=outcome,
            details=details,
            entity_id=entity_id,
        )
        return {
            "compliance_check_id": check_id,
            "compliance_status": outcome,
            "controls": "recorded",
            "message": f"Control {check_type}: {outcome}.",
        }
