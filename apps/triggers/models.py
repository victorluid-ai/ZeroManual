from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TriggerType(str, Enum):
    EMAIL = "email"


class TriggerSignal(BaseModel):
    trigger_type: TriggerType
    signal_id: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ActivationDecision(BaseModel):
    should_activate: bool
    agent_name: str | None = None
    action: str | None = None
    event_payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
