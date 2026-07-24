from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from apps.orchestrator.models import DEFAULT_ENTITY_ID
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


def test_default_admin_password_is_random_not_hardcoded(tmp_path: Path) -> None:
    db_path = str(tmp_path / "rand_admin.db")
    store1 = DataStore(db_path=db_path)
    assert store1.generated_admin_password is not None
    assert store1.generated_admin_password != "admin123"
    assert store1.authenticate_user("admin", store1.generated_admin_password) is not None
    # Re-opening the same (already-seeded) DB must not regenerate/reprint a password.
    store2 = DataStore(db_path=db_path)
    assert store2.generated_admin_password is None


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


# ---- Business entities (persona fisica / empresa) ----


def test_default_entity_backfilled_on_fresh_db(store: DataStore) -> None:
    entity = store.get_business_entity(DEFAULT_ENTITY_ID)
    assert entity is not None
    assert entity["is_default"] == 1


def test_create_and_list_business_entities(store: DataStore) -> None:
    entity = store.create_business_entity(
        entity_type="persona_fisica",
        name="Victor Luid",
        tax_id="12345678A",
        address="Calle Falsa 123",
        default_vat_rate=21.0,
        invoice_series="FAC-P",
    )
    assert entity["entity_type"] == "persona_fisica"
    all_entities = store.list_business_entities()
    assert any(e["entity_id"] == entity["entity_id"] for e in all_entities)


def test_get_business_entity_not_found_returns_none(store: DataStore) -> None:
    assert store.get_business_entity("BIZ-NOPE0000") is None


def test_update_business_entity(store: DataStore) -> None:
    entity = store.create_business_entity(
        entity_type="empresa", name="Old Name", tax_id="B12345678", invoice_series="FAC-E"
    )
    updated = store.update_business_entity(entity["entity_id"], name="New Name", default_vat_rate=10.0)
    assert updated["name"] == "New Name"
    assert updated["default_vat_rate"] == 10.0
    assert updated["tax_id"] == "B12345678"  # untouched field preserved


def test_invoice_number_independent_per_entity(store: DataStore) -> None:
    other = store.create_business_entity(
        entity_type="empresa", name="Otra Empresa", tax_id="B87654321", invoice_series="FAC-O"
    )
    n_default_1 = store.next_invoice_number()
    n_other_1 = store.next_invoice_number(entity_id=other["entity_id"])
    n_default_2 = store.next_invoice_number()
    assert n_default_1.startswith("FAC-")
    assert n_other_1.startswith("FAC-O-")
    assert int(n_default_2.rsplit("-", 1)[1]) == int(n_default_1.rsplit("-", 1)[1]) + 1


def test_client_memory_no_cross_entity_collision(store: DataStore) -> None:
    other = store.create_business_entity(
        entity_type="empresa", name="Otra Empresa", tax_id="B11223344", invoice_series="FAC-X"
    )
    store.upsert_client_memory("Mismo Cliente", "nota entidad default")
    store.upsert_client_memory("Mismo Cliente", "nota otra entidad", entity_id=other["entity_id"])
    assert store.get_client_memory("Mismo Cliente") == "nota entidad default"
    assert store.get_client_memory("Mismo Cliente", entity_id=other["entity_id"]) == "nota otra entidad"


def test_list_invoices_filtered_by_entity(store: DataStore) -> None:
    other = store.create_business_entity(
        entity_type="empresa", name="Otra Empresa", tax_id="B99887766", invoice_series="FAC-Y"
    )
    store.save_invoice("INV-D1", "evt-d1", "Cliente A", 100.0, "issued")
    store.save_invoice("INV-O1", "evt-o1", "Cliente B", 200.0, "issued", entity_id=other["entity_id"])
    default_invoices = store.list_invoices(entity_id=DEFAULT_ENTITY_ID)
    other_invoices = store.list_invoices(entity_id=other["entity_id"])
    assert any(i["invoice_id"] == "INV-D1" for i in default_invoices)
    assert not any(i["invoice_id"] == "INV-O1" for i in default_invoices)
    assert any(i["invoice_id"] == "INV-O1" for i in other_invoices)


def test_list_ledger_entries_filtered_by_entity(store: DataStore) -> None:
    other = store.create_business_entity(
        entity_type="empresa", name="Otra Empresa", tax_id="B55443322", invoice_series="FAC-Z"
    )
    id_default = store.save_ledger_entry(
        event_id="evt-le-d1", client_name="A", amount_eur=10.0, category="ingreso_servicios",
        reference=None, status="classified",
    )
    id_other = store.save_ledger_entry(
        event_id="evt-le-o1", client_name="B", amount_eur=20.0, category="ingreso_servicios",
        reference=None, status="classified", entity_id=other["entity_id"],
    )
    default_entries = store.list_ledger_entries(entity_id=DEFAULT_ENTITY_ID)
    other_entries = store.list_ledger_entries(entity_id=other["entity_id"])
    assert any(e["entry_id"] == id_default for e in default_entries)
    assert not any(e["entry_id"] == id_other for e in default_entries)
    assert any(e["entry_id"] == id_other for e in other_entries)
