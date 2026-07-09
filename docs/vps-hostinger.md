# Despliegue en VPS Hostinger

## Objetivo

Ejecutar ZeroManual (agentes + API/UI) en tu VPS junto a n8n, manteniendo agentes autonomos fuera de workflows n8n.

## Arquitectura en VPS

```text
Internet -> n8n (5678) -> webhook externo
Internet -> ZeroManual API (8090) -> agentes + SQLite/Postgres
```

n8n dispara ZeroManual; ZeroManual decide y ejecuta.

## Pasos recomendados

### 1) Preparar servidor

- Ubuntu 22.04+ en Hostinger VPS
- Instalar Docker + Docker Compose
- Abrir puertos: `22`, `443`, `5678` (n8n), `8090` (ZeroManual, o detras de reverse proxy)

### 2) Clonar proyecto

```bash
git clone <tu-repo-manualzero> /opt/zeromanual
cd /opt/zeromanual
cp .env.example .env
```

Edita `.env` con valores reales (secretos, dominio, umbrales).

### 3) Levantar stack base

```bash
docker compose -f infra/docker-compose.yml up -d
```

### 4) Ejecutar API de agentes

Opcion simple (sin contenedor dedicado):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m apps.interface.api
```

Recomendado produccion: `systemd` o contenedor propio con restart automatico.

### 5) Configurar n8n como disparador

En n8n crea un workflow con nodo **HTTP Request**:

- Method: `POST`
- URL: `http://<tu-vps>:8090/api/v1/webhooks/n8n`
- Header: `x-zeromanual-secret: <ZEROMANUAL_WEBHOOK_SECRET>`
- Body JSON ejemplo:

```json
{
  "message": "Crea una factura de 300 euros para cliente Acme"
}
```

Alternativa estructurada:

```json
{
  "agent_name": "AgentBillingOps",
  "action": "create_invoice",
  "payload": { "amount_eur": 300, "client_name": "Acme" }
}
```

### 6) Reverse proxy (recomendado)

Usa Nginx/Caddy con TLS:

- `https://agents.tudominio.com` -> `localhost:8090`
- `https://n8n.tudominio.com` -> `localhost:5678`

## Checklist de produccion

- [ ] `.env` con secretos fuertes
- [ ] HTTPS activo
- [ ] Backup de `runtime/zeromanual.db`
- [ ] Prueba de instruccion NL + aprobacion + factura emitida
- [ ] Prueba webhook n8n -> ZeroManual
- [ ] Logs monitorizados (`audit-log.jsonl`)

## Nota fiscal (Espana)

Los borradores de IVA/impuestos requieren validacion humana antes de presentacion oficial.
