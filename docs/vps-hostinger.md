# Despliegue en VPS Hostinger

## Arquitectura

```text
Internet -> ZeroManual comercial (:8090)  web + portal + admin slim
Internet -> OpsCenter (:8091)            agentes + facturas + aprobaciones
Internet -> n8n (:5678)                  workflows por cliente
```

n8n escribe borradores en ZeroManual. ZeroManual emite eventos de negocio a OpsCenter.

## Pasos

### 1) ZeroManual

```bash
git clone <repo-zeromanual> /opt/zeromanual
cd /opt/zeromanual
cp .env.example .env
# Definir ZEROMANUAL_WEBHOOK_SECRET, ZEROMANUAL_OPS_URL, ZEROMANUAL_OPS_API_KEY
python3 -m pip install -e .
python3 -m apps.interface.api   # :8090
```

### 2) OpsCenter

```bash
git clone <repo-opscenter> /opt/opscenter
cd /opt/opscenter
cp .env.example .env
# OPSCENTER_API_KEY debe coincidir con ZEROMANUAL_OPS_API_KEY del tenant
python3 -m pip install -e .
python3 -m apps.interface.api   # :8091
```

### 3) Migrar datos ops (si vienes del monolito)

```bash
cd /opt/opscenter
python3 scripts/migrate_from_zeromanual.py --source /opt/zeromanual/runtime/zeromanual.db
```

Haz **backup** de la DB antes.

### 4) n8n

Webhook de borradores:

- `POST http://<vps>:8090/internal/automations/google_reviews/drafts`
- Header: `X-Webhook-Secret: <ZEROMANUAL_WEBHOOK_SECRET>`

### 5) Reverse proxy

- `https://app.tudominio.com` → `:8090`
- `https://ops.tudominio.com` → `:8091`
- `https://n8n.tudominio.com` → `:5678`

## Checklist

- [ ] `.env` con secretos fuertes en ambos servicios
- [ ] HTTPS activo
- [ ] Backup de ambas DB
- [ ] Alta cliente ZM → evento visible en OpsCenter
- [ ] Activar automatización → workflow n8n + onboarding en OpsCenter
- [ ] Admin ZM sin pestañas de facturas/agentes
