"""Contrato de la plantilla google_reviews (HTTP + staticData) y del nombre n8n."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from apps.integrations.n8n_client import (
    N8nClient,
    build_client_workflow_name,
    negocio_ordinal,
    sanitize_workflow_name_part,
)
from apps.integrations.n8n_folders import FOLDER_NAME, FOLDER_PLACEMENT_SKIPPED

TEMPLATE = Path("n8n/templates/google_reviews.json")
LOCATION = "accounts/1/locations/2"
WHEN = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def _response(status: int, *, payload: dict | list | None = None, text: str | None = None) -> httpx.Response:
    request = httpx.Request("GET", "http://n8n.test/api/v1")
    if text is not None:
        return httpx.Response(status, text=text, request=request)
    return httpx.Response(status, json=payload if payload is not None else {}, request=request)


def test_sanitize_and_single_business_name() -> None:
    assert sanitize_workflow_name_part("CDV Trading!!", "Cliente") == "CDVTrading"
    assert sanitize_workflow_name_part("---", "Cliente") == "Cliente"
    assert sanitize_workflow_name_part("José García", "Cliente") == "JoséGarcía"
    name = build_client_workflow_name("CDV Trading", ordinal=1, activated_at=WHEN)
    assert name == "CDVTrading_Negocio01_20261003"
    assert "Paris" not in name
    assert "Calle" not in name


def test_multi_business_ordinal_and_madrid_date() -> None:
    businesses = [
        {"business_id": "B-2", "created_at": "2026-02-01T00:00:00", "business_name": "Norte"},
        {"business_id": "B-1", "created_at": "2026-01-01T00:00:00", "business_name": "Calle Paris 1"},
    ]
    assert negocio_ordinal(businesses, "B-1") == 1
    assert negocio_ordinal(businesses, "B-2") == 2
    assert negocio_ordinal([{"business_id": "ONLY", "business_name": "Calle Paris 1"}], "ONLY") == 1
    tied = [
        {"business_id": "B-2", "created_at": "2026-01-01"},
        {"business_id": "B-1", "created_at": "2026-01-01"},
    ]
    assert negocio_ordinal(tied, "B-1") == 1
    assert negocio_ordinal(tied, "B-2") == 2
    late = datetime(2026, 10, 3, 23, 30, tzinfo=timezone.utc)
    assert build_client_workflow_name("CDV Trading", ordinal=2, activated_at=late).endswith(
        "_Negocio02_20261004"
    )


def test_template_has_contract_nodes_and_no_oauth_placeholders() -> None:
    raw = TEMPLATE.read_text(encoding="utf-8")
    wf = json.loads(raw)
    names = [node["name"] for node in wf["nodes"]]
    assert names.count("Generate AI Draft") == 1
    assert names.count("Post Reply to Google") == 1
    assert names.count("Push Draft to ZeroManual") == 1
    assert names.count("Publish Reply Webhook") == 1
    assert names.count("Build Draft Payload") == 1
    assert "CONFIGURACIÓN PENDIENTE" not in raw
    assert "YOUR_" not in raw
    assert "stickyNote" not in raw
    for node in wf["nodes"]:
        assert "google" not in node["type"].lower()
        assert "oauth" not in node["type"].lower()
        if node["name"] == "Call LLM":
            creds = node["credentials"]
            assert set(creds) == {"openAiApi"}
            assert creds["openAiApi"]["name"] == "OpenRouter - ZeroManual"
            assert creds["openAiApi"]["id"] == "HF8ZRnBsv79RuSZH"
            assert "apiKey" not in creds["openAiApi"]
        else:
            assert "credentials" not in node
    by_name = {node["name"]: node for node in wf["nodes"]}
    assert by_name["Exchange Google Access Token"]["type"] == "n8n-nodes-base.httpRequest"
    assert "oauth2.googleapis.com/token" in by_name["Exchange Google Access Token"]["parameters"]["url"]
    assert "mybusiness.googleapis.com/v4/" in by_name["List Google Reviews"]["parameters"]["url"]
    assert "/reply" in by_name["Post Reply to Google"]["parameters"]["jsCode"]
    assert wf["connections"]["Generate AI Draft"]["main"][0][0]["node"] == "Build Draft Payload"
    assert wf["connections"]["Build Draft Payload"]["main"][0][0]["node"] == "Push Draft to ZeroManual"
    assert wf["connections"]["Push Draft to ZeroManual"]["main"][0][0]["node"] == "Remember Drafted Review"
    assert wf["connections"]["Publish Reply Webhook"]["main"][0][0]["node"] == "Post Reply to Google"
    push = by_name["Push Draft to ZeroManual"]["parameters"]
    assert push["method"] == "POST"
    assert "/internal/automations/google_reviews/drafts" in push["url"]
    assert push["headerParameters"]["parameters"][0]["name"] == "X-Webhook-Secret"
    assert "$env.ZEROMANUAL_WEBHOOK_SECRET" in push["headerParameters"]["parameters"][0]["value"]
    assert by_name["Publish Reply Webhook"]["parameters"]["path"] == "publish-reply"
    assert "Generate AI Draft" in by_name["Remember Drafted Review"]["parameters"]["jsCode"]
    assert "change_me" not in raw
    assert "sk-" not in raw


def test_each_item_code_returns_object_and_openrouter_llm() -> None:
    """runOnceForEachItem must return one object. The task runner rejects arrays."""
    wf = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    by_name = {node["name"]: node for node in wf["nodes"]}
    for name in ("Normalize Review", "Generate AI Draft", "Build Draft Payload"):
        node = by_name[name]
        assert node["parameters"]["mode"] == "runOnceForEachItem"
        code = node["parameters"]["jsCode"]
        assert "return {" in code
        assert "return [{" not in code
    for name in ("Load Client Context", "Post Reply to Google"):
        node = by_name[name]
        assert node["parameters"]["mode"] == "runOnceForAllItems"
        assert "return [{" in node["parameters"]["jsCode"]

    draft = by_name["Generate AI Draft"]["parameters"]["jsCode"]
    assert "replace(/<think>" in draft
    llm = by_name["Call LLM"]
    assert llm["type"] == "n8n-nodes-base.httpRequest"
    params = llm["parameters"]
    assert params["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert params["authentication"] == "predefinedCredentialType"
    assert params["nodeCredentialType"] == "openAiApi"
    body = params["jsonBody"]
    assert "nvidia/nemotron-3-super-120b-a12b:free" in body
    assert "gemma-4-31b-it:free" in body
    assert "gemma-4-26b-a4b-it:free" in body
    assert "español de España" in body
    assert "idioma de la reseña" in body
    assert llm["retryOnFail"] is True
    assert llm["maxTries"] == 3
    assert llm["waitBetweenTries"] == 5000
    assert "qwen3" not in body
    assert "11434" not in params["url"]
    assert "availableInMCP" not in wf["settings"]


def test_template_injection_does_not_duplicate_baked_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    wf = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    n8n = N8nClient()
    before = [node["name"] for node in wf["nodes"]]
    n8n._inject_draft_push_node(wf, "CLI-ABC", "google_reviews", "BIZ-1")
    n8n._inject_publish_reply_webhook(wf, "CLI-ABC", "BIZ-1")
    assert [node["name"] for node in wf["nodes"]] == before
    assert [edge["node"] for edge in wf["connections"]["Generate AI Draft"]["main"][0]] == [
        "Build Draft Payload"
    ]
    assert wf["connections"]["Publish Reply Webhook"]["main"][0][0]["node"] == "Post Reply to Google"

    monkeypatch.setenv("N8N_WEBHOOK_CRED_ID", "cred-header-1")
    n8n._inject_draft_push_node(wf, "CLI-ABC", "google_reviews", "BIZ-1")
    push = next(node for node in wf["nodes"] if node["name"] == "Push Draft to ZeroManual")
    assert push["credentials"]["httpHeaderAuth"]["id"] == "cred-header-1"
    assert "headerParameters" not in push["parameters"]
    assert push["parameters"]["sendHeaders"] is False
    assert names_once(wf, "Push Draft to ZeroManual")


def names_once(wf: dict, name: str) -> bool:
    return sum(1 for node in wf["nodes"] if node["name"] == name) == 1


def test_injection_still_adds_push_on_legacy_graph() -> None:
    n8n = N8nClient()
    wf = {
        "nodes": [
            {"name": "Generate AI Draft", "type": "n8n-nodes-base.code", "parameters": {}},
            {"name": "Remember Drafted Review", "type": "n8n-nodes-base.code", "parameters": {}},
        ],
        "connections": {
            "Generate AI Draft": {
                "main": [[{"node": "Remember Drafted Review", "type": "main", "index": 0}]]
            }
        },
    }
    n8n._inject_draft_push_node(wf, "CLI-ABC", "google_reviews", "BIZ-1")
    targets = [edge["node"] for edge in wf["connections"]["Generate AI Draft"]["main"][0]]
    assert targets == ["Remember Drafted Review", "Push Draft to ZeroManual"]
    assert sum(1 for node in wf["nodes"] if node["name"] == "Push Draft to ZeroManual") == 1


def test_duplicate_template_names_static_data_and_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    n8n = N8nClient()
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    submitted: dict = {}
    monkeypatch.setattr(n8n, "ensure_client_folder", lambda: "fld-zeromanual")
    monkeypatch.setattr(n8n, "get_workflow", lambda template_id: template)
    monkeypatch.setattr(n8n, "activate_workflow", lambda workflow_id: submitted.setdefault("activated", workflow_id))

    def submit(wf: dict, folder_id: str) -> dict:
        submitted["wf"] = wf
        submitted["folder"] = folder_id
        return {"id": "wf-new"}

    monkeypatch.setattr(n8n, "_submit_workflow", submit)
    wf_id = n8n.duplicate_template(
        template_id="oju0vufPh9qyRqQs",
        client_id="CLI-A60A38F5",
        client_name="CDV Trading",
        refresh_token="refresh-not-a-secret-fixture",
        location_id=LOCATION,
        automation_type="google_reviews",
        business_id="BIZ-1",
        business_ordinal=1,
        activated_at=WHEN,
    )
    assert wf_id == "wf-new"
    assert submitted["folder"] == "fld-zeromanual"
    assert submitted["activated"] == "wf-new"
    wf = submitted["wf"]
    assert wf["name"] == "CDVTrading_Negocio01_20261003"
    assert "oju0vufPh9qyRqQs" not in wf["name"]
    assert wf["staticData"]["refresh_token"] == "refresh-not-a-secret-fixture"
    assert wf["staticData"]["global"]["location_id"] == LOCATION
    assert wf["staticData"]["global"]["client_name"] == "CDV Trading"
    assert wf["staticData"]["client_id"] == "CLI-A60A38F5"
    assert wf["staticData"]["global"]["client_id"] == "CLI-A60A38F5"
    assert wf["staticData"]["global"]["business_id"] == "BIZ-1"
    push_nodes = [node for node in wf["nodes"] if node["name"] == "Push Draft to ZeroManual"]
    assert len(push_nodes) == 1
    webhook = next(node for node in wf["nodes"] if node["name"] == "Publish Reply Webhook")
    assert webhook["parameters"]["path"] == "publish-reply-cli-a60a38f5-biz-1"
    assert wf["connections"]["Generate AI Draft"]["main"][0][0]["node"] == "Build Draft Payload"
    assert wf["connections"]["Publish Reply Webhook"]["main"][0][0]["node"] == "Post Reply to Google"


def test_submit_falls_back_to_put_parent_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    n8n = N8nClient()
    calls: list[tuple[str, str]] = []

    def post(url: str, headers=None, json=None, timeout=None):  # noqa: A002
        calls.append(("POST", url))
        if json and "parentFolderId" in json:
            return _response(400, text='{"message":"must NOT have additional properties parentFolderId"}')
        return _response(200, payload={"id": "wf-9"})

    def put(url: str, headers=None, json=None, timeout=None):  # noqa: A002
        calls.append(("PUT", url))
        assert json["parentFolderId"] == "fld-1"
        assert json["name"] == "CDVTrading_Negocio01_20261003"
        return _response(200, payload={"id": "wf-9"})

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "put", put)
    created = n8n._submit_workflow(
        {"name": "CDVTrading_Negocio01_20261003", "nodes": [], "connections": {}, "settings": {}},
        "fld-1",
    )
    assert created["id"] == "wf-9"
    assert ("PUT", f"{n8n._base}/workflows/wf-9") in calls


def test_submit_deletes_copy_when_move_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    n8n = N8nClient()
    deleted: list[str] = []

    def post(url: str, headers=None, json=None, timeout=None):  # noqa: A002
        if json and "parentFolderId" in json:
            return _response(400, text="parentFolderId additional properties")
        return _response(200, payload={"id": "wf-orphan"})

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "put", lambda *a, **k: _response(404, text="missing"))
    monkeypatch.setattr(n8n, "delete_workflow", lambda workflow_id: deleted.append(workflow_id))
    with pytest.raises(RuntimeError, match="Zeromanual"):
        n8n._submit_workflow({"name": "n", "nodes": [], "connections": {}, "settings": {}}, "fld")
    assert deleted == ["wf-orphan"]


def test_folder_lookup_creates_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("N8N_PROJECT_ID", raising=False)
    n8n = N8nClient()
    seen: list[tuple[str, str]] = []

    def request(method: str, url: str, headers=None, params=None, json=None, timeout=None):  # noqa: A002
        seen.append((method, url))
        if method == "GET" and url.endswith("/projects"):
            return _response(200, payload={"data": [{"id": "proj-1", "type": "personal"}], "nextCursor": None})
        if method == "GET" and url.endswith("/projects/proj-1/folders"):
            return _response(200, payload={"data": [], "count": 0})
        if method == "POST" and url.endswith("/projects/proj-1/folders"):
            assert json == {"name": FOLDER_NAME}
            return _response(201, payload={"id": "fld-new", "name": FOLDER_NAME})
        raise AssertionError(f"unexpected {method} {url}")

    monkeypatch.setattr(httpx, "request", request)
    assert n8n.ensure_client_folder() == "fld-new"
    assert any(method == "POST" for method, _url in seen)


def test_folder_reuses_exact_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("N8N_PROJECT_ID", "proj-9")
    n8n = N8nClient()

    def request(method: str, url: str, headers=None, params=None, json=None, timeout=None):  # noqa: A002
        assert method == "GET"
        assert params["filter"] == json_mod({"name": "Zeromanual"})
        return _response(
            200,
            payload={
                "count": 2,
                "data": [
                    {"id": "other", "name": "Otra"},
                    {"id": "fld-z", "name": "Zeromanual"},
                ],
            },
        )

    monkeypatch.setattr(httpx, "request", request)
    assert n8n.ensure_client_folder() == "fld-z"


def json_mod(payload: dict) -> str:
    return json.dumps(payload)


@pytest.mark.parametrize("status", [403, 404])
@pytest.mark.parametrize("project_id", [None, "proj-1"])
def test_duplicate_template_skips_folder_on_projects_or_folders_denied(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: int,
    project_id: str | None,
) -> None:
    """403/404 on projects or folders must not abort clone or activate."""
    monkeypatch.delenv("N8N_PROJECT_ID", raising=False)
    if project_id:
        monkeypatch.setenv("N8N_PROJECT_ID", project_id)
    n8n = N8nClient()
    folder_calls: list[str] = []
    created: list[dict] = []
    activated: list[str] = []
    template = {"name": "tpl", "nodes": [], "connections": {}, "settings": {}}

    def request(method: str, url: str, headers=None, params=None, json=None, timeout=None):  # noqa: A002
        folder_calls.append(url)
        return _response(status, text="folder api denied")

    def get(url: str, headers=None, timeout=None):
        assert url.endswith("/workflows/tpl-1")
        return _response(200, payload=template)

    def post(url: str, headers=None, json=None, timeout=None):  # noqa: A002
        if url.endswith("/activate"):
            activated.append(url)
            return _response(200, payload={})
        created.append(json or {})
        return _response(200, payload={"id": "wf-skipped"})

    monkeypatch.setattr(httpx, "request", request)
    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(httpx, "post", post)

    with caplog.at_level(logging.WARNING, logger="apps.integrations.n8n_folders"):
        assert n8n.ensure_client_folder() is None
        wf_id = n8n.duplicate_template(
            template_id="tpl-1",
            client_id="CLI-A60A38F5",
            client_name="CDV Trading",
            refresh_token="refresh-not-a-secret-fixture",
            location_id=LOCATION,
            automation_type="google_reviews",
            business_id="BIZ-1992869B7402",
            business_ordinal=1,
            activated_at=WHEN,
        )

    assert wf_id == "wf-skipped"
    assert created and "parentFolderId" not in created[0]
    assert created[0]["name"] == "CDVTrading_Negocio01_20261003"
    assert activated == [f"{n8n._base}/workflows/wf-skipped/activate"]
    assert any(FOLDER_PLACEMENT_SKIPPED in record.message for record in caplog.records)
    if project_id:
        assert any(url.endswith(f"/projects/{project_id}/folders") for url in folder_calls)
    else:
        assert any(url.endswith("/projects") for url in folder_calls)
        assert not any("/folders" in url for url in folder_calls)


@pytest.mark.parametrize("status", [403, 404])
def test_folder_create_denied_still_clones_without_parent(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    monkeypatch.setenv("N8N_PROJECT_ID", "proj-1")
    n8n = N8nClient()
    created: list[dict] = []

    def request(method: str, url: str, headers=None, params=None, json=None, timeout=None):  # noqa: A002
        if method == "GET" and url.endswith("/projects/proj-1/folders"):
            return _response(200, payload={"data": [], "count": 0})
        if method == "POST" and url.endswith("/projects/proj-1/folders"):
            return _response(status, text="cannot create folder")
        raise AssertionError(f"unexpected {method} {url}")

    def post(url: str, headers=None, json=None, timeout=None):  # noqa: A002
        if url.endswith("/activate"):
            return _response(200, payload={})
        created.append(json or {})
        return _response(200, payload={"id": "wf-root"})

    monkeypatch.setattr(httpx, "request", request)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: _response(
            200, payload={"name": "tpl", "nodes": [], "connections": {}, "settings": {}}
        ),
    )
    monkeypatch.setattr(httpx, "post", post)
    wf_id = n8n.duplicate_template(
        template_id="tpl-1",
        client_id="CLI-1",
        client_name="CDV Trading",
        refresh_token="rt",
        location_id=LOCATION,
        automation_type="google_reviews",
        business_id="BIZ-1",
        business_ordinal=1,
        activated_at=WHEN,
    )
    assert wf_id == "wf-root"
    assert created and "parentFolderId" not in created[0]
    assert n8n.ensure_client_folder() is None


def test_projects_server_error_still_aborts_clone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("N8N_PROJECT_ID", raising=False)
    n8n = N8nClient()
    created: list[str] = []

    monkeypatch.setattr(httpx, "request", lambda *a, **k: _response(500, text="boom"))
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _response(200, payload={"nodes": []}))
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: created.append("post") or _response(200, payload={"id": "nope"}),
    )
    with pytest.raises(httpx.HTTPStatusError):
        n8n.duplicate_template(
            template_id="tpl-1",
            client_id="CLI-1",
            client_name="CDV Trading",
            refresh_token="rt",
            location_id=LOCATION,
            automation_type="google_reviews",
            business_id="BIZ-1",
        )
    assert created == []


def test_missing_template_still_fails_after_folder_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("N8N_PROJECT_ID", raising=False)
    n8n = N8nClient()
    created: list[str] = []
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _response(403, text="forbidden"))
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _response(404, text="missing template"))
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: created.append("post") or _response(200, payload={"id": "nope"}),
    )
    with pytest.raises(httpx.HTTPStatusError):
        n8n.duplicate_template(
            template_id="tpl-missing",
            client_id="CLI-1",
            client_name="CDV Trading",
            refresh_token="rt",
            location_id=LOCATION,
            automation_type="google_reviews",
            business_id="BIZ-1",
        )
    assert n8n.ensure_client_folder() is None
    assert created == []


def test_activate_threads_ordinal_not_display_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.interface.payments import activate_automation_for_client

    monkeypatch.setattr(
        "apps.interface.payments.stripe_payments.stripe_enabled",
        lambda settings=None: False,
    )
    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    captured: dict = {}

    class Store:
        def get_google_creds(self, client_id: str) -> dict:
            return {"refresh_token": "rt", "location_id": LOCATION}

        def get_automation(self, *args, **kwargs):
            return None

        def get_business(self, business_id: str) -> dict:
            return {
                "business_id": business_id,
                "location_id": LOCATION,
                "business_name": "Calle Paris 1",
            }

        def list_businesses(self, client_id: str) -> list[dict]:
            return [
                {"business_id": "B-1", "created_at": "2026-01-01", "business_name": "Calle Paris 1"},
                {"business_id": "B-2", "created_at": "2026-02-01", "business_name": "Norte"},
            ]

        def activate_automation(self, *args, **kwargs) -> dict:
            return {"status": "active"}

    class N8n:
        def duplicate_template(self, **kwargs):
            captured.update(kwargs)
            return "wf-1"

    activate_automation_for_client(
        store=Store(),
        n8n=N8n(),
        client_id="CLI-1",
        client_name="CDV Trading",
        automation_type="google_reviews",
        business_id="B-2",
    )
    assert captured["business_ordinal"] == 2
    assert "business_name" not in captured
    assert captured["location_id"] == LOCATION
