from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from apps.zeromanual_env import zm_env


@dataclass(frozen=True)
class Settings:
    environment: str
    claude_model: str
    ai_mode: str
    approval_threshold_eur: float
    db_path: str
    webhook_secret: str
    api_key: str
    operators: frozenset[str]


def load_settings() -> Settings:
    load_dotenv()
    raw_ops = zm_env("OPERATORS", "owner")
    operators = frozenset(o.strip() for o in raw_ops.split(",") if o.strip())
    return Settings(
        environment=zm_env("ENV", "dev"),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
        ai_mode=zm_env("AI_MODE", "eco").lower(),
        approval_threshold_eur=float(os.getenv("APPROVAL_THRESHOLD_EUR", "500.0")),
        db_path=zm_env("DB_PATH", "runtime/zeromanual.db"),
        webhook_secret=zm_env("WEBHOOK_SECRET", ""),
        api_key=zm_env("API_KEY", ""),
        operators=operators,
    )
