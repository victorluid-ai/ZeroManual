# Mantenimiento

Plataforma de **mantenimiento preventivo** para grupos de restauración.
Inventario de equipos por restaurante, calendario de revisiones y sistema de alarmas.
Backend Python (FastAPI + Jinja2) y base de datos **Supabase (PostgreSQL)**. Sin React.

## Arranque rápido (demo local)

```bash
# Desde la raíz del repo
python -m pip install -e ".[dev]"
export MANTENIMIENTO_DEMO_MODE=true
python -m apps.mantenimiento.app
```

Abre http://localhost:8100

## Supabase (producción / serio)

1. Crea un proyecto en [Supabase](https://supabase.com).
2. En el SQL Editor, ejecuta en orden:
   - `supabase/migrations/001_initial_schema.sql`
   - `supabase/seed.sql` (datos de ejemplo)
3. Copia `apps/mantenimiento/.env.example` a `.env` en la raíz o exporta:

```bash
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=eyJ...
unset MANTENIMIENTO_DEMO_MODE
python -m apps.mantenimiento.app
```

La app usa la **service role key** en el servidor (nunca en el navegador) para hablar con PostgREST.

## Modelo de datos

| Tabla | Uso |
|-------|-----|
| `groups` | Grupo de restauración (tenant) |
| `restaurants` | Locales del grupo |
| `equipment_types` | Catálogo (horno, Josper, combi, cámara…) |
| `equipment` | Máquinas físicas por restaurante |
| `maintenance_plans` | Planes preventivos con `next_due_at` |
| `maintenance_logs` | Historial de intervenciones |
| `alarms` | Alarmas abiertas / reconocidas / resueltas |

Función SQL `refresh_maintenance_alarms()` genera alarmas a partir de planes vencidos o dentro del `lead_time`.

Vista `v_upcoming_maintenance` alimenta el panel y la lista de preventivos.

## Rutas

| URL | Función |
|-----|---------|
| `/` | Landing |
| `/panel` | Dashboard operativo |
| `/restaurantes` | Alta y listado de locales |
| `/equipos` | Inventario + alta de máquinas |
| `/preventivos` | Calendario y cierre de intervenciones |
| `/alarmas` | Sistema de alarmas |
| `/salud` | Healthcheck JSON |
| `/api/docs` | OpenAPI |

## Diseño

Identidad visual propia (Fraunces + Sora), atmósfera industrial-hospitality
(verde tinta / cobre), sin componentes tipo dashboard genérico en la landing.
