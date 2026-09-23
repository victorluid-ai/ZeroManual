"""Tests unitarios del servicio (modo demo, sin Supabase)."""

from __future__ import annotations

import os

import pytest

# Forzar demo antes de importar el servicio
os.environ["MANTENIMIENTO_DEMO_MODE"] = "true"
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)

from apps.mantenimiento.app.config import get_settings
from apps.mantenimiento.app.db import get_demo
from apps.mantenimiento.app.services import MaintenanceService


@pytest.fixture(autouse=True)
def _reset_cache():
    get_settings.cache_clear()
    import apps.mantenimiento.app.db as db

    db._demo = None
    yield
    get_settings.cache_clear()
    db._demo = None


def test_dashboard_counts():
    svc = MaintenanceService()
    assert svc.is_demo
    group = svc.resolve_group()
    data = svc.dashboard(group["id"])
    assert data["restaurants_count"] == 3
    assert data["equipment_count"] == 6
    assert data["overdue_count"] >= 1
    assert data["alarms_count"] >= 1


def test_create_equipment_creates_plan():
    svc = MaintenanceService()
    group = svc.resolve_group()
    restaurants = svc.list_restaurants(group["id"])
    types = svc.list_equipment_types()
    created = svc.create_equipment(
        restaurant_id=restaurants[0]["id"],
        equipment_type_id=types[0]["id"],
        name="Horno test",
        brand="TestBrand",
        model="T-1",
        serial_number="SN-1",
        location_note="Cocina",
    )
    assert created["name"] == "Horno test"
    upcoming = svc.upcoming(group["id"])
    assert any(u["equipment_name"] == "Horno test" for u in upcoming)


def test_complete_plan_resolves_alarm():
    svc = MaintenanceService()
    group = svc.resolve_group()
    upcoming = svc.upcoming(group["id"])
    overdue = next(u for u in upcoming if u["urgency"] == "vencido")
    svc.complete_plan(overdue["plan_id"], performed_by="Ana", notes="OK")
    alarms = svc.list_alarms(group["id"])
    assert all(a.get("plan_id") != overdue["plan_id"] for a in alarms)


def test_health_endpoint():
    from fastapi.testclient import TestClient
    from apps.mantenimiento.app.main import app

    client = TestClient(app)
    res = client.get("/salud")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["demo"] is True


def test_panel_renders():
    from fastapi.testclient import TestClient
    from apps.mantenimiento.app.main import app

    client = TestClient(app)
    res = client.get("/panel")
    assert res.status_code == 200
    assert "Panel de preventivo" in res.text
    assert "Mantenimiento" in res.text
