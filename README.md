# ZeroManual

**ZeroManual** es una empresa de automatizaciones digitales con dos caras conectadas:

| Capa | URL | Para qué |
|------|-----|----------|
| **Web comercial** | `http://localhost:8090/` | Vender servicios a clientes (landing, precios, registro) |
| **Portal cliente** | `/client` | Clientes activan automatizaciones (reseñas Google, etc.) |
| **Admin web** | `/admin` | Usuarios admin y altas/bajas de clientes del portal |

Facturación, agentes IA, contabilidad y aprobaciones viven en el repo hermano **OpsCenter** (puerto `8091` por defecto).

La web en `apps/web/zeroman/` es la **fachada comercial**. El admin de este repo solo gestiona la web.

## Estructura

- `apps/web/zeroman/` — sitio comercial ZeroManual.
- `apps/orchestrator/` — runtime de agentes.
- `apps/agents/` — lógica de negocio + tools.
- `apps/interface/` — API, admin, portal cliente.
- `docs/` — arquitectura, integraciones, operación.

## Arranque rápido

1. Copiar `.env.example` a `.env`.
2. `python -m pip install -e .`
3. `python -m apps.interface.api`
4. Abrir **http://localhost:8090** (web comercial).

Puerto configurable: `ZEROMANUAL_INTERFACE_PORT` en `.env`.

## Triggers autonomos

```bash
python -m apps.triggers.runner
```

Guía: `docs/triggers.md`

## Documentación

- `docs/brand.md` — web vs operaciones IA
- `docs/operations.md` — uso diario del panel admin
- `docs/integrations.md` — PDF, SMTP, export contable

## Nota fiscal

Los borradores contables no sustituyen la validación de un asesor fiscal antes de presentar impuestos.
