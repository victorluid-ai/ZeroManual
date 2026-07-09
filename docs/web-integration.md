# Integracion futura de web (Claude Design)

## Objetivo

Incorporar la web que estas disenando en Claude Design sin romper contratos internos de agentes ni seguridad operativa.

## Ruta prevista

- Codigo frontend en `apps/web/`.
- Consumo de API del orquestador mediante endpoints versionados (`/api/v1/...`).
- Autenticacion con token de servicio y roles por tipo de accion.

## Contratos que deben mantenerse estables

- Evento de entrada: `event_id`, `agent_name`, `action`, `payload`.
- Resultado de salida: `status`, `decision`, `output`, `audit_notes`.
- Estados criticos: `COMPLETED`, `NEEDS_APPROVAL`, `FAILED`.

## Checklist para la Fase 2

1. Exportar/anadir artefactos de Claude Design dentro de `apps/web/`.
2. Adaptar componentes al modelo de datos del orquestador.
3. Añadir vistas:
   - Dashboard de agentes.
   - Cola de aprobaciones humanas.
   - Historial de auditoria.
4. Validar trazabilidad extremo a extremo.
