# ZeroManual

**ZeroManual** es la web comercial y el portal de clientes. La facturación, agentes IA y aprobaciones viven en el repo hermano **OpsCenter**.

| Capa | URL | Para qué |
|------|-----|----------|
| **Web comercial** | `http://localhost:8090/` | Vender servicios (landing, precios, registro) |
| **Portal cliente** | `/client` | Activar automatizaciones (reseñas Google, etc.) |
| **Admin comercial** | `/admin` | Usuarios del producto, clientes y estado de automatizaciones |
| **OpsCenter** | `http://localhost:8091` | Facturas, agentes, aprobaciones, contabilidad (repo aparte) |

## Arranque rápido

1. Copiar `.env.example` a `.env` (incluye `ZEROMANUAL_OPS_URL` / `ZEROMANUAL_OPS_API_KEY`).
2. `python3 -m pip install -e ".[dev]"`
3. `python3 -m apps.interface.api`
4. Abrir **http://localhost:8090**

## Puente a OpsCenter

Al registrar un cliente o activar una automatización, ZeroManual emite un evento HTTP a OpsCenter (si `ZEROMANUAL_OPS_URL` y `ZEROMANUAL_OPS_API_KEY` están definidos). Los fallos del puente se registran y **no** bloquean el portal.

## Migrar datos ops antiguos

Si tenías facturas/aprobaciones en `runtime/zeromanual.db`, usa el script del repo OpsCenter:

```bash
cd /path/to/OpsCenter
python3 scripts/migrate_from_zeromanual.py --source /path/to/zeromanual.db
```

## Tests

```bash
pytest tests/ -q
```

## Documentación

- `docs/brand.md` — web vs OpsCenter
- `docs/architecture.md` — límites de sistema
- `docs/operations.md` — operación diaria comercial
- `docs/vps-hostinger.md` — despliegue dos servicios
