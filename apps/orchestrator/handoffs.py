from __future__ import annotations

from typing import Any
from uuid import uuid4

from apps.orchestrator.models import Event, ExecutionStatus


def build_handoff_events(
    source_event: Event,
    output: dict[str, Any],
    status: ExecutionStatus,
) -> list[dict[str, Any]]:
    if status != ExecutionStatus.COMPLETED:
        return []

    handoffs: list[dict[str, Any]] = []

    if (
        source_event.agent_name == "AgentBillingOps"
        and source_event.action == "create_invoice"
        and output.get("invoice_id")
    ):
        client = source_event.payload.get("client_name") or source_event.payload.get("client")
        amount = source_event.payload.get("amount_eur")
        handoffs.append(
            {
                "event_id": str(uuid4()),
                "source": "agent_handoff",
                "agent_name": "AgentAccountingAssistantES",
                "action": "classify_transaction",
                "payload": {
                    "client_name": client,
                    "amount_eur": amount,
                    "invoice_id": output.get("invoice_id"),
                    "parent_event_id": source_event.event_id,
                },
            }
        )

    if source_event.agent_name == "AgentSalesPipeline" and source_event.action == "draft_proposal":
        lead = (
            source_event.payload.get("lead_name")
            or source_event.payload.get("client_name")
            or source_event.payload.get("client")
        )
        if lead:
            handoffs.append(
                {
                    "event_id": str(uuid4()),
                    "source": "agent_handoff",
                    "agent_name": "AgentClientDeliveryManager",
                    "action": "client_onboarding",
                    "payload": {
                        "client_name": lead,
                        "parent_event_id": source_event.event_id,
                    },
                }
            )

    return handoffs
