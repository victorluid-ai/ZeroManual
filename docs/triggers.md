# Triggers nativos

Los triggers de email y el runner de agentes viven en **OpsCenter**, no en ZeroManual comercial.

```bash
cd /path/to/OpsCenter
python -m apps.triggers.runner
```

Documentación completa: repo OpsCenter → `docs/triggers.md`.

ZeroManual comercial solo recibe webhooks de n8n en:

`POST /internal/automations/{automation_type}/drafts`
