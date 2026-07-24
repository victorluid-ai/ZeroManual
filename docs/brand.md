# Marca ZeroManual

## Una marca, dos capas

```text
                    ZeroManual (marca única)
                           │
         ┌─────────────────┴─────────────────┐
         ▼                                   ▼
   Web comercial                      Motor operativo
   apps/web/zeroman/                  apps/agents + orchestrator
   /  /client                         /admin  /ui
   Vende servicios                    Gestiona la empresa con IA
```

## Web comercial (`/`)

- Landing, precios, FAQ, contacto.
- Registro y login de **clientes** en `/client`.
- Automatizaciones que el cliente activa (reseñas Google, Instagram, etc.).

## Admin web (`/admin`)

- Altas/bajas de **clientes del portal** y usuarios admin del producto.
- Sin facturas, agentes ni contabilidad (eso está en **OpsCenter**).

## OpsCenter (repo aparte)

- Panel ops: facturas, agentes, empresas fiscales, aprobaciones, consola NL.
- Pensado como centro de operaciones multi-negocio.

## Enlace entre ambas

1. Un cliente se registra en la web → fila en `clients` (SQLite de ZeroManual).
2. Activa una automatización → workflow n8n del cliente.
3. La facturación/operaciones de negocio se gestionan en OpsCenter.

## Variables de entorno

Prefijo oficial: `ZEROMANUAL_*` (el prefijo legacy `MANUALZERO_*` sigue funcionando).

## Repo

La carpeta del repositorio puede seguir llamándose `ManualZero` en disco; la marca pública es **ZeroManual** en todo lo visible al usuario.
