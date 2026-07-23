from __future__ import annotations

from pathlib import Path

from apps.commercial.store import DataStore


def test_users_and_clients(tmp_path: Path) -> None:
    store = DataStore(str(tmp_path / "c.db"))
    # may already have seeded admin
    users = store.list_users()
    assert len(users) >= 1

    client = store.create_client("Demo", "demo@x.com", "pass")
    assert client["client_id"].startswith("CLI-")
    assert store.authenticate_client("demo@x.com", "pass") is not None
    assert store.authenticate_client("demo@x.com", "wrong") is None

    store.activate_automation(client["client_id"], "google_reviews", "wf-1")
    autos = store.list_client_automations(client["client_id"])
    assert autos[0]["status"] == "active"


def test_drafts(tmp_path: Path) -> None:
    store = DataStore(str(tmp_path / "d.db"))
    client = store.create_client("D2", "d2@x.com", "pass")
    draft = store.create_draft(
        client_id=client["client_id"],
        automation_type="google_reviews",
        suggested_reply="Hola",
        source_text="Buen servicio",
    )
    assert draft["status"] == "pending"
    updated = store.resolve_draft(draft["draft_id"], "approved", "Hola")
    assert updated["status"] == "approved"
