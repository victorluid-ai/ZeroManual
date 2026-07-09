from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from apps.orchestrator.store import DataStore


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(db_path=str(tmp_path / "test.db"))


def test_invoice_number_sequential(store: DataStore) -> None:
    n1 = store.next_invoice_number()
    n2 = store.next_invoice_number()
    n3 = store.next_invoice_number()
    parts1 = n1.rsplit("-", 1)
    parts2 = n2.rsplit("-", 1)
    parts3 = n3.rsplit("-", 1)
    assert int(parts2[1]) == int(parts1[1]) + 1
    assert int(parts3[1]) == int(parts2[1]) + 1


def test_invoice_number_format(store: DataStore) -> None:
    num = store.next_invoice_number()
    parts = num.split("-")
    assert len(parts) == 3
    assert parts[2].isdigit() and len(parts[2]) == 4


def test_save_and_get_invoice(store: DataStore) -> None:
    store.save_invoice(
        invoice_id="INV-TEST001",
        event_id="evt-001",
        client_name="Acme SL",
        amount_eur=100.0,
        status="issued",
    )
    inv = store.get_invoice("INV-TEST001")
    assert inv is not None
    assert inv["client_name"] == "Acme SL"
    assert inv["status"] == "issued"


def test_update_invoice_status(store: DataStore) -> None:
    store.save_invoice("INV-002", "evt-002", "Beta SA", 200.0, "issued")
    store.update_invoice_status("INV-002", "paid")
    inv = store.get_invoice("INV-002")
    assert inv["status"] == "paid"


def test_pending_approvals_roundtrip(store: DataStore) -> None:
    store.save_pending_approval(
        event_id="evt-003",
        agent_name="AgentBillingOps",
        action="create_invoice",
        payload={"amount_eur": 1000.0},
        decision={"summary": "Big invoice", "risk_level": "C_HIGH", "proposed_actions": [], "requires_human_approval": True},
    )
    rows = store.list_pending_approvals()
    assert any(r["event_id"] == "evt-003" for r in rows)
    store.delete_pending_approval("evt-003")
    rows = store.list_pending_approvals()
    assert not any(r["event_id"] == "evt-003" for r in rows)


def test_client_memory(store: DataStore) -> None:
    store.upsert_client_memory("Acme SL", "primer cliente, paga tarde")
    notes = store.get_client_memory("Acme SL")
    assert notes == "primer cliente, paga tarde"
    store.upsert_client_memory("Acme SL", "actualizado")
    assert store.get_client_memory("Acme SL") == "actualizado"


def test_email_processed_dedup(store: DataStore) -> None:
    assert not store.is_email_processed("uid-1", "INBOX")
    store.mark_email_processed("uid-1", "INBOX")
    assert store.is_email_processed("uid-1", "INBOX")
    assert not store.is_email_processed("uid-1", "SENT")


def test_ledger_entry(store: DataStore) -> None:
    entry_id = store.save_ledger_entry(
        event_id="evt-ld-001",
        client_name="Gamma SL",
        amount_eur=500.0,
        category="ingreso_servicios",
        reference="INV-001",
        status="classified",
    )
    entries = store.list_ledger_entries()
    assert any(e["entry_id"] == entry_id for e in entries)
