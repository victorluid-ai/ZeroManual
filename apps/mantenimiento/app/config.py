"""Configuración de Mantenimiento (Supabase)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = "Mantenimiento"
    host: str = "0.0.0.0"
    port: int = 8100
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_anon_key: str = ""
    default_group_slug: str = "sabores-atlanticos"
    demo_mode: bool = False

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


@lru_cache
def get_settings() -> Settings:
    return Settings(
        host=os.getenv("MANTENIMIENTO_HOST", "0.0.0.0"),
        port=int(os.getenv("MANTENIMIENTO_PORT", "8100")),
        supabase_url=os.getenv("SUPABASE_URL", "").rstrip("/"),
        supabase_service_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
        default_group_slug=os.getenv(
            "MANTENIMIENTO_DEFAULT_GROUP_SLUG", "sabores-atlanticos"
        ),
        demo_mode=os.getenv("MANTENIMIENTO_DEMO_MODE", "").lower() in (
            "1",
            "true",
            "yes",
        ),
    )
