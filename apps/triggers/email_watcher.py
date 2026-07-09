from __future__ import annotations

import email
import imaplib
from email.header import decode_header
from typing import Any

from apps.triggers.config import EmailSettings
from apps.triggers.models import TriggerSignal, TriggerType


class EmailWatcher:
    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    def poll(self) -> list[TriggerSignal]:
        if not self.settings.enabled:
            return []

        signals: list[TriggerSignal] = []
        mail = imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port)
        try:
            mail.login(self.settings.imap_user, self.settings.imap_password)
            mail.select(self.settings.imap_folder)
            status, data = mail.search(None, "UNSEEN")
            if status != "OK" or not data[0]:
                return []

            for uid in data[0].split():
                uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)

                status, msg_data = mail.fetch(uid, "(RFC822)")
                if status != "OK" or not msg_data:
                    continue

                raw = msg_data[0][1]
                message = email.message_from_bytes(raw)
                subject = self._decode_header(message.get("Subject", ""))
                from_addr = self._decode_header(message.get("From", ""))
                body = self._extract_body(message)

                signal = TriggerSignal(
                    trigger_type=TriggerType.EMAIL,
                    signal_id=f"email-{uid_str}",
                    summary=f"Nuevo email: {subject}",
                    payload={
                        "uid": uid_str,
                        "folder": self.settings.imap_folder,
                        "subject": subject,
                        "from_email": from_addr,
                        "body": body[:4000],
                    },
                )
                signals.append(signal)
        finally:
            try:
                mail.logout()
            except Exception:
                pass

        return signals

    def _decode_header(self, value: str) -> str:
        if not value:
            return ""
        parts = decode_header(value)
        decoded: list[str] = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)

    def _extract_body(self, message: Any) -> str:
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain" and "attachment" not in str(
                    part.get("Content-Disposition", "")
                ):
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            return ""
        payload = message.get_payload(decode=True)
        if payload:
            return payload.decode(message.get_content_charset() or "utf-8", errors="replace")
        return str(message.get_payload())
