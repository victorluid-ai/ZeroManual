# Operacion diaria ZeroManual (comercial)

## Principio

Este repo opera la **web y el portal**. Facturas, agentes y aprobaciones se gestionan en **OpsCenter**.

## Flujo habitual

1. Revisas clientes y automatizaciones en `/admin`.
2. Los clientes activan reseñas Google desde `/client`.
3. Para facturar o aprobar acciones de agentes, abres OpsCenter (`ZEROMANUAL_OPS_URL`).

## Seguridad

- `ZEROMANUAL_WEBHOOK_SECRET`: protege `POST /internal/automations/{type}/drafts`.
- `ZEROMANUAL_OPS_URL` + `ZEROMANUAL_OPS_API_KEY`: puente hacia OpsCenter (opcional en local).

## Endpoints principales

| Endpoint | Uso |
|----------|-----|
| `POST /client/register` | Alta cliente |
| `POST /client/login` | Login cliente |
| `GET /api/v1/admin/clients` | Listado clientes (admin) |
| `GET /api/v1/admin/users` | Usuarios admin |
| `POST /internal/automations/{type}/drafts` | Borradores desde n8n |

## Persistencia

- SQLite: `runtime/zeromanual.db`
- OpsCenter: `runtime/opscenter.db` (otro proceso)

## Mantenimiento

- Backup semanal de `zeromanual.db`.
- Rotacion de secretos cada 90 dias.
- Verificar que el puente OpsCenter responde (`/health` en `:8091`).
