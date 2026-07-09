from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.integrations.settings import CompanySettings


class AccountingExporter:
    """Export CSV borrador para asesoria / importacion contable (Espana)."""

    HEADERS = [
        "fecha",
        "tipo_documento",
        "numero_factura",
        "referencia_interna",
        "cliente",
        "nif_cliente",
        "concepto",
        "base_imponible",
        "tipo_iva_pct",
        "cuota_iva",
        "total",
        "estado",
        "categoria_asiento",
        "referencia_asiento",
    ]

    def __init__(self, company: CompanySettings, output_dir: str) -> None:
        self.company = company
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_csv(
        self,
        invoices: list[dict[str, Any]],
        ledger_entries: list[dict[str, Any]],
    ) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"contabilidad_zeromanual_{stamp}.csv"

        rows: list[dict[str, str]] = []

        for inv in invoices:
            base = inv.get("base_amount_eur")
            vat = inv.get("vat_amount_eur")
            total = inv.get("total_eur") or inv.get("amount_eur")
            rows.append(
                {
                    "fecha": str(inv.get("created_at", ""))[:10],
                    "tipo_documento": "factura_emitida",
                    "numero_factura": str(inv.get("invoice_number") or ""),
                    "referencia_interna": str(inv.get("invoice_id") or ""),
                    "cliente": str(inv.get("client_name") or ""),
                    "nif_cliente": str(inv.get("client_nif") or ""),
                    "concepto": "Ingreso por servicios",
                    "base_imponible": f"{base:.2f}" if base is not None else "",
                    "tipo_iva_pct": str(inv.get("vat_rate") or self.company.default_vat_rate),
                    "cuota_iva": f"{vat:.2f}" if vat is not None else "",
                    "total": f"{total:.2f}" if total is not None else "",
                    "estado": str(inv.get("status") or ""),
                    "categoria_asiento": "",
                    "referencia_asiento": "",
                }
            )

        for entry in ledger_entries:
            amount = entry.get("amount_eur")
            rows.append(
                {
                    "fecha": str(entry.get("created_at", ""))[:10],
                    "tipo_documento": "asiento",
                    "numero_factura": str(entry.get("reference") or ""),
                    "referencia_interna": str(entry.get("entry_id") or ""),
                    "cliente": str(entry.get("client_name") or ""),
                    "nif_cliente": "",
                    "concepto": str(entry.get("category") or ""),
                    "base_imponible": "",
                    "tipo_iva_pct": "",
                    "cuota_iva": "",
                    "total": f"{amount:.2f}" if amount is not None else "",
                    "estado": str(entry.get("status") or ""),
                    "categoria_asiento": str(entry.get("category") or ""),
                    "referencia_asiento": str(entry.get("entry_id") or ""),
                }
            )

        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.HEADERS, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

        return path
