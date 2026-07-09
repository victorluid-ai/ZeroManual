from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from apps.zeromanual_env import zm_env

@dataclass(frozen=True)
class CompanySettings:
    name: str
    nif: str
    address: str
    default_vat_rate: float
    invoice_series: str


@dataclass(frozen=True)
class SmtpSettings:
    enabled: bool
    host: str
    port: int
    user: str
    password: str
    from_address: str
    use_tls: bool
    auto_send_on_issue: bool


@dataclass(frozen=True)
class IntegrationSettings:
    company: CompanySettings
    smtp: SmtpSettings
    invoices_dir: str
    exports_dir: str


def load_integration_settings() -> IntegrationSettings:
    load_dotenv()
    return IntegrationSettings(
        company=CompanySettings(
            name=zm_env("COMPANY_NAME", "ZeroManual"),
            nif=zm_env("COMPANY_NIF", ""),
            address=zm_env("COMPANY_ADDRESS", ""),
            default_vat_rate=float(zm_env("DEFAULT_VAT_RATE", "21")),
            invoice_series=zm_env("INVOICE_SERIES", "FAC"),
        ),
        smtp=SmtpSettings(
            enabled=os.getenv("SMTP_ENABLED", "false").lower() == "true",
            host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
            port=int(os.getenv("SMTP_PORT", "587")),
            user=os.getenv("SMTP_USER", ""),
            password=os.getenv("SMTP_PASSWORD", ""),
            from_address=os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "billing@zeromanual.co")),
            use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
            auto_send_on_issue=os.getenv("SMTP_AUTO_SEND_ON_ISSUE", "false").lower() == "true",
        ),
        invoices_dir=os.getenv("INVOICES_OUTPUT_DIR", "runtime/invoices"),
        exports_dir=os.getenv("EXPORTS_OUTPUT_DIR", "runtime/exports"),
    )
