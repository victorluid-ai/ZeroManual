# Integraciones reales (Fase 3)

## PDF de factura

Al emitir una factura (`create_invoice`), ZeroManual:

1. Asigna numero legal secuencial: `FAC-2026-0001` (serie + año + contador).
2. Calcula base, IVA y total segun `ZEROMANUAL_DEFAULT_VAT_RATE`.
3. Genera PDF en `runtime/invoices/`.
4. Guarda ruta y desglose en SQLite.

Descarga: `GET /api/v1/invoices/{invoice_id}/pdf` o enlace **PDF** en la consola.

## SMTP (envio al cliente)

Variables en `.env`:

```env
SMTP_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu@gmail.com
SMTP_PASSWORD=contrasena_de_aplicacion
SMTP_FROM=ZeroManual <tu@gmail.com>
SMTP_AUTO_SEND_ON_ISSUE=false
```

- `SMTP_AUTO_SEND_ON_ISSUE=true` envia al crear si el payload incluye `client_email`.
- Recordatorio / reenvio: accion `send_reminder` con `invoice_id` en payload.
- Tool directa: `send_invoice_email`.

## Export contable (borrador)

`POST /api/v1/accounting/export` genera CSV (`;`, UTF-8 BOM) en `runtime/exports/` con:

- Facturas emitidas (base, IVA, total, cliente).
- Asientos del libro (`ledger_entries`).

Boton en consola: **Exportar contabilidad (CSV)**.

Revisar siempre con asesoria antes de declaraciones oficiales.

## Payload ampliado de factura

```json
{
  "client_name": "Acme SL",
  "amount_eur": 300,
  "client_email": "facturacion@acme.com",
  "client_nif": "B12345678",
  "concept": "Automatizacion mensual"
}
```
