from __future__ import annotations

from typing import Any

from apps.common.tax_id import is_valid_nif
from apps.integrations.invoice_pdf import InvoicePDFGenerator
from apps.integrations.settings import CompanySettings, load_integration_settings
from apps.integrations.smtp_client import SmtpClient
from apps.orchestrator.models import DEFAULT_ENTITY_ID
from apps.orchestrator.store import DataStore

VALID_VAT_RATES: frozenset[float] = frozenset({0.0, 4.0, 10.0, 21.0})


class BillingTools:
    def __init__(self, store: DataStore) -> None:
        self.store = store
        self._settings = load_integration_settings()
        self._smtp = SmtpClient(self._settings.smtp)

    def _company_settings_for(self, entity_id: str) -> CompanySettings:
        """Fiscal identity to print on the invoice — from the business_entities
        row for entity_id, falling back to the single .env-configured company
        only if the row is somehow missing (shouldn't happen in practice)."""
        row = self.store.get_business_entity(entity_id)
        if row is None:
            return self._settings.company
        return CompanySettings(
            name=row["name"],
            nif=row["tax_id"],
            address=row["address"],
            default_vat_rate=row["default_vat_rate"],
            invoice_series=row["invoice_series"],
        )

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
        entity_id: str = DEFAULT_ENTITY_ID,
    ) -> dict[str, Any]:
        if client_nif and not is_valid_nif(client_nif):
            return {
                "error": (
                    f"NIF/CIF no valido: '{client_nif}'. "
                    "Formatos aceptados: DNI (12345678A), CIF (B1234567X), NIE (X1234567A)."
                )
            }
        company = self._company_settings_for(entity_id)
        effective_vat_rate = vat_rate if vat_rate is not None else company.default_vat_rate
        if effective_vat_rate not in VALID_VAT_RATES:
            return {
                "error": (
                    f"Tipo de IVA no valido: {effective_vat_rate}%. "
                    f"Valores permitidos segun RD 1619/2012: {sorted(VALID_VAT_RATES)}"
                )
            }
        invoice_id = f"INV-{event_id[:8].upper()}"
        existing = self.store.get_invoice(invoice_id)
        if existing is not None and existing.get("pdf_path"):
            # Idempotent: replaying the same event_id (retry, at-least-once
            # delivery) must not burn another legal invoice number/PDF.
            return {
                "invoice_id": invoice_id,
                "invoice_number": existing.get("invoice_number"),
                "status": existing.get("status", "issued"),
                "client_name": existing.get("client_name"),
                "amount_eur": str(existing.get("amount_eur") or ""),
                "pdf_path": existing.get("pdf_path"),
                "message": f"Factura {existing.get('invoice_number')} ya emitida para este evento (sin duplicar).",
            }
        invoice_number = self.store.next_invoice_number(entity_id=entity_id)
        amounts = InvoicePDFGenerator.compute_amounts(amount_eur, effective_vat_rate)

        pdf = InvoicePDFGenerator(company, self._settings.invoices_dir)
        pdf_path = pdf.generate(
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
            entity_id=entity_id,
        )

        if client_name:
            notes = f"Ultima factura {invoice_number} ({invoice_id})"
            if amount_eur is not None:
                notes += f" por {amount_eur} EUR"
            self.store.upsert_client_memory(client_name, notes, entity_id=entity_id)

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
        company = self._company_settings_for(invoice.get("entity_id") or DEFAULT_ENTITY_ID)

        subject = f"Factura {invoice_number} — {company.name}"
        body = (
            f"Hola {client_name},\n\n"
            f"Adjuntamos la factura {invoice_number}"
            f"{f' por un importe de {total:.2f} EUR' if total is not None else ''}.\n\n"
            f"Saludos,\n{company.name}"
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
