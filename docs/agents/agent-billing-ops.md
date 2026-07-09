# AgentBillingOps

## Mision
Automatizar facturacion, seguimiento de cobro y recordatorios.

## Entradas
- `create_invoice`
- `send_reminder`
- `mark_paid`

## Salidas
- Factura emitida
- Estado de cobro actualizado
- Evidencia para auditoria

## Guardrails
- Si el importe supera el umbral de aprobacion, escalar.
- Validar datos fiscales minimos antes de emitir.
