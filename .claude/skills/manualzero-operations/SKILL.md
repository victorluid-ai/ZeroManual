---
name: ZeroManual-operations
description: Operar ZeroManual comercial (portal/admin) y enlazar con OpsCenter para facturas/agentes.
---

# ZeroManual Operations

## Arranque comercial

```bash
python -m apps.interface.api   # :8090
```

## Arranque OpsCenter (repo hermano)

```bash
cd /path/to/OpsCenter
python -m apps.interface.api   # :8091
python -m apps.triggers.runner
```

## API comercial util

- `POST /client/register` — alta cliente (emite evento a OpsCenter si el puente está configurado)
- `GET /api/v1/admin/clients` — clientes + automatizaciones
- `GET /api/v1/admin/users` — usuarios admin
- `POST /internal/automations/{type}/drafts` — borradores desde n8n

## API OpsCenter (facturas / agentes)

- `POST /api/v1/natural-language`
- `GET /api/v1/approvals`
- `POST /api/v1/approvals/{id}/approve`
- `GET /api/v1/invoices`

Headers: `X-API-Key`, `X-Tenant-Id: zeromanual`.

## Regla

Agentes de negocio en **OpsCenter** (`apps/agents/`), no en este repo. No confundir con agentes dev de `.claude/agents/`.
