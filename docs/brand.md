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

## Operaciones IA (`/admin`, `/ui`)

- Panel **admin**: facturas, aprobaciones, clientes, agentes, export contable.
- Consola **ui**: instrucciones en lenguaje natural para agentes internos.
- Solo para operadores de ZeroManual (tú y tu equipo).

## Enlace entre ambas

1. Un cliente se registra en la web → fila en `clients` (SQLite).
2. Activa una automatización → workflow + agentes de entrega.
3. Una venta genera eventos → `AgentBillingOps` emite factura PDF.
4. Handoff → contabilidad ES clasifica el ingreso.
5. Todo trazado en `runtime/zeromanual.db` y audit log.

## Variables de entorno

Prefijo oficial: `ZEROMANUAL_*` (el prefijo legacy `MANUALZERO_*` sigue funcionando).

## Repo

La carpeta del repositorio puede seguir llamándose `ManualZero` en disco; la marca pública es **ZeroManual** en todo lo visible al usuario.
