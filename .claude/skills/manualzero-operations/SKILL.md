---
name: ZeroManual-operations
description: Operar ZeroManual via API y consola — eventos, aprobaciones, facturas y triggers. Usar cuando el usuario pida ejecutar agentes de negocio, revisar pendientes o probar facturacion.
---

# ZeroManual Operations

## Arranque

```bash
python -m apps.interface.api
python -m apps.triggers.runner
```

## API util

- `POST /api/v1/natural-language` — instruccion en texto libre
- `GET /api/v1/approvals` — pendientes
- `POST /api/v1/approvals/{id}/approve`
- `GET /api/v1/invoices`
- `POST /api/v1/triggers/run-once`

## Regla

Agentes de negocio en `apps/agents/`, no confundir con agentes dev de `.claude/agents/`.
