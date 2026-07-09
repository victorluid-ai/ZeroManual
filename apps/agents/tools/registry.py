from __future__ import annotations

from typing import Any, Callable

from apps.agents.tools.accounting import AccountingTools
from apps.agents.tools.billing import BillingTools
from apps.agents.tools.delivery import DeliveryTools
from apps.agents.tools.governance import GovernanceTools
from apps.agents.tools.sales import SalesTools
from apps.orchestrator.store import DataStore


class ToolRegistry:
    def __init__(self, store: DataStore) -> None:
        billing = BillingTools(store)
        accounting = AccountingTools(store)
        governance = GovernanceTools(store)
        sales = SalesTools(store)
        delivery = DeliveryTools(store)

        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "create_invoice_draft": billing.create_invoice_draft,
            "send_invoice_email": billing.send_invoice_email,
            "mark_invoice_paid": billing.mark_invoice_paid,
            "classify_ledger_entry": accounting.classify_ledger_entry,
            "record_vat_draft": accounting.record_vat_draft,
            "log_compliance_check": governance.log_compliance_check,
            "update_lead": sales.update_lead,
            "log_delivery_update": delivery.log_delivery_update,
        }

    def run(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(tool_name)
        if handler is None:
            return {"error": f"Unknown tool: {tool_name}"}
        return handler(**arguments)

    @property
    def tool_names(self) -> list[str]:
        return list(self._handlers.keys())
