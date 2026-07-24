from __future__ import annotations

from typing import Any

from apps.orchestrator.models import DEFAULT_ENTITY_ID
from apps.orchestrator.store import DataStore


class SalesTools:
    def __init__(self, store: DataStore) -> None:
        self.store = store

    def update_lead(
        self,
        event_id: str,
        lead_name: str,
        stage: str,
        deal_value_eur: float | None = None,
        entity_id: str = DEFAULT_ENTITY_ID,
    ) -> dict[str, Any]:
        notes = f"Lead {lead_name}: etapa {stage}"
        if deal_value_eur is not None:
            notes += f" ({deal_value_eur} EUR)"
        self.store.upsert_client_memory(lead_name, notes, entity_id=entity_id)
        return {
            "lead_name": lead_name,
            "lead_status": stage,
            "deal_value_eur": str(deal_value_eur) if deal_value_eur is not None else "",
            "message": f"Lead {lead_name} actualizado a {stage}.",
        }
