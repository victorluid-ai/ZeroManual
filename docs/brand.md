# Marca ZeroManual

## Una marca, dos sistemas

```text
                    ZeroManual (marca)
                           │
         ┌─────────────────┴─────────────────┐
         ▼                                   ▼
   Web comercial                      OpsCenter (repo aparte)
   apps/web + /client + /admin slim   agentes, facturas, NL
   Vende y entrega automatizaciones   Opera varios negocios (tenants)
```

## Web comercial (`/`, `/client`, `/admin`)

- Landing, precios, FAQ, contacto.
- Registro/login de **clientes** en `/client`.
- Admin comercial: usuarios del producto + clientes portal + automatizaciones.
- Sin facturas, sin agentes, sin aprobaciones.

## OpsCenter (`:8091`)

- Panel ops: facturas, aprobaciones, ledger, agentes, consola NL.
- Multi-tenant: ZeroManual es el tenant `zeromanual`.
- Triggers email nativos y export contable.

## Enlace

1. Cliente se registra en ZeroManual → fila en `clients`.
2. Activa automatización → n8n + evento a OpsCenter (`client_onboarding`).
3. Operaciones financieras se gestionan solo en OpsCenter.

## Variables

Prefijo `ZEROMANUAL_*`. Puente: `ZEROMANUAL_OPS_URL`, `ZEROMANUAL_OPS_API_KEY`, `ZEROMANUAL_OPS_TENANT_ID`.
