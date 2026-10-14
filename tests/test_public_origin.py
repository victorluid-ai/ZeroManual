"""Allowlisted public origins for the exmanual.com transition."""

from __future__ import annotations

import pytest

from apps.integrations.public_origin import oauth_redirect_uri, origin_for_request


@pytest.fixture(autouse=True)
def _clear_public_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "ZEROMANUAL_PUBLIC_HOSTS",
        "MANUALZERO_PUBLIC_HOSTS",
        "ZEROMANUAL_PUBLIC_URL",
        "MANUALZERO_PUBLIC_URL",
        "GOOGLE_REDIRECT_URI",
    ):
        monkeypatch.delenv(key, raising=False)


def test_www_canonicalizes_to_apex() -> None:
    origin = origin_for_request(
        host="www.exmanual.com",
        forwarded_host=None,
        forwarded_proto="http",
        fallback="https://app.srv1255804.hstgr.cloud",
    )
    assert origin == "https://exmanual.com"


def test_old_host_stays_on_old_host_when_public_url_is_exmanual() -> None:
    origin = origin_for_request(
        host="app.srv1255804.hstgr.cloud",
        forwarded_host=None,
        forwarded_proto=None,
        fallback="https://exmanual.com",
    )
    assert origin == "https://app.srv1255804.hstgr.cloud"


def test_unknown_host_uses_fallback_even_if_forwarded_host_is_spoofed() -> None:
    origin = origin_for_request(
        host="exmanual.com",
        forwarded_host="evil.example",
        forwarded_proto="https",
        fallback="https://app.srv1255804.hstgr.cloud",
    )
    assert origin == "https://exmanual.com"

    blocked = origin_for_request(
        host="evil.example",
        forwarded_host="also-evil.example",
        forwarded_proto="https",
        fallback="https://exmanual.com",
    )
    assert blocked == "https://exmanual.com"


def test_localhost_keeps_the_configured_scheme_and_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZEROMANUAL_PUBLIC_URL", "http://localhost:8090")
    origin = origin_for_request(
        host="localhost:8090",
        forwarded_host=None,
        forwarded_proto="https",
        fallback="http://localhost:8090",
    )
    assert origin == "http://localhost:8090"


def test_public_hosts_env_can_drop_the_old_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_PUBLIC_HOSTS", "exmanual.com,www.exmanual.com")
    origin = origin_for_request(
        host="app.srv1255804.hstgr.cloud",
        forwarded_host=None,
        forwarded_proto="https",
        fallback="https://exmanual.com",
    )
    assert origin == "https://exmanual.com"


def test_oauth_redirect_follows_host_and_keeps_the_callback_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "https://app.srv1255804.hstgr.cloud/client/google/callback",
    )
    assert (
        oauth_redirect_uri(
            host="exmanual.com",
            forwarded_host=None,
            forwarded_proto="https",
        )
        == "https://exmanual.com/client/google/callback"
    )
    assert (
        oauth_redirect_uri(
            host="testserver",
            forwarded_host=None,
            forwarded_proto=None,
        )
        == "https://app.srv1255804.hstgr.cloud/client/google/callback"
    )
