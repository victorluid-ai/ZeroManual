from __future__ import annotations

import re
from typing import Any

from apps.integrations.invoice_pdf import InvoicePDFGenerator
from apps.integrations.settings import load_integration_settings
from apps.integrations.smtp_client import SmtpClient
from apps.orchestrator.store import DataStore

VALID_VAT_RATES: frozenset[float] = frozenset({0.0, 4.0, 10.0, 21.0})

_NIF_DNI = re.compile(r"^\d{8}[A-Z]$")
_NIF_CIF = re.compile(r"^[A-HJNPQRSUVW]\d{7}[0-9A-J]$")
_NIF_NIE = re.compile(r"^[XYZ]\d{7}[A-Z]$")


def _is_valid_nif(nif: str) -> bool:
    n = nif.strip().upper()
    return bool(_NIF_DNI.match(n) or _NIF_CIF.match(n) or _NIF_NIE.match(n))


class BillingTools:
    def __init__(self, store: DataStore) -> None:
        self.store = store
        self._settings = load_integration_settings()
        self._pdf = InvoicePDFGenerator(
            self._settings.company,
            self._settings.invoices_dir,
        )
        self._smtp = SmtpClient(self._settings.smtp)

    def create_invoice_draft(
        self,
        event_id: str,
        client_name: str,
        amount_eur: float | None,
        approved_by: str | None = None,
        client_email: str | None = None,
        client_nif: str | None = None,
        concept: str | None = None,
        vat_rate: float | None = None,
    ) -> dict[str, Any]:
        if client_nif and not _is_valid_nif(client_nif):
            return {
                "error": (
                    f"NIF/CIF no valido: '{client_nif}'. "
                    "Formatos aceptados: DNI (12345678A), CIF (B1234567X), NIE (X1234567A)."
                )
            }
        effective_vat_rate = vat_rate if vat_rate is not None else self._settings.company.default_vat_rate
        if effective_vat_rate not in VALID_VAT_RATES:
            return {
                "error": (
                    f"Tipo de IVA no valido: {effective_vat_rate}%. "
                    f"Valores permitidos segun RD 1619/2012: {sorted(VALID_VAT_RATES)}"
                )
            }
        invoice_id = f"INV-{event_id[:8].upper()}"
        invoice_number = self.store.next_invoice_number()
        amounts = InvoicePDFGenerator.compute_amounts(amount_eur, effective_vat_rate)

        pdf_path = self._pdf.generate(
            invoice_id=invoice_id,
            invoice_number=invoice_number,
            client_name=client_name,
            base_amount_eur=amounts["base"],
            vat_rate=effective_vat_rate,
            vat_amount_eur=amounts["vat"],
            total_eur=amounts["total"],
            client_nif=client_nif or "",
            concept=concept or "Servicios de automatizacion digital",
        )

        self.store.save_invoice(
            invoice_id=invoice_id,
            event_id=event_id,
            client_name=client_name,
            amount_eur=amount_eur,
            status="issued",
            approved_by=approved_by,
            invoice_number=invoice_number,
            pdf_path=str(pdf_path),
            client_email=client_email,
            client_nif=client_nif,
            base_amount_eur=amounts["base"],
            vat_rate=effective_vat_rate,
            vat_amount_eur=amounts["vat"],
            total_eur=amounts["total"],
        )

        if client_name:
            notes = f"Ultima factura {invoice_number} ({invoice_id})"
            if amount_eur is not None:
                notes += f" por {amount_eur} EUR"
            self.store.upsert_client_memory(client_name, notes)

        result: dict[str, Any] = {
            "invoice_id": invoice_id,
            "invoice_number": invoice_number,
            "status": "issued",
            "client_name": client_name,
            "amount_eur": str(amount_eur) if amount_eur is not None else "",
            "pdf_path": str(pdf_path),
            "message": f"Factura {invoice_number} emitida para {client_name}.",
        }

        email = client_email
        if email and self._settings.smtp.auto_send_on_issue:
            send_result = self.send_invoice_email(
                invoice_id=invoice_id,
                to_email=email,
            )
            result["email"] = send_result

        return result

    def send_invoice_email(
        self,
        invoice_id: str,
        to_email: str | None = None,
    ) -> dict[str, Any]:
        invoice = self.store.get_invoice(invoice_id)
        if invoice is None:
            return {"error": f"Factura no encontrada: {invoice_id}"}

        recipient = to_email or invoice.get("client_email")
        if not recipient:
            return {
                "status": "skipped",
                "message": "Sin email de cliente (client_email en payload o factura).",
            }

        pdf_path_str = invoice.get("pdf_path")
        if not pdf_path_str:
            return {"error": "La factura no tiene PDF generado."}

        from pathlib import Path

        pdf_path = Path(pdf_path_str)
        invoice_number = str(invoice.get("invoice_number") or invoice_id)
        client_name = str(invoice.get("client_name") or "cliente")
        total = invoice.get("total_eur") or invoice.get("amount_eur")

        subject = f"Factura {invoice_number} — {self._settings.company.name}"
        body = (
            f"Hola {client_name},\n\n"
            f"Adjuntamos la factura {invoice_number}"
            f"{f' por un importe de {total:.2f} EUR' if total is not None else ''}.\n\n"
            f"Saludos,\n{self._settings.company.name}"
        )

        result = self._smtp.send_invoice(
            to_email=recipient,
            subject=subject,
            body=body,
            pdf_path=pdf_path,
            invoice_number=invoice_number,
        )
        if result.get("status") == "sent":
            self.store.mark_invoice_email_sent(invoice_id)
        return result

    def mark_invoice_paid(self, invoice_id: str) -> dict[str, Any]:
        invoice = self.store.get_invoice(invoice_id)
        if invoice is None:
            return {"error": f"Factura no encontrada: {invoice_id}"}
        self.store.update_invoice_status(invoice_id, "paid")
        return {
            "invoice_id": invoice_id,
            "invoice_number": invoice.get("invoice_number"),
            "status": "paid",
            "message": f"Factura {invoice.get('invoice_number') or invoice_id} marcada como pagada.",
        }
