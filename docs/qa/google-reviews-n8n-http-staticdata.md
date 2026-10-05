# google_reviews: plantilla HTTP + staticData

Sustituye la plantilla n8n `oju0vufPh9qyRqQs` (`GMB Review Responder (Draft)`), que pedía una credencial OAuth de Google Business **por cliente**. La copia de cada cliente ya no crea credenciales n8n. Lee el `refresh_token` que ZeroManual inyecta en `workflow.staticData` y llama a Google con HTTP.

Archivo importable: `n8n/templates/google_reviews.json`.

Este cambio **no** desactiva ni reactiva el workflow de CDV, ni aprueba reseñas.

## Contrato staticData

`duplicate_template` escribe estas claves en la raíz y, otra vez, dentro de `staticData.global`:

| Clave | Origen |
| --- | --- |
| `refresh_token` | OAuth de Google del cliente (ya guardado en ZeroManual) |
| `location_id` | `business.location_id`. Sigue siendo obligatorio un resource name `accounts/…/locations/…` (`require_gbp_location_id`) |
| `client_name` | Nombre del cliente |
| `business_id` | Negocio activado |
| `client_id` | Id del cliente. No es un secreto. `Build Draft Payload` lo lee para el POST al portal |

`global` existe porque en n8n `$getWorkflowStaticData('global')` lee **solo** `staticData.global`. Las expresiones HTTP no ven `$workflow.staticData`: `$workflow` expone `id`, `name` y `active`.

El nodo Code `Load Client Context` copia `staticData.global` al item. A partir de ahí los HTTP Request leen:

- `{{ $json.refresh_token }}` en `Exchange Google Access Token`
- `{{ $('Load Client Context').item.json.location_id }}` en `List Google Reviews`
- `{{ $json.access_token }}` como `Authorization: Bearer …` tras el canje de token

`Post Reply to Google` no pasa por ese nodo (el webhook inyectado entra directo). Lee `staticData.global` él mismo con `$getWorkflowStaticData('global')`.

`staticData.global.drafted_review_ids` lo escribe el propio workflow para no reenviar la misma reseña. No forma parte del contrato que inyecta Python. Borrar esa lista obliga a regenerar borradores.

## Nombres de nodo (no renombrar)

En la plantilla:

| Nodo | Tipo | Papel |
| --- | --- | --- |
| `Every 15 Minutes` | scheduleTrigger | Sondeo |
| `Manual Smoke` | manualTrigger | Prueba manual |
| `Load Client Context` | code | Lee `staticData.global` |
| `Exchange Google Access Token` | httpRequest | Canje del refresh token |
| `List Google Reviews` | httpRequest | Lista reseñas |
| `Split Unreplied Reviews` | code | Descarta las que ya tienen respuesta |
| `Normalize Review` | code | `review_name`, `reviewer_name`, `starRating`, `review_text` |
| `Filter Unseen Reviews` | code | Salta ids ya borradoreados |
| `Call LLM` | httpRequest | Chat completions |
| `Generate AI Draft` | code | **Contrato.** Deja reseña + texto del modelo |
| `Build Draft Payload` | code | Arma el JSON del portal desde `staticData.global` y el item |
| `Push Draft to ZeroManual` | httpRequest | **Contrato.** `POST /internal/automations/google_reviews/drafts` con `X-Webhook-Secret` |
| `Remember Drafted Review` | code | Apunta el id en staticData **después** de que el push responde bien |
| `Publish Reply Webhook` | webhook | **Contrato.** Entrada `publish-reply`. En cada copia el path queda `publish-reply-{client}-{business}` |
| `Post Reply to Google` | code | **Contrato.** Publica la respuesta. Hace los HTTP dentro del código |

Camino feliz, ya en el JSON (no depende de que la inyección añada nodos):

`Generate AI Draft` → `Build Draft Payload` → `Push Draft to ZeroManual` → `Remember Drafted Review`

`Publish Reply Webhook` → `Post Reply to Google`

`duplicate_template` no vuelve a crear esos nodos si ya están. En grafos viejos que solo tienen `Generate AI Draft` → `Remember Drafted Review`, sigue añadiendo `Push Draft to ZeroManual` como rama extra y el webhook si faltan. Si `N8N_WEBHOOK_CRED_ID` está definido, sustituye el header `$env` del push por la credencial `httpHeaderAuth` (el secreto no entra en el JSON).

Publicar no lo hace ZeroManual contra la API de Google. Al aceptar (con o sin edición) el portal llama a `trigger_publish_reply`: `POST {N8N_WEBHOOK_BASE_URL}/publish-reply-{client_id}-{business_id}` con `review_id` y `final_reply`. Rechazar no llama a ese webhook.

`Post Reply to Google` es un nodo Code: un HTTP Request no puede leer `staticData`. El código hace el `POST` del token y el `PUT` de la respuesta. El webhook de n8n responde `onReceived`, así que ZeroManual no espera al `PUT`.

`Remember Drafted Review` lee `$('Generate AI Draft')`, no la respuesta HTTP. Si el push falla, no corre y la reseña se reintenta. El portal es idempotente por `review_id`: un reintento no abre un segundo borrador ni republica uno ya resuelto.

No hay nota adhesiva «CONFIGURACIÓN PENDIENTE» ni placeholders `YOUR_*`. No hay nodos de credencial OAuth de Google My Business. Google Sheets no está en el camino feliz: es opcional y no bloquea. Quien quiera un registro puede añadir un nodo Sheets en una rama lateral; no debe intercalarse antes de `Generate AI Draft`.

## APIs de Google y del LLM

Mismo cliente OAuth que ZeroManual (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` en la app). En **n8n** (no en el JSON) hay que definir:

- `ZEROMANUAL_GOOGLE_CLIENT_ID`
- `ZEROMANUAL_GOOGLE_CLIENT_SECRET`
- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` (si no, `$env` llega vacío)

No commitear esos valores.

1. `POST https://oauth2.googleapis.com/token` con `grant_type=refresh_token`, `refresh_token` de staticData y el client id/secret de entorno.
2. `GET https://mybusiness.googleapis.com/v4/{location_id}/reviews?pageSize=50&orderBy=updateTime%20desc`  
   `{location_id}` es `accounts/{account}/locations/{location}`, la misma familia que `GoogleBusinessClient.list_reviews`.
3. `PUT https://mybusiness.googleapis.com/v4/{reviewName}/reply` con `{"comment": final_reply}`.  
   `reviewName` es el `name` de la reseña (`accounts/…/reviews/…`). Si el webhook solo trae el id corto, se antepone `location_id + /reviews/`.

LLM (compartido, no por cliente): `POST {$env.ZEROMANUAL_LLM_BASE_URL || http://127.0.0.1:11434/v1}/chat/completions`, modelo `$env.ZEROMANUAL_LLM_MODEL` o `qwen3:8b`. Si el endpoint exige API key, añadir en `Call LLM` el header `Authorization: Bearer {{$env.ZEROMANUAL_LLM_API_KEY}}`.

`Generate AI Draft` deja en el item `review_name`, `reviewer_name`, `starRating`, `review_text` y `message.content` / `choices[0].message.content`. `Build Draft Payload` convierte eso en el cuerpo del POST. En n8n hace falta `ZEROMANUAL_PUBLIC_URL` y `ZEROMANUAL_WEBHOOK_SECRET` (el mismo valor que en ZeroManual), además de `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`. No commitear el secreto.

## Nombre del workflow

Formato: `NombreCliente_NegocioNN_YYYYMMDD` (fecha en Europe/Madrid).

- `NombreCliente`: `client_name` sin espacios ni símbolos (se conservan letras Unicode y dígitos). Vacío → `Cliente`.
- `NegocioNN`: **nunca** la calle ni el nombre comercial.
  - Un solo negocio del cliente → siempre `Negocio01`. Ejemplo: `CDVTrading_Negocio01_20261003`.
  - Varios negocios → ordinal estable: posición 1-based al ordenar por `created_at` y, en empate, `business_id`. `Negocio01`, `Negocio02`, …
- `activate_automation_for_client` calcula el ordinal con `negocio_ordinal` y lo pasa como `business_ordinal`.

El índice se mantiene mientras no se borre un negocio más antiguo. Borrar uno anterior puede renumerar a los demás en la **siguiente** activación. El nombre ya creado en n8n no se reescribe solo.

Antes el nombre era `{templateId}_{clientId}_{businessId}`.

## Carpeta n8n «Zeromanual»

Al crear la copia, `ensure_client_folder` resuelve la carpeta **por nombre exacto** `Zeromanual`. No hay UUID fijo en el código.

1. Proyecto: `N8N_PROJECT_ID` si está definido; si no, `GET /api/v1/projects` y el primero con `type=personal`, o el primero de la lista.
2. `GET /api/v1/projects/{projectId}/folders?filter={"name":"Zeromanual"}&skip=0&take=100`. Se acepta `{data:[{id,name}], count}` o una lista. El nombre tiene que coincidir exactamente. Si el filtro devuelve 400, se reintenta sin `filter` y se filtra en cliente.
3. Si no existe: `POST /api/v1/projects/{projectId}/folders` con `{"name":"Zeromanual"}`. Solo se crea esa carpeta. Un 409 vuelve a listar por si hubo una carrera.
4. Si la carpeta se resolvió, `POST /api/v1/workflows` incluye `parentFolderId`. Si n8n responde 400 porque no admite el campo (`additional properties` / `parentFolderId`), se crea sin él y se hace `PUT /api/v1/workflows/{id}` con `name`, `nodes`, `connections`, `settings`, `staticData` y `parentFolderId`. Si el PUT falla, se borra la copia y la activación falla: no se deja el workflow en la raíz cuando sí había carpeta.
5. Si `GET/POST /api/v1/projects` o `…/folders` responde 401, 403 o 404, se registra un aviso y la copia se crea **sin** `parentFolderId`. La activación sigue. Un 5xx, una plantilla ausente o un fallo de la API de workflows sigue abortando la activación.

La API key debería poder listar proyectos y carpetas. Si esa instancia no lo permite, el workflow queda en la raíz del proyecto y la activación no se bloquea.

## Importar y apuntar la plantilla

La plantilla debe quedar **inactiva**. No tiene `staticData` de cliente; si se ejecuta, `Load Client Context` falla a propósito.

La plantilla viva ya es `LZbxMigatCfYGGOn`. Este cambio **no** modifica `N8N_TEMPLATE_IDS`. Hay que hacer `PUT` de ese id (no crear otra plantilla ni reactivar CDV). El `PUT` público no acepta `meta` ni `pinData`.

En el entorno de **n8n** (no en el JSON):

- `ZEROMANUAL_GOOGLE_CLIENT_ID`
- `ZEROMANUAL_GOOGLE_CLIENT_SECRET`
- `ZEROMANUAL_PUBLIC_URL` (URL pública de ZeroManual, sin barra final)
- `ZEROMANUAL_WEBHOOK_SECRET` (el mismo valor que en ZeroManual)
- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`
- Opcional: `ZEROMANUAL_LLM_BASE_URL`, `ZEROMANUAL_LLM_MODEL`, `ZEROMANUAL_LLM_API_KEY`

```bash
jq '{name,nodes,connections,settings,staticData}' n8n/templates/google_reviews.json \
  > /tmp/google_reviews_api.json
# Si el PUT rechaza staticData:null, sustituye esa clave por {}.
curl -X PUT "$N8N_API_URL/workflows/LZbxMigatCfYGGOn" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/google_reviews_api.json
```

No llames a `/activate` sobre esa plantilla. No toques los workflows ya copiados para clientes.

En el proceso de ZeroManual, si aún no hay `N8N_WEBHOOK_CRED_ID`, el push usa `$env`. Si esa variable ya apunta a la credencial `httpHeaderAuth`, las activaciones nuevas la enganchan y quitan el header de entorno para no mandarlo vacío. Reiniciar la API solo hace falta si cambias variables de ZeroManual; el id de plantilla no cambia.

## Reactivar CDV: no en este cambio

Este cambio no desactiva ni reactiva el workflow de CDV, ni cambia `N8N_TEMPLATE_IDS`.

La plantilla viva (id que ya usa el entorno, por ejemplo `LZbxMigatCfYGGOn`) hay que actualizarla **en su sitio** con el JSON nuevo y dejarla inactiva. Las copias ya activadas de clientes no se parchean solas. `duplicate_template` solo corre al activar.

Cuando un operador decida reactivar CDV (fuera de este cambio): desactivar la automatización en el portal borra el workflow viejo y al volver a activar clona la plantilla vigente, con nombre `Cliente_NegocioNN_YYYYMMDD`, carpeta `Zeromanual`, push al portal y webhook de publicación. Hasta entonces esa copia sigue sin el bucle nuevo.
