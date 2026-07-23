# Arquitectura ZeroManual (comercial)

## Resumen

ZeroManual es el producto comercial (landing + portal cliente + admin ligero).
El runtime multiagente vive en **OpsCenter** (proceso y DB separados).

## Flujo

```text
Cliente → /client → Google OAuth → n8n workflow
                 ↘ OpsCenterBridge → POST OpsCenter /api/v1/events
Admin ZM → /admin → users + clients + automations (solo lectura/CRUD comercial)
```

## Persistencia

- SQLite `runtime/zeromanual.db`: `users`, `clients`, sesiones, Google creds, automations, drafts.
- Las tablas ops históricas pueden coexistir tras migración, pero la API comercial ya no las expone.

## Seguridad

- Admin y cliente: Bearer sessions.
- Webhooks n8n: `X-Webhook-Secret` (`ZEROMANUAL_WEBHOOK_SECRET`).
- OpsCenter: API key por tenant (`X-API-Key` + `X-Tenant-Id`).

## Hardening siguiente

- Cola de reintentos persistente para el puente OpsCenter.
- Firma de webhooks n8n.
- Rate-limit login en SQLite (hoy en memoria si se añade).
