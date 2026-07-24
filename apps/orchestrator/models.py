from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# Fiscal/business entity every booked event belongs to (invoice series, NIF/CIF...).
# Existing rows and callers that predate multi-entity support fall back to this one.
DEFAULT_ENTITY_ID = "BIZ-00000001"


class RiskLevel(str, Enum):
    A_LOW = "A_LOW"
    B_MEDIUM = "B_MEDIUM"
    C_HIGH = "C_HIGH"


class ExecutionStatus(str, Enum):
    COMPLETED = "COMPLETED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    FAILED = "FAILED"


class Event(BaseModel):
    event_id: str
    source: str = "api"
    agent_name: str
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    entity_id: str = DEFAULT_ENTITY_ID


class AgentDecision(BaseModel):
    summary: str
    risk_level: RiskLevel
    proposed_actions: list[str]
    requires_human_approval: bool


class ExecutionResult(BaseModel):
    status: ExecutionStatus
    decision: AgentDecision
    output: dict[str, Any] = Field(default_factory=dict)
    audit_notes: list[str] = Field(default_factory=list)


class PendingApproval(BaseModel):
    event: Event
    decision: AgentDecision
