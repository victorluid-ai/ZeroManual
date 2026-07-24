# Operacion diaria ZeroManual

## Principio

Los agentes son autonomos y viven en ZeroManual. n8n solo dispara eventos externos (email, cron, formularios), no contiene la logica de negocio de los agentes.

## Flujo habitual

1. Escribes una instruccion en lenguaje natural en la consola web.
2. El sistema interpreta y ejecuta el agente correspondiente.
3. Si el riesgo es alto, entra en cola de aprobacion.
4. Apruebas o rechazas desde el panel derecho.
5. Las facturas emitidas aparecen en **Facturas emitidas**.

## Umbrales y seguridad

- `APPROVAL_THRESHOLD_EUR`: importe a partir del cual facturacion/contabilidad escalan.
- `ZEROMANUAL_WEBHOOK_SECRET`: protege el endpoint que n8n usa para llamar a ZeroManual.

## Endpoints principales

| Endpoint | Uso |
|----------|-----|
| `POST /api/v1/natural-language` | Instruccion en texto libre |
| `POST /api/v1/events` | Evento estructurado (avanzado) |
| `GET /api/v1/approvals` | Pendientes |
| `POST /api/v1/approvals/{id}/approve` | Aprobar |
| `POST /api/v1/approvals/{id}/reject` | Rechazar |
| `GET /api/v1/invoices` | Facturas emitidas |
| `GET /api/v1/ledger` | Asientos contables |
| `GET /api/v1/clients/{name}/context` | Memoria + facturas + ledger del cliente |
| `GET /api/v1/invoices/{id}/pdf` | Descargar PDF de factura |
| `POST /api/v1/accounting/export` | CSV contable borrador |

| `POST /internal/automations/{automation_type}/drafts` | Trigger desde n8n (autenticado con `X-Webhook-Secret`) |

Ver [integrations.md](integrations.md) para SMTP, PDF y export.

## Persistencia

- Base SQLite: `runtime/zeromanual.db` (configurable con `ZEROMANUAL_DB_PATH`)
- Auditoria JSONL: `runtime/audit-log.jsonl`

## Escalado humano

Aprueba solo si:
- conoces el cliente y el importe,
- la accion fiscal/legal es coherente,
- no hay banderas de compliance (`sensitive_data`, `irreversible_action`).

Rechaza si falta contexto o hay duda legal/fiscal.

## Coste de API (Anthropic)

Un flujo de factura **no deberia** gastar LLM al aprobar: la aprobacion solo ejecuta herramientas locales.

Variables recomendadas en `.env`:

| Variable | Valor recomendado | Efecto |
|----------|-------------------|--------|
| `ZEROMANUAL_AI_MODE` | `eco` | Reglas primero; Claude solo si el texto es ambiguo |
| `CLAUDE_MODEL` | `claude-haiku-4-5` | Modelo barato para JSON cortos |
| `CLAUDE_MAX_TOKENS` | `256` | Limita salida y coste por llamada |
| `ZEROMANUAL_AI_MODE` | `off` | Sin llamadas API (solo reglas) |

Modos: `eco` (defecto), `balanced`, `full`, `off`.

Reinicia la API tras cambiar `.env`. Revisa uso en [console.anthropic.com](https://console.anthropic.com/).

**Nota:** el coste de esta sesion en Cursor (agente con `CLAUDE.md` grande) es independiente de ZeroManual.

## Mantenimiento

- Backup semanal de `runtime/zeromanual.db` y `audit-log.jsonl`.
- Rotacion de secretos cada 90 dias.
- Revision mensual de umbrales de aprobacion.
