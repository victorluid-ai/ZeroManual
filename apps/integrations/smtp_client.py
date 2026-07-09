from __future__ import annotations

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from apps.integrations.settings import SmtpSettings


class SmtpClient:
    def __init__(self, settings: SmtpSettings) -> None:
        self.settings = settings

    @property
    def ready(self) -> bool:
        return bool(
            self.settings.enabled
            and self.settings.host
            and self.settings.user
            and self.settings.password
        )

    def send_invoice(
        self,
        to_email: str,
        subject: str,
        body: str,
        pdf_path: Path,
        invoice_number: str,
    ) -> dict[str, str]:
        if not self.ready:
            return {
                "status": "skipped",
                "message": "SMTP no configurado (SMTP_ENABLED=true y credenciales).",
            }

        msg = MIMEMultipart()
        msg["From"] = self.settings.from_address
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        attachment = MIMEApplication(pdf_path.read_bytes(), _subtype="pdf")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"factura_{invoice_number.replace('/', '-')}.pdf",
        )
        msg.attach(attachment)

        if self.settings.use_tls:
            with smtplib.SMTP(self.settings.host, self.settings.port, timeout=30) as server:
                server.starttls()
                server.login(self.settings.user, self.settings.password)
                server.sendmail(self.settings.from_address, [to_email], msg.as_string())
        else:
            with smtplib.SMTP_SSL(self.settings.host, self.settings.port, timeout=30) as server:
                server.login(self.settings.user, self.settings.password)
                server.sendmail(self.settings.from_address, [to_email], msg.as_string())

        return {"status": "sent", "message": f"Factura enviada a {to_email}."}
