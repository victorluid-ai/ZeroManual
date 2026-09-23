"""Cliente Supabase (PostgREST) vía httpx — sin React, backend serio."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from apps.mantenimiento.app.config import Settings, get_settings


class SupabaseError(RuntimeError):
    pass


class SupabaseClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.supabase_configured:
            raise SupabaseError(
                "Faltan SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY. "
                "Configúralos en .env (ver apps/mantenimiento/.env.example)."
            )
        self._base = f"{self.settings.supabase_url}/rest/v1"
        self._headers = {
            "apikey": self.settings.supabase_service_key,
            "Authorization": f"Bearer {self.settings.supabase_service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
        prefer: str | None = None,
    ) -> Any:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                method,
                f"{self._base}/{path.lstrip('/')}",
                headers=headers,
                params=params,
                json=json,
            )
        if response.status_code >= 400:
            raise SupabaseError(
                f"Supabase {method} {path} → {response.status_code}: {response.text}"
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def select(
        self,
        table: str,
        *,
        select: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": select}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        data = self._request("GET", table, params=params)
        return data or []

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", table, json=row)
        if isinstance(data, list):
            return data[0]
        return data

    def update(
        self, table: str, filters: dict[str, str], values: dict[str, Any]
    ) -> list[dict[str, Any]]:
        data = self._request("PATCH", table, params=filters, json=values)
        return data or []

    def delete(self, table: str, filters: dict[str, str]) -> None:
        self._request("DELETE", table, params=filters, prefer="return=minimal")

    def rpc(self, fn: str, args: dict[str, Any] | None = None) -> Any:
        url = f"{self.settings.supabase_url}/rest/v1/rpc/{fn}"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url, headers=self._headers, json=args or {}
            )
        if response.status_code >= 400:
            raise SupabaseError(
                f"RPC {fn} → {response.status_code}: {response.text}"
            )
        if not response.content:
            return None
        return response.json()


class DemoStore:
    """Almacén en memoria para demo local sin proyecto Supabase."""

    def __init__(self) -> None:
        today = date.today()
        group_id = "a1111111-1111-1111-1111-111111111111"
        self.groups = [
            {
                "id": group_id,
                "name": "Grupo Sabores Atlánticos",
                "slug": "sabores-atlanticos",
                "contact_email": "ops@saboresatlanticos.es",
            }
        ]
        self.equipment_types = [
            {
                "id": "b1",
                "name": "Horno convencional",
                "category": "cocina",
                "default_interval_days": 90,
            },
            {
                "id": "b2",
                "name": "Horno Josper / carbón",
                "category": "cocina",
                "default_interval_days": 30,
            },
            {
                "id": "b3",
                "name": "Horno mixto / combi",
                "category": "cocina",
                "default_interval_days": 60,
            },
            {
                "id": "b4",
                "name": "Cámara frigorífica",
                "category": "frio",
                "default_interval_days": 120,
            },
            {
                "id": "b5",
                "name": "Lavavajillas industrial",
                "category": "office",
                "default_interval_days": 45,
            },
        ]
        self.restaurants = [
            {
                "id": "c1",
                "group_id": group_id,
                "name": "Mar Brava",
                "code": "MB-01",
                "city": "A Coruña",
                "address": "Paseo Marítimo 12",
                "is_active": True,
            },
            {
                "id": "c2",
                "group_id": group_id,
                "name": "Asador do Porto",
                "code": "AP-02",
                "city": "Vigo",
                "address": "Rúa do Porto 8",
                "is_active": True,
            },
            {
                "id": "c3",
                "group_id": group_id,
                "name": "Casa da Brasa",
                "code": "CB-03",
                "city": "Santiago de Compostela",
                "address": "Av. da Liberdade 45",
                "is_active": True,
            },
        ]
        self.equipment = [
            {
                "id": "d1",
                "restaurant_id": "c1",
                "equipment_type_id": "b2",
                "name": "Josper principal",
                "brand": "Josper",
                "model": "HJX-25",
                "serial_number": "JSP-2019-8841",
                "location_note": "Línea caliente",
                "status": "operativo",
            },
            {
                "id": "d2",
                "restaurant_id": "c1",
                "equipment_type_id": "b3",
                "name": "Horno combi 1",
                "brand": "Rational",
                "model": "iCombi Pro 10-1/1",
                "serial_number": "RAT-2021-1022",
                "location_note": "Pastelería",
                "status": "operativo",
            },
            {
                "id": "d3",
                "restaurant_id": "c2",
                "equipment_type_id": "b2",
                "name": "Josper asador",
                "brand": "Josper",
                "model": "HJX-50",
                "serial_number": "JSP-2018-4410",
                "location_note": "Sala de brasas",
                "status": "operativo",
            },
            {
                "id": "d4",
                "restaurant_id": "c2",
                "equipment_type_id": "b4",
                "name": "Cámara positiva",
                "brand": "ColdKit",
                "model": "CP-240",
                "serial_number": "CK-2020-778",
                "location_note": "Office frío",
                "status": "operativo",
            },
            {
                "id": "d5",
                "restaurant_id": "c3",
                "equipment_type_id": "b1",
                "name": "Horno pizza",
                "brand": "Moretti Forni",
                "model": "P120E",
                "serial_number": "MF-2022-331",
                "location_note": "Estación pizza",
                "status": "operativo",
            },
            {
                "id": "d6",
                "restaurant_id": "c3",
                "equipment_type_id": "b5",
                "name": "Lavavajillas cinta",
                "brand": "Winterhalter",
                "model": "MT 2040",
                "serial_number": "WH-2021-990",
                "location_note": "Office lavado",
                "status": "en_reparacion",
            },
        ]
        self.plans = [
            {
                "id": "e1",
                "equipment_id": "d1",
                "title": "Limpieza profunda Josper",
                "description": "Cenizas, rejillas y tiro",
                "interval_days": 30,
                "lead_time_days": 5,
                "priority": "critica",
                "is_active": True,
                "last_completed_at": (today.replace(day=1)).isoformat(),
                "next_due_at": (today.fromordinal(today.toordinal() - 5)).isoformat(),
            },
            {
                "id": "e2",
                "equipment_id": "d2",
                "title": "Descalcificación combi",
                "description": "Ciclo Care y juntas",
                "interval_days": 60,
                "lead_time_days": 7,
                "priority": "alta",
                "is_active": True,
                "last_completed_at": None,
                "next_due_at": (today.fromordinal(today.toordinal() + 10)).isoformat(),
            },
            {
                "id": "e3",
                "equipment_id": "d3",
                "title": "Revisión mensual Josper",
                "description": "Cámara y seguridad",
                "interval_days": 30,
                "lead_time_days": 5,
                "priority": "critica",
                "is_active": True,
                "last_completed_at": None,
                "next_due_at": (today.fromordinal(today.toordinal() + 2)).isoformat(),
            },
            {
                "id": "e4",
                "equipment_id": "d4",
                "title": "Revisión frigorífica",
                "description": "Temperaturas y condensador",
                "interval_days": 120,
                "lead_time_days": 14,
                "priority": "media",
                "is_active": True,
                "last_completed_at": None,
                "next_due_at": (today.fromordinal(today.toordinal() + 30)).isoformat(),
            },
            {
                "id": "e5",
                "equipment_id": "d5",
                "title": "Calibración termostato",
                "description": "Temperatura de cámara",
                "interval_days": 90,
                "lead_time_days": 10,
                "priority": "media",
                "is_active": True,
                "last_completed_at": None,
                "next_due_at": (today.fromordinal(today.toordinal() - 10)).isoformat(),
            },
            {
                "id": "e6",
                "equipment_id": "d6",
                "title": "Mantenimiento lavavajillas",
                "description": "Filtros y bomba",
                "interval_days": 45,
                "lead_time_days": 7,
                "priority": "alta",
                "is_active": True,
                "last_completed_at": None,
                "next_due_at": (today.fromordinal(today.toordinal() + 5)).isoformat(),
            },
        ]
        self.alarms: list[dict[str, Any]] = []
        self.logs: list[dict[str, Any]] = []
        self.refresh_alarms(group_id)

    def _type_name(self, type_id: str) -> str:
        for t in self.equipment_types:
            if t["id"] == type_id:
                return t["name"]
        return "Equipo"

    def _restaurant(self, restaurant_id: str) -> dict[str, Any]:
        return next(r for r in self.restaurants if r["id"] == restaurant_id)

    def _equipment(self, equipment_id: str) -> dict[str, Any]:
        return next(e for e in self.equipment if e["id"] == equipment_id)

    def upcoming(self, group_id: str) -> list[dict[str, Any]]:
        today = date.today()
        rows: list[dict[str, Any]] = []
        for plan in self.plans:
            if not plan["is_active"]:
                continue
            eq = self._equipment(plan["equipment_id"])
            if eq["status"] == "retirado":
                continue
            rest = self._restaurant(eq["restaurant_id"])
            if rest["group_id"] != group_id or not rest["is_active"]:
                continue
            due = date.fromisoformat(plan["next_due_at"])
            days = (due - today).days
            if days < 0:
                urgency = "vencido"
            elif days <= plan["lead_time_days"]:
                urgency = "proximo"
            else:
                urgency = "ok"
            rows.append(
                {
                    "plan_id": plan["id"],
                    "plan_title": plan["title"],
                    "priority": plan["priority"],
                    "interval_days": plan["interval_days"],
                    "lead_time_days": plan["lead_time_days"],
                    "next_due_at": plan["next_due_at"],
                    "last_completed_at": plan["last_completed_at"],
                    "days_until_due": days,
                    "urgency": urgency,
                    "equipment_id": eq["id"],
                    "equipment_name": eq["name"],
                    "brand": eq["brand"],
                    "model": eq["model"],
                    "equipment_status": eq["status"],
                    "equipment_type": self._type_name(eq["equipment_type_id"]),
                    "restaurant_id": rest["id"],
                    "restaurant_name": rest["name"],
                    "city": rest["city"],
                    "group_id": group_id,
                }
            )
        rows.sort(key=lambda r: r["next_due_at"])
        return rows

    def refresh_alarms(self, group_id: str) -> int:
        created = 0
        for row in self.upcoming(group_id):
            if row["urgency"] not in ("vencido", "proximo"):
                continue
            exists = any(
                a["plan_id"] == row["plan_id"]
                and a["status"] in ("abierta", "reconocida")
                for a in self.alarms
            )
            if exists:
                continue
            severity = "aviso"
            if row["urgency"] == "vencido" and row["priority"] in ("alta", "critica"):
                severity = "critica"
            elif row["urgency"] == "vencido":
                severity = "urgente"
            elif row["priority"] == "critica":
                severity = "urgente"
            title = (
                f"Mantenimiento vencido: {row['equipment_name']}"
                if row["urgency"] == "vencido"
                else f"Mantenimiento próximo: {row['equipment_name']}"
            )
            self.alarms.append(
                {
                    "id": str(uuid4()),
                    "group_id": group_id,
                    "plan_id": row["plan_id"],
                    "equipment_id": row["equipment_id"],
                    "restaurant_id": row["restaurant_id"],
                    "severity": severity,
                    "status": "abierta",
                    "title": title,
                    "message": (
                        f"{row['plan_title']} en {row['restaurant_name']} — "
                        f"{row['equipment_type']} (vence {row['next_due_at']})"
                    ),
                    "due_at": row["next_due_at"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            created += 1
        return created


_demo: DemoStore | None = None


def get_demo() -> DemoStore:
    global _demo
    if _demo is None:
        _demo = DemoStore()
    return _demo


def get_client() -> SupabaseClient | None:
    settings = get_settings()
    if settings.demo_mode or not settings.supabase_configured:
        return None
    return SupabaseClient(settings)
