"""Mantenimiento — plataforma de preventivos para grupos de restauración."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from apps.mantenimiento.app.config import get_settings
from apps.mantenimiento.app.services import MaintenanceService

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Mantenimiento", docs_url="/api/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _svc() -> MaintenanceService:
    return MaintenanceService()


def _ctx(request: Request, **extra):
    settings = get_settings()
    svc = _svc()
    group = svc.resolve_group()
    alarms = svc.list_alarms(group["id"])
    return {
        "request": request,
        "app_name": settings.app_name,
        "is_demo": svc.is_demo,
        "group": group,
        "alarm_badge": len(alarms),
        **extra,
    }


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html", _ctx(request))


@app.get("/panel", response_class=HTMLResponse)
async def panel(request: Request):
    svc = _svc()
    group = svc.resolve_group()
    data = svc.dashboard(group["id"])
    return templates.TemplateResponse(
        request,
        "panel.html",
        _ctx(request, active="panel", **data),
    )


@app.get("/restaurantes", response_class=HTMLResponse)
async def restaurants_page(request: Request):
    svc = _svc()
    group = svc.resolve_group()
    restaurants = svc.list_restaurants(group["id"])
    equipment = svc.list_equipment(group["id"])
    counts = {}
    for e in equipment:
        counts[e["restaurant_id"]] = counts.get(e["restaurant_id"], 0) + 1
    return templates.TemplateResponse(
        request,
        "restaurantes.html",
        _ctx(
            request,
            active="restaurantes",
            restaurants=restaurants,
            equipment_counts=counts,
        ),
    )


@app.post("/restaurantes")
async def create_restaurant(
    request: Request,
    name: str = Form(...),
    code: str = Form(""),
    city: str = Form(""),
    address: str = Form(""),
):
    svc = _svc()
    group = svc.resolve_group()
    svc.create_restaurant(
        group["id"], name=name, code=code, city=city, address=address
    )
    return RedirectResponse("/restaurantes", status_code=303)


@app.get("/equipos", response_class=HTMLResponse)
async def equipment_page(request: Request, restaurant_id: str | None = None):
    svc = _svc()
    group = svc.resolve_group()
    restaurants = svc.list_restaurants(group["id"])
    types = svc.list_equipment_types()
    equipment = svc.list_equipment(group["id"], restaurant_id=restaurant_id)
    return templates.TemplateResponse(
        request,
        "equipos.html",
        _ctx(
            request,
            active="equipos",
            restaurants=restaurants,
            types=types,
            equipment=equipment,
            filter_restaurant=restaurant_id or "",
        ),
    )


@app.post("/equipos")
async def create_equipment(
    restaurant_id: str = Form(...),
    equipment_type_id: str = Form(...),
    name: str = Form(...),
    brand: str = Form(""),
    model: str = Form(""),
    serial_number: str = Form(""),
    location_note: str = Form(""),
    status: str = Form("operativo"),
):
    svc = _svc()
    svc.create_equipment(
        restaurant_id=restaurant_id,
        equipment_type_id=equipment_type_id,
        name=name,
        brand=brand,
        model=model,
        serial_number=serial_number,
        location_note=location_note,
        status=status,
    )
    return RedirectResponse("/equipos", status_code=303)


@app.get("/preventivos", response_class=HTMLResponse)
async def preventivos_page(request: Request):
    svc = _svc()
    group = svc.resolve_group()
    upcoming = svc.upcoming(group["id"])
    return templates.TemplateResponse(
        request,
        "preventivos.html",
        _ctx(request, active="preventivos", upcoming=upcoming),
    )


@app.post("/preventivos/{plan_id}/completar")
async def complete_plan(
    plan_id: str,
    performed_by: str = Form(""),
    notes: str = Form(""),
):
    svc = _svc()
    svc.complete_plan(plan_id, performed_by=performed_by, notes=notes)
    group = svc.resolve_group()
    svc.refresh_alarms(group["id"])
    return RedirectResponse("/preventivos", status_code=303)


@app.get("/alarmas", response_class=HTMLResponse)
async def alarms_page(request: Request):
    svc = _svc()
    group = svc.resolve_group()
    created = svc.refresh_alarms(group["id"])
    alarms = svc.list_alarms(group["id"], open_only=False)
    open_alarms = [a for a in alarms if a["status"] in ("abierta", "reconocida")]
    return templates.TemplateResponse(
        request,
        "alarmas.html",
        _ctx(
            request,
            active="alarmas",
            alarms=alarms,
            open_alarms=open_alarms,
            newly_created=created,
        ),
    )


@app.post("/alarmas/{alarm_id}/estado")
async def alarm_status(alarm_id: str, status: str = Form(...)):
    svc = _svc()
    svc.update_alarm_status(alarm_id, status)
    return RedirectResponse("/alarmas", status_code=303)


@app.post("/alarmas/refrescar")
async def refresh_alarms():
    svc = _svc()
    group = svc.resolve_group()
    svc.refresh_alarms(group["id"])
    return RedirectResponse("/alarmas", status_code=303)


@app.get("/salud")
async def health():
    settings = get_settings()
    svc = _svc()
    return {
        "ok": True,
        "demo": svc.is_demo,
        "supabase": settings.supabase_configured,
    }


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "apps.mantenimiento.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
