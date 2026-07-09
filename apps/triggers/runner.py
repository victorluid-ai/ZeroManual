from __future__ import annotations

import json
import time

from apps.triggers.config import load_trigger_settings
from apps.triggers.dispatcher import TriggerDispatcher

_MAX_BACKOFF_S = 300
_MAX_CONSECUTIVE_ERRORS = 10


def main() -> None:
    settings = load_trigger_settings()
    dispatcher = TriggerDispatcher()

    if not settings.email.enabled:
        print("EMAIL_TRIGGER_ENABLED=false — enable email triggers in .env to start watching.")
        print("Required: EMAIL_IMAP_USER, EMAIL_IMAP_PASSWORD, EMAIL_IMAP_HOST")
        return

    poll_interval = settings.email.poll_interval_seconds
    print(
        f"ZeroManual trigger runner started. Polling email every "
        f"{poll_interval}s on {settings.email.imap_folder}"
    )

    consecutive_errors = 0
    backoff = poll_interval

    while True:
        try:
            outcomes = dispatcher.run_cycle()
            for outcome in outcomes:
                print(json.dumps(outcome, ensure_ascii=True, default=str))
            consecutive_errors = 0
            backoff = poll_interval
            time.sleep(poll_interval)
        except Exception as exc:
            consecutive_errors += 1
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
            print(f"[ERROR #{consecutive_errors}] Trigger cycle error: {exc}")
            if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                print(
                    f"[CRITICAL] {consecutive_errors} consecutive errors — last: {exc}. Exiting."
                )
                raise SystemExit(1)
            print(f"Retrying in {backoff}s...")
            time.sleep(backoff)


if __name__ == "__main__":
    main()
