"""La fecha del nombre n8n es la de activación, en Europe/Madrid."""

from __future__ import annotations

import importlib.util
import sqlite3
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from apps.integrations.n8n_client import N8nClient, build_client_workflow_name
from apps.interface.google_reviews_activation import activate_google_reviews_for_client

LOCATION = "accounts/1/locations/2"
ACTIVATED = "2026-10-05T10:00:00+00:00"
CREATED_UTC_EDGE = "2026-10-04T23:30:00Z"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "n8n_rename_cdv_workflow.py"


def _load_rename_script():
    spec = importlib.util.spec_from_file_location("n8n_rename_cdv_workflow", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_clone_name_uses_activated_at_not_today() -> None:
    name = build_client_workflow_name("CDV", ordinal=1, activated_at=ACTIVATED)
    assert name == "CDV_Negocio01_20261005"


def test_clone_name_falls_back_to_created_at() -> None:
    name = build_client_workflow_name(
        "CDV",
        ordinal=1,
        created_at="2026-10-04T23:30:00.000Z",
    )
    assert name == "CDV_Negocio01_20261005"


def test_utc_midnight_edge_is_next_madrid_day() -> None:
    """2026-10-04T23:30Z is 01:30 on 5 October in Europe/Madrid."""
    assert build_client_workflow_name("CDV", created_at=CREATED_UTC_EDGE) == "CDV_Negocio01_20261005"
    aware = datetime.fromisoformat("2026-10-04T23:30:00+00:00")
    assert build_client_workflow_name("CDV Trading", ordinal=2, activated_at=aware).endswith(
        "_Negocio02_20261005"
    )


def test_activated_at_wins_over_created_at() -> None:
    name = build_client_workflow_name(
        "CDV",
        activated_at=ACTIVATED,
        created_at="2026-01-01T00:00:00Z",
    )
    assert name == "CDV_Negocio01_20261005"


def test_duplicate_template_uses_created_at_when_activation_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    n8n = N8nClient()
    stored: dict = {}
    monkeypatch.setattr(n8n, "ensure_client_folder", lambda: None)
    monkeypatch.setattr(
        n8n,
        "get_workflow",
        lambda template_id: {"nodes": [], "connections": {}, "settings": {}},
    )

    def create(wf: dict) -> dict:
        stored["created_name"] = wf["name"]
        return {"id": "wf-new", "createdAt": CREATED_UTC_EDGE}

    def put(workflow_id: str, wf: dict, folder_id: str | None) -> None:
        stored["renamed"] = wf["name"]
        stored["workflow_id"] = workflow_id
        stored["folder"] = folder_id

    monkeypatch.setattr(n8n, "create_workflow", create)
    monkeypatch.setattr(n8n, "_put_named_workflow", put)
    monkeypatch.setattr(n8n, "activate_workflow", lambda workflow_id: stored.setdefault("activated", workflow_id))
    wf_id = n8n.duplicate_template(
        template_id="tpl",
        client_id="CLI-1",
        client_name="CDV",
        refresh_token="rt",
        location_id=None,
        business_ordinal=1,
    )
    assert wf_id == "wf-new"
    assert stored["created_name"] == "CDV"
    assert stored["renamed"] == "CDV_Negocio01_20261005"
    assert stored["folder"] is None
    assert stored["activated"] == "wf-new"


def test_duplicate_template_keeps_activated_at_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    n8n = N8nClient()
    stored: dict = {}
    monkeypatch.setattr(n8n, "ensure_client_folder", lambda: None)
    monkeypatch.setattr(
        n8n,
        "get_workflow",
        lambda template_id: {"nodes": [], "connections": {}, "settings": {}},
    )
    def create(wf: dict) -> dict:
        stored["name"] = wf["name"]
        return {"id": "wf-act", "createdAt": "2020-01-01T00:00:00Z"}

    monkeypatch.setattr(n8n, "create_workflow", create)

    def refuse_rename(*_args, **_kwargs) -> None:
        raise AssertionError("no debe renombrar si hay activated_at")

    monkeypatch.setattr(n8n, "_put_named_workflow", refuse_rename)
    monkeypatch.setattr(n8n, "activate_workflow", lambda workflow_id: None)
    wf_id = n8n.duplicate_template(
        template_id="tpl",
        client_id="CLI-1",
        client_name="CDV",
        refresh_token="rt",
        location_id=None,
        business_ordinal=1,
        activated_at=ACTIVATED,
        created_at="2020-01-01T00:00:00Z",
    )
    assert wf_id == "wf-act"
    assert stored["name"] == "CDV_Negocio01_20261005"


def test_activation_passes_stored_activated_at() -> None:
    captured: dict = {}

    class Store:
        def get_business(self, business_id: str) -> dict:
            return {"business_id": business_id, "location_id": LOCATION}

        def list_businesses(self, client_id: str) -> list[dict]:
            return [{"business_id": "B-1", "created_at": "2026-01-01", "location_id": LOCATION}]

        def begin_google_reviews_claim(self, client_id: str, business_id: str, location_id: str) -> dict:
            return {
                "action": "reserve",
                "business_id": business_id,
                "automation": {"activated_at": ACTIVATED},
            }

        def bind_google_reviews_workflow(
            self, client_id: str, business_id: str, workflow_id: str, location_id: str
        ) -> dict:
            return {"status": "active", "n8n_workflow_id": workflow_id}

        def abort_google_reviews_claim(self, client_id: str, business_id: str) -> None:
            raise AssertionError("la activación válida no debe liberar la reserva")

    class N8n:
        def duplicate_template(self, **kwargs):
            captured.update(kwargs)
            return "wf-1"

    activate_google_reviews_for_client(
        store=Store(),
        n8n=N8n(),
        client_id="CLI-1",
        client_name="CDV",
        business_id="B-1",
        refresh_token="rt",
        template_id="tpl",
    )
    assert captured["activated_at"] == ACTIVATED
    assert captured["business_ordinal"] == 1


def _automation_db(path: Path, activated_at: str | None) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE client_automations (n8n_workflow_id TEXT, activated_at TEXT)"
    )
    if activated_at is not None:
        conn.execute(
            "INSERT INTO client_automations (n8n_workflow_id, activated_at) VALUES (?, ?)",
            ("1d0ZyxxIU3cPSlXg", activated_at),
        )
    conn.commit()
    conn.close()


def _response(status: int, payload: dict) -> httpx.Response:
    request = httpx.Request("GET", "http://n8n.test/api/v1/workflows/1d0ZyxxIU3cPSlXg")
    return httpx.Response(status, json=payload, request=request)


def test_rename_uses_activated_at_and_does_not_print_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load_rename_script()
    db = tmp_path / "rename.db"
    _automation_db(db, ACTIVATED)
    bodies: list[dict] = []
    secret = "n8n-key-must-stay-out-of-stdout"

    def get(url: str, headers=None, timeout=None):
        assert headers["X-N8N-API-KEY"] == secret
        return _response(
            200,
            {"nodes": [], "connections": {}, "settings": {}, "createdAt": "2020-01-01T00:00:00.000Z"},
        )

    def put(url: str, headers=None, json=None, timeout=None):  # noqa: A002
        bodies.append(json)
        return _response(200, {"name": json["name"]})

    monkeypatch.setenv("N8N_API_URL", "http://n8n.test/api/v1")
    monkeypatch.setenv("N8N_API_KEY", secret)
    monkeypatch.setattr(module.httpx, "get", get)
    monkeypatch.setattr(module.httpx, "put", put)
    module.rename_workflow(module.WORKFLOW_ID, "", db_path=str(db))
    assert bodies[0]["name"] == "CDV_Negocio01_20261005"
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_rename_falls_back_to_created_at_at_midnight_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_rename_script()
    db = tmp_path / "empty.db"
    _automation_db(db, None)
    bodies: list[dict] = []

    def get(url: str, headers=None, timeout=None):
        return _response(
            200,
            {
                "nodes": [{"name": "Keep"}],
                "connections": {},
                "settings": {},
                "staticData": {},
                "createdAt": "2026-10-04T23:30:00.000Z",
            },
        )

    def put(url: str, headers=None, json=None, timeout=None):  # noqa: A002
        bodies.append(json)
        return _response(200, {"name": json["name"]})

    monkeypatch.setenv("N8N_API_URL", "http://n8n.test/api/v1")
    monkeypatch.setenv("N8N_API_KEY", "n8n-key-must-stay-out-of-stdout")
    monkeypatch.setattr(module.httpx, "get", get)
    monkeypatch.setattr(module.httpx, "put", put)
    module.rename_workflow(module.WORKFLOW_ID, "", db_path=str(db))
    assert bodies[0]["name"] == "CDV_Negocio01_20261005"
    assert bodies[0]["nodes"] == [{"name": "Keep"}]


def test_rename_command_date_matches_clone_rule() -> None:
    module = _load_rename_script()
    assert module.target_workflow_name(activated_at=ACTIVATED) == "CDV_Negocio01_20261005"
    assert module.target_workflow_name(created_at=CREATED_UTC_EDGE) == "CDV_Negocio01_20261005"
    with pytest.raises(ValueError):
        module.target_workflow_name()
