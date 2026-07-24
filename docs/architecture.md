# Arquitectura ZeroManual (Fase 1-2)

## Resumen

ZeroManual usa una arquitectura Claude-first con triggers nativos (email) y un orquestador Python para ejecutar agentes con politicas de riesgo, herramientas auditables y handoffs entre agentes.

## Flujo operativo

1. Consola NL, email o API emiten un evento de negocio.
2. `apps/orchestrator/runtime.py` enruta el evento al agente objetivo.
3. El agente ejecuta: plan (reglas o Claude en modo eco) -> riesgo -> ejecutar tool o escalar.
4. Si `COMPLETED`, el bus de handoffs puede encadenar agentes (ej. factura -> contabilidad).
5. El resultado se guarda en SQLite y `runtime/audit-log.jsonl`.

## Handoffs automaticos

| Origen | Accion | Destino | Accion |
|--------|--------|---------|--------|
| AgentBillingOps | create_invoice | AgentAccountingAssistantES | classify_transaction |
| AgentSalesPipeline | draft_proposal | AgentClientDeliveryManager | client_onboarding |

## Niveles de autonomia

- Nivel A: ejecucion autonoma total.
- Nivel B: ejecucion autonoma con controles reforzados.
- Nivel C: bloqueo y solicitud de aprobacion humana.

## Integraciones clave

- n8n: dispara hacia ZeroManual solo a través de `POST /internal/automations/{automation_type}/drafts` (autenticado con `X-Webhook-Secret`), usado hoy por el workflow de reseñas de Google. No existe un webhook genérico `/api/v1/webhooks/n8n`.
- SQLite (`runtime/zeromanual.db`): aprobaciones, facturas y log de eventos.
- Postgres: opcional en VPS via `docker-compose` para escalar despues.
- Claude: interpretacion NL (opcional con `ANTHROPIC_API_KEY`).

## Hardening recomendado (siguiente paso)

- Autenticacion por servicio para webhooks internos.
- Firma de eventos entre n8n y orquestador.
- Cifrado de datos sensibles y politicas RGPD.
