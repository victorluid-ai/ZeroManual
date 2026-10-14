# Plan de migración a exmanual.com

Lista de URLs y variables que habría que cambiar para que la aplicación use `https://exmanual.com` como origen público. Este documento no cambia ningún valor. El proxy de `exmanual.com` no sustituye estas URLs: Stripe, Google y n8n siguen apuntando a lo que tengan hoy.

El `.env` del VPS no está en git. Donde abajo dice «valor en el servidor», el sitio es ese archivo, no una línea del repositorio. `apps/zeromanual_env.py` (líneas 9-14) acepta también el prefijo legacy `MANUALZERO_` para el mismo nombre.

`exmanual.es` no entra en esta lista ni en el proxy.

## URL base

Valor de corte: `https://exmanual.com` (sin barra final).

| Variable | Archivo | Línea | Qué hace hoy |
|---|---|---|---|
| `ZEROMANUAL_PUBLIC_URL` | `.env.example` | 39 | Default de ejemplo `http://localhost:8090`. El valor real está en el `.env` del servidor. |
| `ZEROMANUAL_PUBLIC_URL` / `MANUALZERO_PUBLIC_URL` | `apps/integrations/stripe_payments.py` | 158 | `public_url` de Stripe, leída con `zm_env("PUBLIC_URL", ...)`. |
| `ZEROMANUAL_PUBLIC_URL` | `apps/integrations/n8n_client.py` | 354 | Base al inyectar el nodo que llama a la API. La URL armada está en la línea 364. |
| `ZEROMANUAL_PUBLIC_URL` | `docs/qa/google-reviews-n8n-http-staticdata.md` | 93 | Dice que n8n necesita esta variable. |
| `ZEROMANUAL_PUBLIC_URL` | `docs/qa/google-reviews-n8n-http-staticdata.md` | 133 | La misma variable, en el checklist de n8n. |
| `ZEROMANUAL_PUBLIC_URL` | `docs/qa/gmb-automation-status.md` | 299 | El POST de borradores usa `{ZEROMANUAL_PUBLIC_URL}/internal/automations/{type}/drafts`. |
| `ZEROMANUAL_PUBLIC_URL` | `docs/qa/gmb-automation-status.md` | 435 | Ejemplo de la variable en un procedimiento. |

Los tests fijan `http://localhost:8090` y no forman parte del corte: `tests/test_stripe_payments.py` líneas 102 y 597.

## Stripe: success, cancel y webhook

Success y cancel salen de `public_url`. No hay variables distintas para ellas.

| Qué | Archivo | Línea | Destino si la URL base pasa a exmanual.com |
|---|---|---|---|
| `success_url` | `apps/integrations/stripe_payments.py` | 417-419 | `https://exmanual.com/client/checkout/success?session_id={CHECKOUT_SESSION_ID}` |
| `cancel_url` | `apps/integrations/stripe_payments.py` | 421 | `https://exmanual.com/?checkout=cancelled` |
| Esas dos URLs se envían a Stripe | `apps/integrations/stripe_payments.py` | 448-449 | Mismos valores, dentro del `Session.create`. |
| `return_url` del portal de facturación | `apps/integrations/stripe_payments.py` | 528 | `https://exmanual.com/client` |
| Ruta del webhook | `apps/interface/payments.py` | 370 | `POST /internal/stripe/webhook` |

El endpoint que hay que cambiar en el dashboard de Stripe (no está en el repo) sería `https://exmanual.com/internal/stripe/webhook`. El secreto `ZEROMANUAL_STRIPE_WEBHOOK_SECRET` (`.env.example` línea 42, lectura en `apps/integrations/stripe_payments.py` línea 156) no es una URL: no hace falta rotarlo solo por el dominio.

## Redirect de Google OAuth

Valor de corte: `https://exmanual.com/client/google/callback`. Hay que registrar esa URI en el cliente OAuth de Google Cloud. Hoy el código no la construye: usa la variable tal cual.

| Qué | Archivo | Línea |
|---|---|---|
| `GOOGLE_REDIRECT_URI` | `.env.example` | 31 |
| Lectura de la variable | `apps/integrations/google_oauth.py` | 29 |
| Se manda en la URL de autorización | `apps/integrations/google_oauth.py` | 39 |
| Se manda al canjear el código | `apps/integrations/google_oauth.py` | 60 |
| Ruta que tiene que seguir coincidiendo | `apps/interface/api.py` | 337 |

`scripts/qa/onboarding_playwright_check.py` línea 63 rellena la variable con el `BASE` del propio script. No es la config de producción.

## URLs de n8n hacia la API

n8n llama a la API con `ZEROMANUAL_PUBLIC_URL` dentro de su propio entorno (el contenedor de n8n, no el `.env` de esta app). Ese entorno no está en el repo.

| Qué | Archivo | Línea | Nota |
|---|---|---|---|
| URL del nodo `Push Draft to ZeroManual` | `n8n/templates/google_reviews.json` | 255 | `$env.ZEROMANUAL_PUBLIC_URL` o, si falta, `http://127.0.0.1:8090`, más `/internal/automations/google_reviews/drafts`. |
| La misma URL cuando el portal inyecta el nodo en un grafo viejo | `apps/integrations/n8n_client.py` | 354 y 364 | Usa el `ZEROMANUAL_PUBLIC_URL` de la app. |

En el corte, la variable del contenedor de n8n y la de la app tendrían que ser `https://exmanual.com`. Los workflows ya clonados guardan la URL que tenían al activarse: no se actualizan solos.

## Correos y textos con el dominio antiguo

| Texto | Archivo | Línea |
|---|---|---|
| `hello@zeroman.co` | `apps/web/zeroman/app.jsx` | 46 |
| `hola@zeroman.co` | `apps/web/zeroman/app.jsx` | 97 |
| Default `billing@zeromanual.co` si no hay `SMTP_FROM` ni `SMTP_USER` | `apps/integrations/settings.py` | 55 |
| Ejemplo `SMTP_FROM=ZeroManual <tu@gmail.com>` | `docs/integrations.md` | 24 |

`SMTP_FROM` real, si existe, está en el `.env` del servidor. `.env.example` no lo define.

## No cambiar al pasar el dominio de la web

Estas URLs son de n8n. El host sigue siendo `n8n.srv1255804.hstgr.cloud`. No deben pasar a `exmanual.com`.

| Variable | Archivo | Línea |
|---|---|---|
| `N8N_HOST` | `.env.example` | 11 |
| `N8N_WEBHOOK_URL` | `.env.example` | 12 |
| `N8N_WEBHOOK_BASE_URL` | `.env.example` | 13 |
| `N8N_API_URL` | `.env.example` | 18 |
| Lectura de `N8N_API_URL` | `apps/integrations/n8n_client.py` | 123 |
| Lectura de `N8N_WEBHOOK_BASE_URL` | `apps/integrations/n8n_client.py` | 279 |
| `N8N_API_URL=https://n8n.srv1255804.hstgr.cloud/api/v1` | `docs/qa/gmb-automation-brief.md` | 107 |
