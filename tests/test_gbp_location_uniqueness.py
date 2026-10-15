"""A Google location can belong to only one live ExManual account."""

from __future__ import annotations

import importlib.util
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from apps.orchestrator.gbp_location_claim import (
    GBP_LOCATION_TAKEN_MESSAGE,
    LIVE_LOCATION_INDEX,
)
from apps.orchestrator.store import DataStore

LOCATION = "accounts/9/locations/1"
OTHER_LOCATION = "accounts/9/locations/2"
DUP_A = "ePhhOcDT7ew5q74A"
DUP_B = "74hUH1G0aTgGBrZT"


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("MANUALZERO_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "gbp-unique.db"))
    import importlib
    import apps.interface.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


def _register(client: TestClient, email: str) -> dict:
    resp = client.post(
        "/client/register",
        json={"name": "Negocio", "email": email, "password": "secret123"},
    )
    assert resp.status_code == 200
    return resp.json()


def _prepare(client: TestClient, email: str, location: str) -> tuple[dict, str, str]:
    import apps.interface.api as api_module

    reg = _register(client, email)
    client_id = reg["client"]["client_id"]
    auth = {"Authorization": f"Bearer {reg['token']}"}
    api_module.runtime.store.save_google_creds(
        client_id=client_id,
        refresh_token="reftok",
        access_token="tok",
        token_expiry=None,
        google_email=email,
        location_id=None,
    )
    rows = api_module.runtime.store.sync_businesses(
        client_id,
        [
            {
                "google_account_id": "accounts/9",
                "location_id": location,
                "business_name": "Ficha",
            }
        ],
    )
    business_id = next(row["business_id"] for row in rows if row["location_id"] == location)
    return auth, client_id, business_id


def _activate(client: TestClient, auth: dict, business_id: str):
    return client.post(
        f"/client/automations/google_reviews/activate?business_id={business_id}",
        headers=auth,
    )


def test_free_location_stores_real_n8n_workflow_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id, business_id = _prepare(client, "free@example.com", LOCATION)
    calls: list[str] = []

    def fake(**kwargs):
        calls.append(kwargs["client_id"])
        return "wf-real-1"

    monkeypatch.setattr(api_module._n8n, "duplicate_template", fake)
    resp = _activate(client, auth, business_id)
    assert resp.status_code == 200
    assert resp.json()["workflow_id"] == "wf-real-1"
    assert calls == [client_id]
    stored = api_module.runtime.store.get_automation(client_id, business_id, "google_reviews")
    assert stored["n8n_workflow_id"] == "wf-real-1"
    assert stored["location_id"] == LOCATION
    assert stored["status"] == "active"


def test_same_client_reuses_workflow_without_calling_n8n(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id, business_id = _prepare(client, "same@example.com", LOCATION)
    calls: list[str] = []
    monkeypatch.setattr(
        api_module._n8n,
        "duplicate_template",
        lambda **kwargs: calls.append("n8n") or "wf-same",
    )
    first = _activate(client, auth, business_id)
    second = _activate(client, auth, business_id)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["workflow_id"] == "wf-same"
    assert second.json()["workflow_id"] == "wf-same"
    assert calls == ["n8n"]

    conn = api_module.runtime.store._connect()
    conn.execute(
        "UPDATE client_automations SET status='paused' WHERE client_id=? AND business_id=?",
        (client_id, business_id),
    )
    conn.commit()
    conn.close()
    paused = _activate(client, auth, business_id)
    assert paused.status_code == 200
    assert paused.json()["workflow_id"] == "wf-same"
    assert calls == ["n8n"]


def test_other_client_same_location_is_409_and_skips_n8n(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth_a, client_a, biz_a = _prepare(client, "owner@example.com", LOCATION)
    auth_b, client_b, biz_b = _prepare(client, "other@example.com", LOCATION)
    calls: list[str] = []
    monkeypatch.setattr(
        api_module._n8n,
        "duplicate_template",
        lambda **kwargs: calls.append(kwargs["client_id"]) or "wf-owner",
    )
    owner = _activate(client, auth_a, biz_a)
    assert owner.status_code == 200
    taken = _activate(client, auth_b, biz_b)
    assert taken.status_code == 409
    assert taken.json()["detail"] == GBP_LOCATION_TAKEN_MESSAGE
    assert client_a not in taken.text
    assert "owner@example.com" not in taken.text
    assert "wf-owner" not in taken.text
    assert calls == [client_a]
    stored_b = api_module.runtime.store.get_automation(client_b, biz_b, "google_reviews")
    assert stored_b is None or stored_b["status"] not in ("active", "paused")


def test_paused_location_blocks_other_client(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth_a, client_a, biz_a = _prepare(client, "paused-owner@example.com", LOCATION)
    auth_b, _client_b, biz_b = _prepare(client, "paused-other@example.com", LOCATION)
    calls: list[int] = []
    monkeypatch.setattr(
        api_module._n8n,
        "duplicate_template",
        lambda **kwargs: calls.append(1) or "wf-paused",
    )
    assert _activate(client, auth_a, biz_a).status_code == 200
    conn = api_module.runtime.store._connect()
    conn.execute(
        "UPDATE client_automations SET status='paused' WHERE client_id=?",
        (client_a,),
    )
    conn.commit()
    conn.close()
    taken = _activate(client, auth_b, biz_b)
    assert taken.status_code == 409
    assert taken.json()["detail"] == GBP_LOCATION_TAKEN_MESSAGE
    assert calls == [1]


def test_inactive_location_can_be_claimed_by_another_client(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth_a, client_a, biz_a = _prepare(client, "old@example.com", LOCATION)
    auth_b, client_b, biz_b = _prepare(client, "new@example.com", LOCATION)
    monkeypatch.setattr(api_module._n8n, "duplicate_template", lambda **kwargs: "wf-new")
    assert _activate(client, auth_a, biz_a).status_code == 200
    conn = api_module.runtime.store._connect()
    conn.execute(
        "UPDATE client_automations SET status='inactive', n8n_workflow_id=NULL WHERE client_id=?",
        (client_a,),
    )
    conn.commit()
    conn.close()
    resp = _activate(client, auth_b, biz_b)
    assert resp.status_code == 200
    assert resp.json()["workflow_id"] == "wf-new"
    stored = api_module.runtime.store.get_automation(client_b, biz_b, "google_reviews")
    assert stored["n8n_workflow_id"] == "wf-new"


def test_activate_does_not_fall_back_to_creds_location(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id, business_id = _prepare(client, "nofallback@example.com", LOCATION)
    conn = api_module.runtime.store._connect()
    conn.execute(
        "UPDATE client_businesses SET location_id=? WHERE business_id=?",
        (f"default-{client_id}", business_id),
    )
    conn.execute(
        "UPDATE client_google_creds SET location_id=? WHERE client_id=?",
        (LOCATION, client_id),
    )
    conn.commit()
    conn.close()
    calls: list[str] = []
    monkeypatch.setattr(
        api_module._n8n,
        "duplicate_template",
        lambda **kwargs: calls.append("n8n") or "wf-no",
    )
    resp = _activate(client, auth, business_id)
    assert resp.status_code == 400
    assert "ficha válida" in resp.json()["detail"]
    assert calls == []


def test_ambiguous_locations_return_400_without_n8n(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id, _biz = _prepare(client, "ambi@example.com", LOCATION)
    api_module.runtime.store.sync_businesses(
        client_id,
        [
            {
                "google_account_id": "accounts/9",
                "location_id": LOCATION,
                "business_name": "Uno",
            },
            {
                "google_account_id": "accounts/9",
                "location_id": OTHER_LOCATION,
                "business_name": "Dos",
            },
        ],
    )
    calls: list[str] = []
    monkeypatch.setattr(
        api_module._n8n,
        "duplicate_template",
        lambda **kwargs: calls.append("n8n") or "wf-no",
    )
    resp = client.post("/client/automations/google_reviews/activate", headers=auth)
    assert resp.status_code == 400
    assert calls == []


def test_google_connect_conflict_is_409_without_n8n(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth_a, _client_a, biz_a = _prepare(client, "connect-owner@example.com", LOCATION)
    reg_b = _register(client, "connect-other@example.com")
    client_b = reg_b["client"]["client_id"]
    calls: list[str] = []
    monkeypatch.setattr(
        api_module._n8n,
        "duplicate_template",
        lambda **kwargs: calls.append("n8n") or "wf-connect",
    )
    assert _activate(client, auth_a, biz_a).status_code == 200
    assert calls == ["n8n"]
    monkeypatch.setattr(
        api_module._google_oauth,
        "exchange_code",
        lambda code, state: (
            client_b,
            {"access_token": "tok", "refresh_token": "reftok", "expires_in": 3600},
        ),
    )
    monkeypatch.setattr(api_module._google_oauth, "get_user_email", lambda token: "connect-other@example.com")
    monkeypatch.setattr(
        api_module._google_business,
        "list_businesses_for_creds",
        lambda creds: (
            [
                {
                    "google_account_id": "accounts/9",
                    "location_id": LOCATION,
                    "business_name": "Ficha",
                }
            ],
            None,
        ),
    )
    resp = client.get("/client/google/callback?code=abc&state=xyz", follow_redirects=False)
    assert resp.status_code == 409
    assert GBP_LOCATION_TAKEN_MESSAGE in resp.text
    assert "error=location_taken" in resp.text
    assert "connect-owner@example.com" not in resp.text
    assert calls == ["n8n"]


def test_portal_shows_location_taken_message(client: TestClient) -> None:
    page = client.get("/client")
    assert page.status_code == 200
    assert GBP_LOCATION_TAKEN_MESSAGE in page.text
    assert "params.get('error') === 'location_taken'" in page.text
    assert "showLocationTaken" in page.text


def test_concurrent_activations_only_one_calls_n8n(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth_a, _a, biz_a = _prepare(client, "race-a@example.com", LOCATION)
    auth_b, _b, biz_b = _prepare(client, "race-b@example.com", LOCATION)
    calls: list[str] = []
    lock = threading.Lock()

    def fake(**kwargs):
        with lock:
            calls.append(kwargs["client_id"])
        return "wf-" + kwargs["client_id"]

    monkeypatch.setattr(api_module._n8n, "duplicate_template", fake)
    barrier = threading.Barrier(2)

    def once(auth: dict, business_id: str):
        barrier.wait(timeout=5)
        with TestClient(api_module.app) as local:
            return local.post(
                f"/client/automations/google_reviews/activate?business_id={business_id}",
                headers=auth,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(once, auth_a, biz_a),
            pool.submit(once, auth_b, biz_b),
        ]
        results = [future.result(timeout=20) for future in futures]
    statuses = sorted(resp.status_code for resp in results)
    assert statuses == [200, 409]
    assert len(calls) == 1
    winner = next(resp for resp in results if resp.status_code == 200)
    loser = next(resp for resp in results if resp.status_code == 409)
    assert loser.json()["detail"] == GBP_LOCATION_TAKEN_MESSAGE
    assert winner.json()["workflow_id"] == "wf-" + calls[0]
    stored = api_module.runtime.store.get_automation_by_workflow(calls[0], winner.json()["workflow_id"])
    assert stored is not None
    assert stored["n8n_workflow_id"] == winner.json()["workflow_id"]


def test_migration_keeps_duplicate_live_locations(tmp_path: Path) -> None:
    db_path = tmp_path / "dup.db"
    store = DataStore(str(db_path))
    first = store.create_client("Uno", "uno@example.com", "secret123")
    second = store.create_client("Dos", "dos@example.com", "secret123")
    conn = sqlite3.connect(db_path)
    conn.execute(f"DROP INDEX IF EXISTS {LIVE_LOCATION_INDEX}")
    now = "2026-01-01T00:00:00+00:00"
    for client_id, workflow_id, business_id in (
        (first["client_id"], DUP_A, "BIZ-DUP-A"),
        (second["client_id"], DUP_B, "BIZ-DUP-B"),
    ):
        conn.execute(
            """
            INSERT INTO client_businesses
                (business_id, client_id, google_account_id, location_id, business_name, created_at)
            VALUES (?, ?, 'accounts/9', ?, 'Ficha', ?)
            """,
            (business_id, client_id, LOCATION, now),
        )
        conn.execute(
            """
            INSERT INTO client_automations
                (client_id, business_id, automation_type, n8n_workflow_id, status,
                 activated_at, reply_mode, location_id)
            VALUES (?, ?, 'google_reviews', ?, 'active', ?, 'approval', ?)
            """,
            (client_id, business_id, workflow_id, now, LOCATION),
        )
    conn.execute("DELETE FROM schema_version WHERE version >= 9")
    conn.commit()
    conn.close()

    reopened = DataStore(str(db_path))
    kept = _workflow_ids(db_path)
    assert kept == {DUP_A, DUP_B}
    assert _index_exists(db_path) is False
    assert _schema_version(db_path) >= 9

    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE client_automations SET status='inactive' WHERE n8n_workflow_id=?",
        (DUP_B,),
    )
    conn.commit()
    conn.close()
    DataStore(str(db_path))
    assert _index_exists(db_path) is True
    assert _workflow_ids(db_path) == {DUP_A, DUP_B}
    assert reopened is not None


def test_rename_command_targets_cdv_workflow_only() -> None:
    path = Path(__file__).resolve().parents[1] / "scripts" / "n8n_rename_cdv_workflow.py"
    spec = importlib.util.spec_from_file_location("n8n_rename_cdv_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    when = datetime(2026, 10, 15, 23, 30, tzinfo=ZoneInfo("Europe/Madrid"))
    assert module.target_workflow_name(when) == "CDV_Negocio01_20261015"
    assert module.WORKFLOW_ID == "1d0ZyxxIU3cPSlXg"
    assert "python scripts/n8n_rename_cdv_workflow.py" in (module.__doc__ or "")
    module.assert_workflow_allowed(module.WORKFLOW_ID)
    with pytest.raises(SystemExit):
        module.assert_workflow_allowed(DUP_A)
    with pytest.raises(SystemExit):
        module.assert_workflow_allowed(DUP_B)


def _workflow_ids(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT n8n_workflow_id FROM client_automations WHERE n8n_workflow_id IS NOT NULL"
    ).fetchall()
    conn.close()
    return {row[0] for row in rows}


def _index_exists(db_path: Path) -> bool:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (LIVE_LOCATION_INDEX,),
    ).fetchone()
    conn.close()
    return row is not None


def _schema_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    conn.close()
    return int(row[0] or 0)
