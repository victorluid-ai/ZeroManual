from __future__ import annotations

from typing import Any

from apps.orchestrator.audit import AuditLogger
from apps.orchestrator.config import load_settings
from apps.orchestrator.handoffs import build_handoff_events
from apps.orchestrator.models import AgentDecision, Event, ExecutionResult, ExecutionStatus, PendingApproval, RiskLevel
from apps.orchestrator.registry import build_agent_registry
from apps.orchestrator.store import DataStore


class OrchestratorRuntime:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.audit = AuditLogger()
        self.store = DataStore(self.settings.db_path)
        self.registry = build_agent_registry(store=self.store)
        self._hydrate_pending_from_db()

    def _hydrate_pending_from_db(self) -> None:
        self.pending_approvals: dict[str, PendingApproval] = {}
        for row in self.store.list_pending_approvals():
            event = Event(
                event_id=row["event_id"],
                agent_name=row["agent_name"],
                action=row["action"],
                payload=row["payload"],
                entity_id=row["entity_id"],
            )
            decision_data = row["decision"]
            decision = AgentDecision(
                summary=decision_data["summary"],
                risk_level=RiskLevel(decision_data["risk_level"]),
                proposed_actions=decision_data["proposed_actions"],
                requires_human_approval=decision_data["requires_human_approval"],
            )
            self.pending_approvals[row["event_id"]] = PendingApproval(event=event, decision=decision)

    def process_event(self, raw_event: dict[str, Any]) -> dict[str, Any]:
        event = Event(**raw_event)
        agent = self.registry.get(event.agent_name)
        if agent is None:
            error = {"error": f"Unknown agent: {event.agent_name}"}
            self.audit.write("orchestrator", event.event_id, "FAILED", error)
            return error

        result = agent.handle_event(event, self.settings.approval_threshold_eur)
        serialized = result.model_dump()

        self.store.log_event(
            event_id=event.event_id,
            agent_name=event.agent_name,
            action=event.action,
            status=result.status.value,
            source=event.source,
            payload=event.payload,
        )

        if result.status == ExecutionStatus.NEEDS_APPROVAL:
            self.pending_approvals[event.event_id] = PendingApproval(event=event, decision=result.decision)
            self.store.save_pending_approval(
                event_id=event.event_id,
                agent_name=event.agent_name,
                action=event.action,
                payload=event.payload,
                decision=result.decision.model_dump(mode="json"),
                entity_id=event.entity_id,
            )
        elif result.status == ExecutionStatus.COMPLETED:
            self._persist_billing_output(event, result.output)
            handoffs = self._run_handoffs(event, result)
            if handoffs:
                serialized["handoffs"] = handoffs

        self.audit.write(agent.name, event.event_id, result.status.value, serialized)
        return serialized

    def _run_handoffs(self, event: Event, result: ExecutionResult) -> list[dict[str, Any]]:
        outcomes: list[dict[str, Any]] = []
        for raw in build_handoff_events(event, result.output, result.status):
            child = self.process_event(raw)
            outcomes.append({"event": raw, "result": child})
        return outcomes

    def _persist_billing_output(self, event: Event, output: dict[str, Any], approved_by: str | None = None) -> None:
        if event.agent_name != "AgentBillingOps" or "invoice_id" not in output:
            return
        existing = self.store.get_invoice(str(output["invoice_id"]))
        if existing and existing.get("pdf_path"):
            return
        client_name = event.payload.get("client_name") or event.payload.get("client")
        amount = event.payload.get("amount_eur")
        self.store.save_invoice(
            invoice_id=output["invoice_id"],
            event_id=event.event_id,
            client_name=str(client_name) if client_name else None,
            amount_eur=float(amount) if amount is not None else None,
            status=output.get("status", "issued"),
            approved_by=approved_by,
            entity_id=event.entity_id,
        )

    def list_agents(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for name, agent in self.registry.items():
            entries.append(
                {
                    "agent_name": name,
                    "supported_actions": list(agent.supported_actions),
                }
            )
        return entries

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        return self.store.list_pending_approvals()

    def list_invoices(self, limit: int = 50, entity_id: str | None = None) -> list[dict[str, Any]]:
        return self.store.list_invoices(limit=limit, entity_id=entity_id)

    def approve(self, event_id: str, approved_by: str) -> dict[str, Any]:
        pending = self.pending_approvals.get(event_id)
        if pending is None:
            stored = self.store.load_pending_approval(event_id)
            if stored is None:
                return {"error": f"No pending approval for event_id={event_id}"}
            d = stored["decision"]
            pending = PendingApproval(
                event=Event(
                    event_id=stored["event_id"],
                    agent_name=stored["agent_name"],
                    action=stored["action"],
                    payload=stored["payload"],
                    entity_id=stored["entity_id"],
                ),
                decision=AgentDecision(
                    summary=d["summary"],
                    risk_level=RiskLevel(d["risk_level"]),
                    proposed_actions=d["proposed_actions"],
                    requires_human_approval=d["requires_human_approval"],
                ),
            )

        agent = self.registry.get(pending.event.agent_name)
        if agent is None:
            return {"error": f"Unknown agent for pending event_id={event_id}"}

        output = agent.execute(pending.event, pending.decision)
        response = {
            "status": "COMPLETED",
            "event_id": event_id,
            "approved_by": approved_by,
            "output": output,
            "audit_notes": ["Approved by human operator and executed."],
        }
        self._persist_billing_output(pending.event, output, approved_by=approved_by)
        self.store.log_event(
            event_id=event_id,
            agent_name=pending.event.agent_name,
            action=pending.event.action,
            status="COMPLETED",
            source=pending.event.source,
            payload=pending.event.payload,
        )
        self.audit.write(agent.name, event_id, "COMPLETED", response)

        handoff_event = Event(
            event_id=event_id,
            agent_name=pending.event.agent_name,
            action=pending.event.action,
            payload=pending.event.payload,
            source=pending.event.source,
            entity_id=pending.event.entity_id,
        )
        handoff_result = ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            decision=pending.decision,
            output=output,
        )
        handoffs = self._run_handoffs(handoff_event, handoff_result)
        if handoffs:
            response["handoffs"] = handoffs

        self.store.delete_pending_approval(event_id)
        if event_id in self.pending_approvals:
            del self.pending_approvals[event_id]
        return response

    def get_client_context(self, client_name: str) -> dict[str, Any]:
        notes = self.store.get_client_memory(client_name)
        invoices = [
            inv
            for inv in self.store.list_invoices(limit=100)
            if inv.get("client_name") == client_name
        ]
        ledger = [
            entry
            for entry in self.store.list_ledger_entries(limit=100)
            if entry.get("client_name") == client_name
        ]
        return {
            "client_name": client_name,
            "memory": notes,
            "invoices": invoices[:10],
            "ledger_entries": ledger[:10],
        }

    def reject(self, event_id: str, rejected_by: str, reason: str) -> dict[str, Any]:
        pending = self.pending_approvals.get(event_id)
        agent_name = pending.event.agent_name if pending else "unknown"
        if pending is None:
            stored = self.store.load_pending_approval(event_id)
            if stored:
                agent_name = stored["agent_name"]

        response = {
            "status": "REJECTED",
            "event_id": event_id,
            "rejected_by": rejected_by,
            "reason": reason,
        }
        self.audit.write(agent_name, event_id, "REJECTED", response)
        self.store.delete_pending_approval(event_id)
        if event_id in self.pending_approvals:
            del self.pending_approvals[event_id]
        return response
