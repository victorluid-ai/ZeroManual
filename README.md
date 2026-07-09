# ZeroManual

**ZeroManual** es una empresa de automatizaciones digitales con dos caras conectadas:

| Capa | URL | Para qué |
|------|-----|----------|
| **Web comercial** | `http://localhost:8090/` | Vender servicios a clientes (landing, precios, registro) |
| **Portal cliente** | `/client` | Clientes activan automatizaciones (reseñas Google, etc.) |
| **Operaciones IA** | `/admin` | Tu empresa gestionada por agentes (facturas, aprobaciones, contabilidad) |
| **Consola técnica** | `/ui` | Operador: lenguaje natural y eventos directos |

El código en `apps/` es el **motor interno** que opera ZeroManual con agentes autónomos. La web en `apps/web/zeroman/` es la **fachada comercial**. Misma marca, mismo servidor, mismos datos.

## Agentes internos (operaciones)

1. `AgentBillingOps` — facturación, cobros, recordatorios.
2. `AgentAccountingAssistantES` — contabilidad España.
3. `AgentClientDeliveryManager` — onboarding y entrega.
4. `AgentSalesPipeline` — ventas y propuestas.
5. `AgentGovernanceAndCompliance` — cumplimiento y aprobaciones.

## Estructura

- `apps/web/zeroman/` — sitio comercial ZeroManual.
- `apps/orchestrator/` — runtime de agentes.
- `apps/agents/` — lógica de negocio + tools.
- `apps/interface/` — API, admin, portal cliente.
- `docs/` — arquitectura, integraciones, operación.

## Arranque rápido

1. Copiar `.env.example` a `.env`.
2. `python -m pip install -e .`
3. `python -m apps.interface.api`
4. Abrir **http://localhost:8090** (web comercial).

Puerto configurable: `ZEROMANUAL_INTERFACE_PORT` en `.env`.

## Triggers autonomos

```bash
python -m apps.triggers.runner
```

Guía: `docs/triggers.md`

## Documentación

- `docs/brand.md` — web vs operaciones IA
- `docs/operations.md` — uso diario del panel admin
- `docs/integrations.md` — PDF, SMTP, export contable

## Nota fiscal

Los borradores contables no sustituyen la validación de un asesor fiscal antes de presentar impuestos.
