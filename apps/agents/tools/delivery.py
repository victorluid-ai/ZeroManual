from __future__ import annotations

from typing import Any

from apps.orchestrator.models import DEFAULT_ENTITY_ID
from apps.orchestrator.store import DataStore


class DeliveryTools:
    def __init__(self, store: DataStore) -> None:
        self.store = store

    def log_delivery_update(
        self,
        event_id: str,
        client_name: str,
        delivery_status: str,
        note: str = "",
        entity_id: str = DEFAULT_ENTITY_ID,
    ) -> dict[str, Any]:
        msg = f"Entrega {delivery_status}"
        if note:
            msg += f" — {note}"
        self.store.upsert_client_memory(client_name, msg, entity_id=entity_id)
        return {
            "client_name": client_name,
            "delivery_status": delivery_status,
            "workflow_sync": "completed",
            "message": f"Plan de entrega actualizado para {client_name}.",
        }
