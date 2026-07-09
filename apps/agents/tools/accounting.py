from __future__ import annotations

from typing import Any

from apps.orchestrator.store import DataStore


class AccountingTools:
    def __init__(self, store: DataStore) -> None:
        self.store = store

    def classify_ledger_entry(
        self,
        event_id: str,
        client_name: str | None,
        amount_eur: float | None,
        invoice_id: str | None = None,
        category: str = "ingreso_servicios",
    ) -> dict[str, Any]:
        entry_id = self.store.save_ledger_entry(
            event_id=event_id,
            client_name=client_name,
            amount_eur=amount_eur,
            category=category,
            reference=invoice_id,
            status="classified",
        )
        if client_name:
            note = f"Asiento {entry_id} clasificado ({category})"
            if invoice_id:
                note += f" ref {invoice_id}"
            self.store.upsert_client_memory(client_name, note)
        return {
            "ledger_entry_id": entry_id,
            "ledger_status": "classified",
            "category": category,
            "message": "Movimiento contable clasificado y encolado para cierre mensual.",
        }

    def record_vat_draft(
        self,
        event_id: str,
        period: str,
        amount_eur: float | None = None,
    ) -> dict[str, Any]:
        entry_id = self.store.save_ledger_entry(
            event_id=event_id,
            client_name=None,
            amount_eur=amount_eur,
            category="iva_borrador",
            reference=period,
            status="vat_draft",
        )
        return {
            "ledger_entry_id": entry_id,
            "vat_status": "draft",
            "period": period,
            "message": f"Borrador IVA {period} registrado (requiere revision humana).",
        }
