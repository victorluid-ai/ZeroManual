"""Variables de entorno ZeroManual (acepta prefijo legacy MANUALZERO_)."""

from __future__ import annotations

import os


def zm_env(name: str, default: str = "") -> str:
    current = os.getenv(f"ZEROMANUAL_{name}")
    if current is not None and current != "":
        return current
    legacy = os.getenv(f"MANUALZERO_{name}")
    if legacy is not None:
        return legacy
    return default
