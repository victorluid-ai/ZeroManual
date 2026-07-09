# Triggers nativos (sin n8n)

## Filosofia

Los agentes **no** se activan con workflows de n8n.

ZeroManual observa el mundo real (emails, y en el futuro mas fuentes) y cada agente se despierta **solo cuando detecta una senal relevante**.

```text
Email nuevo -> Detector -> ¿Requiere facturacion? -> AgentBillingOps
```

## Componentes

| Modulo | Rol |
|--------|-----|
| `EmailWatcher` | Lee buzon IMAP (emails no leidos) |
| `TriggerDetector` | Decide si activar un agente y con que accion |
| `TriggerDispatcher` | Ejecuta el agente via orquestador |
| `runner.py` | Bucle continuo en segundo plano |

## Activar watcher de email

En `.env`:

```env
EMAIL_TRIGGER_ENABLED=true
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_IMAP_USER=tu@email.com
EMAIL_IMAP_PASSWORD=app_password_aqui
EMAIL_IMAP_FOLDER=INBOX
EMAIL_POLL_INTERVAL_SECONDS=60
```

Gmail: usa **contrasena de aplicacion**, no la contrasena normal.

## Arrancar el runner

Terminal separada (deja la API/consola en otra):

```bash
python -m apps.triggers.runner
```

## Que hace AgentBillingOps con un email

1. Llega email no leido.
2. Detector busca palabras clave (`factura`, `invoice`, `pedido`, `cobro`...) o usa Claude si hay `ANTHROPIC_API_KEY`.
3. Si aplica, extrae importe/cliente cuando puede.
4. Dispara `create_invoice` o `send_reminder`.
5. Si importe > umbral, va a **aprobacion humana** en la consola web.

## Probar sin IMAP real

```bash
POST /api/v1/triggers/run-once
```

(con `EMAIL_TRIGGER_ENABLED=true` y buzon configurado)

O simula por consola web con lenguaje natural (modo manual).

## n8n

Opcional y **no recomendado** para activar agentes. Usa triggers nativos de ZeroManual.
