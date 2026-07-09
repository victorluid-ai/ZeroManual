from __future__ import annotations

from typing import Any
from uuid import uuid4

from apps.orchestrator.runtime import OrchestratorRuntime
from apps.triggers.config import load_trigger_settings
from apps.triggers.detector import TriggerDetector
from apps.triggers.email_watcher import EmailWatcher
from apps.triggers.models import TriggerSignal, TriggerType


class TriggerDispatcher:
    """Polls external signals and autonomously wakes the right agent when needed."""

    def __init__(self, runtime: OrchestratorRuntime | None = None) -> None:
        self.runtime = runtime or OrchestratorRuntime()
        self.settings = load_trigger_settings()
        self.detector = TriggerDetector()
        self.email_watcher = EmailWatcher(self.settings.email)

    def run_cycle(self) -> list[dict[str, Any]]:
        outcomes: list[dict[str, Any]] = []
        if self.settings.email.enabled:
            for signal in self.email_watcher.poll():
                uid = signal.payload.get("uid")
                folder = signal.payload.get("folder", "INBOX")
                if uid and self.runtime.store.is_email_processed(str(uid), str(folder)):
                    continue
                outcomes.append(self._handle_signal(signal))
        return outcomes

    def _handle_signal(self, signal: TriggerSignal) -> dict[str, Any]:
        decision = self.detector.evaluate(signal)

        self.runtime.store.log_trigger(
            signal_id=signal.signal_id,
            trigger_type=signal.trigger_type.value,
            activated=decision.should_activate,
            agent_name=decision.agent_name,
            reason=decision.reason,
        )

        uid = signal.payload.get("uid")
        folder = signal.payload.get("folder", "INBOX")

        if not decision.should_activate or not decision.agent_name or not decision.action:
            if uid:
                self.runtime.store.mark_email_processed(str(uid), str(folder))
            return {
                "signal_id": signal.signal_id,
                "activated": False,
                "reason": decision.reason,
                "summary": signal.summary,
            }

        event_id = str(uuid4())
        event = {
            "event_id": event_id,
            "source": f"trigger_{signal.trigger_type.value}",
            "agent_name": decision.agent_name,
            "action": decision.action,
            "payload": {
                **decision.event_payload,
                "trigger_signal_id": signal.signal_id,
            },
        }
        result = self.runtime.process_event(event)

        if uid:
            self.runtime.store.mark_email_processed(str(uid), str(folder))

        return {
            "signal_id": signal.signal_id,
            "activated": True,
            "reason": decision.reason,
            "summary": signal.summary,
            "event": event,
            "result": result,
        }
