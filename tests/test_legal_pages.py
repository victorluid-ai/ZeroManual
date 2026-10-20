"""Rutas públicas de aviso legal, privacidad, cookies y términos."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.interface.legal import _GOOGLE_LIMITED_USE

_PATHS = ("/aviso-legal", "/privacidad", "/cookies", "/terminos")
_GOOGLE_POLICY = "https://developers.google.com/terms/api-services-user-data-policy"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")
    import importlib
    import apps.interface.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


@pytest.mark.parametrize("path", _PATHS)
def test_legal_pages_are_spanish_and_name_exmanual(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    text = resp.text
    assert '<html lang="es">' in text
    assert "ExManual" in text
    assert "hola@exmanual.com" in text
    for href in _PATHS:
        assert f'href="{href}"' in text


def test_aviso_legal_marks_founder_data_pending(client: TestClient) -> None:
    text = client.get("/aviso-legal").text
    assert "LSSI" in text
    for label in ("Titular", "NIF", "Domicilio", "Datos registrales", "autónomo o sociedad"):
        assert label in text
    assert text.count("[PENDIENTE]") >= 5


def test_privacidad_covers_gdpr_google_and_processors(client: TestClient) -> None:
    text = client.get("/privacidad").text
    assert "RGPD" in text
    assert "LOPDGDD" in text
    assert _GOOGLE_LIMITED_USE in text
    assert _GOOGLE_POLICY in text
    for name in ("Stripe", "Google", "Hostinger", "OpenRouter", "Anthropic", "n8n"):
        assert name in text
    assert "business.manage" in text
    assert "no usa Gmail" in text or "no usa Gmail".lower() in text.lower()
    assert "www.aepd.es" in text
    assert "[PENDIENTE]" in text
    assert "[REVISAR]" in text


def test_cookies_page_lists_only_technical_storage(client: TestClient) -> None:
    text = client.get("/cookies").text
    assert "No hay cookies de análisis" in text
    assert "no muestra un banner" in text
    for key in (
        "mz_client_token",
        "mz_token",
        "zm_pending_activations",
        "zm_currency",
        "zm_tweaks",
    ):
        assert key in text
    assert "Técnica" in text
    assert "cookieconsent" not in text.lower()
    assert "Aceptar cookies" not in text


def test_terminos_use_catalog_prices_and_review_notes(client: TestClient) -> None:
    text = client.get("/terminos").text
    assert "14 días" in text
    assert "21" in text
    for price in ("29,00", "39,00", "24,00", "34,00"):
        assert price in text
    assert "Cancelar suscripción" in text
    assert "aprobación" in text
    assert "automáticas" in text
    assert "ley española" in text
    assert "[REVISAR]" in text
    assert "B2B" in text


def test_landing_and_portal_link_the_legal_pages(client: TestClient) -> None:
    landing = client.get("/").text
    assert 'src="/assets/app.jsx?v=14"' in landing
    js = client.get("/assets/app.jsx").text
    for href in _PATHS:
        assert f'href="{href}"' in js
    assert "function LegalPair()" in js
    portal = client.get("/client").text
    for href in _PATHS:
        assert f'href="{href}"' in portal
    assert 'class="portal-legal"' in portal
    assert 'class="legal-inline"' in portal
