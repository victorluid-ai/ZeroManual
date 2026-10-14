from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from apps.integrations.google_oauth import (
    PURPOSE_BUSINESS,
    SCOPE_BUSINESS_MANAGE,
    SCOPE_USERINFO_EMAIL,
    SCOPES_BY_PURPOSE,
    GoogleOAuthHelper,
)


def test_business_purpose_scopes_include_email_identity() -> None:
    scopes = SCOPES_BY_PURPOSE[PURPOSE_BUSINESS].split()
    assert SCOPE_BUSINESS_MANAGE in scopes
    assert SCOPE_USERINFO_EMAIL in scopes
    assert "openid" in scopes


def test_business_auth_url_includes_userinfo_email_and_business_manage() -> None:
    helper = GoogleOAuthHelper()
    url = helper.get_authorization_url("CLI-TEST")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    scopes = (qs.get("scope") or [""])[0].split()
    assert SCOPE_BUSINESS_MANAGE in scopes
    assert SCOPE_USERINFO_EMAIL in scopes
    assert "openid" in scopes
    assert qs.get("access_type") == ["offline"]
    assert qs.get("prompt") == ["consent"]
    assert qs.get("response_type") == ["code"]
    assert (qs.get("state") or [""])[0]


def test_exchange_reuses_the_redirect_uri_sent_to_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "sec")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "https://app.srv1255804.hstgr.cloud/client/google/callback",
    )
    helper = GoogleOAuthHelper()
    new_uri = "https://exmanual.com/client/google/callback"
    url = helper.get_authorization_url("CLI-1", redirect_uri=new_uri)
    state = parse_qs(urlparse(url).query)["state"][0]
    assert parse_qs(urlparse(url).query)["redirect_uri"] == [new_uri]

    captured: dict = {}

    class _Response:
        is_success = True

        @staticmethod
        def json() -> dict:
            return {"access_token": "tok"}

    def fake_post(url: str, data: dict, timeout: int) -> _Response:
        captured["url"] = url
        captured["data"] = data
        return _Response()

    monkeypatch.setattr("apps.integrations.google_oauth.httpx.post", fake_post)
    client_id, tokens = helper.exchange_code("auth-code", state)
    assert client_id == "CLI-1"
    assert tokens["access_token"] == "tok"
    assert captured["data"]["redirect_uri"] == new_uri
    assert captured["data"]["redirect_uri"] != helper._redirect_uri


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("MANUALZERO_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "https://app.srv1255804.hstgr.cloud/client/google/callback",
    )
    import importlib

    import apps.interface.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


def test_google_connect_redirect_follows_the_browser_host(client: TestClient) -> None:
    reg = client.post(
        "/client/register",
        json={"name": "OAuth Biz", "email": "oauth-host@example.com", "password": "secret123"},
    )
    assert reg.status_code == 200
    auth = {"Authorization": f"Bearer {reg.json()['token']}"}

    old = client.get(
        "/client/google/connect",
        headers={**auth, "x-forwarded-host": "app.srv1255804.hstgr.cloud"},
    )
    new = client.get(
        "/client/google/connect",
        headers={**auth, "x-forwarded-host": "exmanual.com"},
    )
    assert old.status_code == 200
    assert new.status_code == 200
    old_qs = parse_qs(urlparse(old.json()["redirect_url"]).query)
    new_qs = parse_qs(urlparse(new.json()["redirect_url"]).query)
    assert old_qs["redirect_uri"] == [
        "https://app.srv1255804.hstgr.cloud/client/google/callback"
    ]
    assert new_qs["redirect_uri"] == ["https://exmanual.com/client/google/callback"]
