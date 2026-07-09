from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class EmailSettings:
    enabled: bool
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    imap_folder: str
    poll_interval_seconds: int


@dataclass(frozen=True)
class TriggerSettings:
    email: EmailSettings


def load_trigger_settings() -> TriggerSettings:
    load_dotenv()
    return TriggerSettings(
        email=EmailSettings(
            enabled=os.getenv("EMAIL_TRIGGER_ENABLED", "false").lower() == "true",
            imap_host=os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com"),
            imap_port=int(os.getenv("EMAIL_IMAP_PORT", "993")),
            imap_user=os.getenv("EMAIL_IMAP_USER", ""),
            imap_password=os.getenv("EMAIL_IMAP_PASSWORD", ""),
            imap_folder=os.getenv("EMAIL_IMAP_FOLDER", "INBOX"),
            poll_interval_seconds=int(os.getenv("EMAIL_POLL_INTERVAL_SECONDS", "60")),
        )
    )
