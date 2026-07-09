from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fpdf import FPDF, XPos, YPos

from apps.integrations.settings import CompanySettings


class InvoicePDFGenerator:
    def __init__(self, company: CompanySettings, output_dir: str) -> None:
        self.company = company
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        invoice_id: str,
        invoice_number: str,
        client_name: str,
        base_amount_eur: float,
        vat_rate: float,
        vat_amount_eur: float,
        total_eur: float,
        issue_date: date | None = None,
        client_nif: str = "",
        concept: str = "Servicios de automatizacion digital",
    ) -> Path:
        issue_date = issue_date or date.today()
        safe_number = invoice_number.replace("/", "-")
        pdf_path = self.output_dir / f"{safe_number}.pdf"

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, self.company.name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font("Helvetica", size=10)
        if self.company.nif:
            pdf.cell(0, 6, f"NIF: {self.company.nif}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if self.company.address:
            pdf.cell(0, 6, self.company.address, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.ln(8)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"FACTURA {invoice_number}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 6, f"Fecha: {issue_date.isoformat()}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, f"Referencia interna: {invoice_id}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(6)

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Cliente", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 6, client_name, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if client_nif:
            pdf.cell(0, 6, f"NIF: {client_nif}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.ln(8)
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 6, f"Concepto: {concept}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        rows = [
            ("Base imponible", f"{base_amount_eur:.2f} EUR"),
            (f"IVA ({vat_rate:.0f}%)", f"{vat_amount_eur:.2f} EUR"),
            ("TOTAL", f"{total_eur:.2f} EUR"),
        ]
        for label, value in rows:
            pdf.set_font("Helvetica", "B" if label == "TOTAL" else "", 10)
            pdf.cell(95, 8, label)
            pdf.cell(0, 8, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.ln(12)
        pdf.set_font("Helvetica", size=8)
        pdf.multi_cell(
            0,
            5,
            "Documento generado por ZeroManual. Borrador operativo: revisar con asesoria "
            "antes de presentacion fiscal oficial.",
        )

        pdf.output(str(pdf_path))
        return pdf_path

    @staticmethod
    def compute_amounts(
        amount_eur: float | None,
        vat_rate: float,
    ) -> dict[str, float]:
        total = float(amount_eur or 0.0)
        if total <= 0:
            return {"base": 0.0, "vat": 0.0, "total": 0.0}
        base = round(total / (1 + vat_rate / 100), 2)
        vat = round(total - base, 2)
        return {"base": base, "vat": vat, "total": total}
