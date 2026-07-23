from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from apps.zeromanual_env import zm_env


@dataclass(frozen=True)
class CommercialSettings:
    db_path: str
    webhook_secret: str
    ops_url: str
    ops_api_key: str
    ops_tenant_id: str


def load_commercial_settings() -> CommercialSettings:
    load_dotenv()
    return CommercialSettings(
        db_path=zm_env("DB_PATH", "runtime/zeromanual.db"),
        webhook_secret=zm_env("WEBHOOK_SECRET", ""),
        ops_url=zm_env("OPS_URL", ""),
        ops_api_key=zm_env("OPS_API_KEY", ""),
        ops_tenant_id=zm_env("OPS_TENANT_ID", "zeromanual"),
    )
