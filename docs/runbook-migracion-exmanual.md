# Runbook: Stripe, Google y URL pública hacia exmanual.com

Procedimiento para cuando el founder apruebe el cambio. No está aplicado. No rota secretos, no borra el endpoint viejo de Stripe y no quita el redirect viejo de Google.

El inventario de variables está en `docs/migracion-dominio-exmanual.md`. Este runbook es el orden para cambiarlas en producción. `exmanual.es` no entra. Las URLs de n8n (`N8N_HOST`, `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_BASE_URL`, `N8N_API_URL`) siguen en `n8n.srv1255804.hstgr.cloud`.

Mientras duren los dos dominios, el código de este PR hace dos cosas que un `.env` solo no puede:

- Checkout, cancelación, portal de facturación y el redirect de Google salen del host de la petición si es `exmanual.com`, `www.exmanual.com` (se canonicaliza al apex) o `app.srv1255804.hstgr.cloud`. Cualquier otro host usa `ZEROMANUAL_PUBLIC_URL` / `GOOGLE_REDIRECT_URI`.
- El webhook acepta `ZEROMANUAL_STRIPE_WEBHOOK_SECRET` y, además, los secretos de `ZEROMANUAL_STRIPE_WEBHOOK_SECRETS` (separados por comas).

Hay que desplegar ese código antes de cambiar las URLs. Si se cambia el `.env` con el código viejo, un solo redirect y un solo secreto de webhook: el host que no coincida con la variable deja de cerrar OAuth o de verificar su endpoint.

Cada paso dice quién lo ejecuta. Los pasos de terminal son en el VPS, como usuario que ya administra Docker en `/opt/zeromanual`. No imprimas secretos en el chat ni en un ticket.

## 0. Anotar el estado actual (terminal del VPS, solo lectura)

```bash
cd /opt/zeromanual
git status --short
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
awk -F= '$1=="ZEROMANUAL_PUBLIC_URL" || $1=="MANUALZERO_PUBLIC_URL" || $1=="GOOGLE_REDIRECT_URI" {print}' .env | tee /root/exmanual-url-rollback.txt
python3 - <<'PY'
from pathlib import Path
for line in Path("/opt/zeromanual/.env").read_text().splitlines():
    if line.startswith("ZEROMANUAL_STRIPE_SECRET_KEY="):
        print("stripe_mode", line.split("=", 1)[1].strip()[:8])
    elif line.startswith(("ZEROMANUAL_STRIPE_WEBHOOK_SECRET=", "ZEROMANUAL_STRIPE_WEBHOOK_SECRETS=")):
        value = line.split("=", 1)[1].strip()
        print(line.split("=", 1)[0], "presente" if value else "vacio", len(value))
PY
```

Comprobación: la rama es `master` y no hay cambios en ficheros ya versionados. `/root/exmanual-url-rollback.txt` tiene la URL pública y el redirect actuales (esperado: host `app.srv1255804.hstgr.cloud`). `stripe_mode` es `sk_live_` o `sk_test_`. Anota el SHA: es el punto de vuelta atrás del código. Si `git status` muestra edits en ficheros versionados, para aquí.

El `.env` no está en git. `infra/docker-compose.vps.yml` tampoco. Un `git merge` posterior no los borra.

## 1. Añadir el redirect de Google (consola Google Cloud)

Quién: founder, en el navegador. No sustituyas el URI viejo.

1. Abre [Google Cloud → Credenciales](https://console.cloud.google.com/apis/credentials).
2. Arriba, elige el proyecto cuyo cliente OAuth coincide con el id del servidor. En el VPS, el id (no es el secreto):

   ```bash
   awk -F= '$1=="GOOGLE_CLIENT_ID" {print $2}' /opt/zeromanual/.env
   ```

   No ejecutes el mismo `awk` con `GOOGLE_CLIENT_SECRET`.
3. En **OAuth 2.0 Client IDs**, abre ese cliente.
4. En **Authorized redirect URIs**, pulsa **ADD URI**.
5. Pega exactamente `https://exmanual.com/client/google/callback`.
6. Deja la URI que ya está (la de `/root/exmanual-url-rollback.txt`, hoy `https://app.srv1255804.hstgr.cloud/client/google/callback`). No añadas `www`: Traefik manda `www.exmanual.com` al apex y el código canonicaliza ese host a `https://exmanual.com`.
7. Pulsa **Save**.

Comprobación: la lista muestra las dos URI. Google puede tardar un minuto en aplicarlas.

Vuelta atrás: **Delete** solo de `https://exmanual.com/client/google/callback` y **Save**. La URI vieja se queda.

## 2. Desplegar el código (terminal del VPS)

Quién: founder, por SSH, cuando este PR ya esté en `master`. Todavía no edites `.env`.

Si `docker ps --format '{{.Names}}'` muestra más de un contenedor cuyo nombre contiene `api`, usa el del proyecto de `/opt/zeromanual`, no otro.

```bash
cd /opt/zeromanual
git fetch origin master
git merge --ff-only origin/master
test -f apps/integrations/public_origin.py && echo 'codigo nuevo presente'
api_id=$(docker ps -qf name=api | head -1)
docker inspect "$api_id" --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
```

Comprobación: el merge es fast-forward y existe `apps/integrations/public_origin.py`. La base SQLite (`runtime/zeromanual.db` o el fichero que apunte `ZEROMANUAL_DB_PATH`) tiene que verse en un bind mount o en un volumen con nombre. Si la única copia está dentro del sistema de ficheros del contenedor, para aquí: recrear lo borraría.

Recrea solo `api`, con el override que ya publica exmanual.com. Sin ese segundo `-f`, Traefik pierde el router de `exmanual.com`.

```bash
cd /opt/zeromanual
docker compose -f infra/docker-compose.vps.yml -f infra/docker-compose.exmanual.yml up -d --force-recreate --no-deps api
curl -fsS -o /dev/null -w 'exmanual %{http_code}\n' https://exmanual.com/
curl -fsS -o /dev/null -w 'app %{http_code}\n' https://app.srv1255804.hstgr.cloud/
```

Si el `inspect` no muestra `/opt/zeromanual` montado en `/app`, la imagen lleva el código dentro y hace falta construir:

```bash
docker compose -f infra/docker-compose.vps.yml -f infra/docker-compose.exmanual.yml up -d --build --force-recreate --no-deps api
```

Comprobación: las dos URLs responden `200`. Recrear `api` tira los `state` de OAuth que estén en memoria (caducan a los 10 minutos). Quien tuviera Google abierto tiene que pulsar conectar otra vez. Las sesiones de Checkout ya creadas conservan la `success_url` con la que nacieron.

Vuelta atrás: solo si este paso se deshace antes de tocar `.env`.

```bash
cd /opt/zeromanual
git reset --hard <SHA_ANOTADO_EN_EL_PASO_0>
docker compose -f infra/docker-compose.vps.yml -f infra/docker-compose.exmanual.yml up -d --force-recreate --no-deps api
```

`reset --hard` deshace cambios sin commit en ficheros versionados. No toca `.env` ni `infra/docker-compose.vps.yml`.

## 3. Segundo endpoint de webhook (dashboard de Stripe)

Quién: founder, en el navegador. Mismo modo que el paso 0 (`sk_live_` → Live, `sk_test_` → Test). El interruptor está arriba a la derecha en el dashboard.

1. Abre [Developers → Webhooks](https://dashboard.stripe.com/webhooks).
2. Abre el endpoint que ya apunta a `https://app.srv1255804.hstgr.cloud/internal/stripe/webhook`. Anota los eventos. No pulses **Roll secret**. No lo borres ni lo desactives.
3. Pulsa **Add endpoint**.
4. **Endpoint URL:** `https://exmanual.com/internal/stripe/webhook`.
5. **Select events.** Marca los mismos que el endpoint viejo. La API actúa sobre `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted` e `invoice.payment_failed`. Si el viejo tiene más, márcalos también: un evento de más responde 200 y no cambia datos.
6. Versión de API: la que muestra el endpoint viejo en su ficha. No subas de versión en este paso.
7. **Add endpoint**. Stripe enseña el signing secret una vez (`whsec_...`). Guárdalo fuera del repo. No lo pegues en el entorno de n8n: n8n no verifica webhooks de Stripe.

Qué secreto usar:

- `ZEROMANUAL_STRIPE_WEBHOOK_SECRET` sigue siendo el `whsec_` del endpoint viejo. No lo cambies.
- `ZEROMANUAL_STRIPE_WEBHOOK_SECRETS` recibe solo el `whsec_` del endpoint nuevo.

Los dos endpoints reciben cada evento. El alta de suscripción es un upsert por cliente y tipo de automatización: la segunda entrega no crea otra fila. Un `customer.subscription.deleted` repetido vuelve a marcar la misma automatización como desactivada. En el dashboard se verán dos envíos por evento hasta que se retire el endpoint viejo.

Comprobación: en la lista hay dos endpoints activos, uno por dominio. El viejo conserva su secreto.

Vuelta atrás: abre el endpoint de exmanual.com y pulsa **Disable** o **Delete**. El de `app.srv1255804` no se toca. Si el secreto nuevo aún no está en `.env`, no hay nada que borrar ahí.

## 4. Cargar el secreto nuevo (terminal del VPS)

Quién: founder, por SSH. El valor no queda en el historial si entra por `read -rs`.

```bash
cd /opt/zeromanual
cp -a .env ".env.bak.$(date +%Y%m%d%H%M)"
read -rs NEW_STRIPE_WEBHOOK_SECRET
export NEW_STRIPE_WEBHOOK_SECRET
python3 - <<'PY'
import os
from pathlib import Path
path = Path("/opt/zeromanual/.env")
key = "ZEROMANUAL_STRIPE_WEBHOOK_SECRETS"
value = os.environ["NEW_STRIPE_WEBHOOK_SECRET"].strip()
if not value.startswith("whsec_") or "," in value:
    raise SystemExit("el secreto nuevo tiene que ser un único whsec_, sin comas")
lines = []
found = False
for line in path.read_text().splitlines():
    if line.startswith(key + "="):
        lines.append(f"{key}={value}")
        found = True
    else:
        lines.append(line)
if not found:
    lines.append(f"{key}={value}")
path.write_text("\n".join(lines) + "\n")
print(key, "escrito", len(value))
PY
unset NEW_STRIPE_WEBHOOK_SECRET
docker compose -f infra/docker-compose.vps.yml -f infra/docker-compose.exmanual.yml up -d --force-recreate --no-deps api
```

Comprobación: el script imprime `escrito` y una longitud, no el secreto. Las dos webs siguen en 200 (los `curl` del paso 2). En Stripe, abre el endpoint nuevo → **Send test webhook** no hace falta todavía; el smoke del paso 7 mira un evento real. Si quieres un control antes, en el endpoint nuevo elige un evento de prueba: sin `client_id` en el metadata, `checkout.session.completed` responde 400, y eso solo demuestra que la firma cuadra si el cuerpo del 400 no dice `Webhook inválido`. Un 400 con `Sesión Stripe sin client_id` significa que la firma del secreto nuevo ya vale.

Vuelta atrás:

```bash
cd /opt/zeromanual
# Restaura el .env de la copia .env.bak.<fecha> de este paso, o borra solo la línea
# ZEROMANUAL_STRIPE_WEBHOOK_SECRETS. No toques ZEROMANUAL_STRIPE_WEBHOOK_SECRET.
docker compose -f infra/docker-compose.vps.yml -f infra/docker-compose.exmanual.yml up -d --force-recreate --no-deps api
```

Desactiva el endpoint nuevo en Stripe para que no acumule fallos.

## 5. Cambiar la URL pública y el redirect por defecto (terminal del VPS)

Quién: founder, por SSH. Con el código del paso 2, un navegador en `app.srv1255804.hstgr.cloud` sigue volviendo a ese host. La variable pasa a ser el fallback y lo que usará n8n.

```bash
cd /opt/zeromanual
python3 - <<'PY'
from pathlib import Path
path = Path("/opt/zeromanual/.env")
updates = {
    "ZEROMANUAL_PUBLIC_URL": "https://exmanual.com",
    "GOOGLE_REDIRECT_URI": "https://exmanual.com/client/google/callback",
}
lines = path.read_text().splitlines()
seen = set()
out = []
for line in lines:
    key = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else None
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
legacy = "MANUALZERO_PUBLIC_URL"
out = [
    "MANUALZERO_PUBLIC_URL=https://exmanual.com" if line.startswith(legacy + "=") else line
    for line in out
]
path.write_text("\n".join(out) + "\n")
print("PUBLIC_URL y GOOGLE_REDIRECT_URI actualizados")
PY
docker compose -f infra/docker-compose.vps.yml -f infra/docker-compose.exmanual.yml up -d --force-recreate --no-deps api
curl -fsS -o /dev/null -w 'exmanual %{http_code}\n' https://exmanual.com/
curl -fsS -o /dev/null -w 'app %{http_code}\n' https://app.srv1255804.hstgr.cloud/
```

Comprobación: el script confirma las dos claves. No modifica `ZEROMANUAL_STRIPE_WEBHOOK_SECRET` ni las variables `N8N_*`. Las dos webs responden 200. `MANUALZERO_PUBLIC_URL` solo se reescribe si ya existía, para que no vuelva a imponer el host viejo.

Vuelta atrás: copia los valores de `/root/exmanual-url-rollback.txt` otra vez al `.env` (mismo script, con las URLs viejas) y recrea `api` con los dos ficheros compose.

## 6. La misma URL en el contenedor de n8n (terminal del VPS)

Quién: founder, por SSH. El compose de n8n no está en este repo. No recrees Traefik.

```bash
n8n_id=$(docker ps -qf name=n8n | head -1)
echo "container=$n8n_id"
docker inspect "$n8n_id" --format 'workdir={{index .Config.Labels "com.docker.compose.project.working_dir"}}{{println}}config={{index .Config.Labels "com.docker.compose.project.config_files"}}{{println}}service={{index .Config.Labels "com.docker.compose.service"}}'
docker inspect "$n8n_id" --format '{{range .Config.Env}}{{println .}}{{end}}' | awk -F= '$1=="ZEROMANUAL_PUBLIC_URL" || $1=="N8N_BLOCK_ENV_ACCESS_IN_NODE" {print}'
```

Anota el valor viejo de `ZEROMANUAL_PUBLIC_URL` (esperado: `https://app.srv1255804.hstgr.cloud`). En el `config` que imprima el inspect (fichero compose o `.env` de ese proyecto), cambia solo esa variable a `https://exmanual.com`, sin barra final. Deja `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`. Si el inspect no trae `config` ni `workdir`, la variable se puso al crear el contenedor y hay que cambiarla en el mismo sitio donde se creó (panel o compose que no etiquetó el contenedor). No inventes otra ruta.

Recrea solo ese servicio, con el mismo `-f` que salga en `config`:

```bash
docker compose -f <config> up -d --force-recreate --no-deps <service>
curl -fsS -o /dev/null -w 'n8n %{http_code}\n' https://n8n.srv1255804.hstgr.cloud/
```

Comprobación: n8n responde (200 o el 401 de su login; no un fallo de conexión) y `https://exmanual.com/` sigue en 200.

### Workflows ya clonados

Hay dos formas de URL en el nodo `Push Draft to ZeroManual`:

- La plantilla actual (`n8n/templates/google_reviews.json`) guarda una expresión: `$env.ZEROMANUAL_PUBLIC_URL` más `/internal/automations/google_reviews/drafts`. `duplicate_template` copia los nodos tal cual. Esas copias no tienen el host escrito. En la siguiente ejecución leen el entorno del contenedor. Tras este paso llaman a `https://exmanual.com`. Siguen funcionando porque ese dominio sirve la misma API.
- Las copias de grafos viejos, sin ese nodo, recibieron una URL literal al activarse (`apps/integrations/n8n_client.py`, `_inject_draft_push_node`), con el `ZEROMANUAL_PUBLIC_URL` de la app en ese momento. Esa URL no se reescribe sola. Siguen llamando a `https://app.srv1255804.hstgr.cloud`, que sigue vivo.

Para ver cuál es cuál, en el VPS. No actives `set -x`: el `.env` tiene secretos y el punto siguiente los exporta en esa sesión. Cierra el SSH al terminar. Si `. ./.env` se queja por espacios, exporta a mano solo `N8N_API_URL` y `N8N_API_KEY`, sin imprimirlos.

```bash
cd /opt/zeromanual
set -a
. ./.env
set +a
curl -sS -H "X-N8N-API-KEY: $N8N_API_KEY" "$N8N_API_URL/workflows?limit=250" \
  | jq -r '.data[].id' | while read -r id; do
    curl -sS -H "X-N8N-API-KEY: $N8N_API_KEY" "$N8N_API_URL/workflows/$id" \
      | jq -r --arg id "$id" '
          . as $wf
          | .nodes[]?
          | select(.name == "Push Draft to ZeroManual")
          | $id + " " + $wf.name + " " + (.parameters.url // "")'
  done
unset N8N_API_KEY
```

Actualizar una literal, si se quiere: en la UI de n8n (`https://n8n.srv1255804.hstgr.cloud`), abre el workflow, nodo **Push Draft to ZeroManual**, y cambia el host de la URL a `https://exmanual.com`. Deja el path `/internal/automations/google_reviews/drafts`. Guarda y no desactives el workflow. No hace falta tocar las que todavía muestran `$env.ZEROMANUAL_PUBLIC_URL`. No hace falta reactivar clientes en el portal: eso borra la copia y clona otra.

Vuelta atrás de este paso: devuelve `ZEROMANUAL_PUBLIC_URL` del contenedor n8n al valor anotado y recrea solo ese servicio con `--no-deps`. Las expresiones vuelven al host viejo en la siguiente ejecución. Las literales que hayas editado a mano hay que revertirlas a mano.

## 7. Smoke

Quién: founder. El modo de Stripe es el del paso 0.

1. **Checkout vuelve a exmanual.com.** Entra en `https://exmanual.com/client`, inicia un checkout. Con `sk_test_`, tarjeta `4242 4242 4242 4242`, fecha futura, CVC cualquiera. Con `sk_live_`, es un cargo real: elige tú el importe. El navegador tiene que abrir `https://exmanual.com/client/checkout/success?session_id=cs_...` y acabar en el portal. Cancelar un checkout (no pagues) tiene que dejar el navegador en `https://exmanual.com/?checkout=cancelled`. En el dashboard de Stripe, la sesión muestra esa `success_url`.
2. **Webhook recibido.** En Developers → Webhooks, el endpoint de `https://exmanual.com/internal/stripe/webhook` tiene el evento con respuesta 200. El endpoint viejo muestra otro envío del mismo evento, también 200. Eso es la convivencia, no un doble cobro.
3. **Google Allow vuelve a exmanual.com.** En `https://exmanual.com/client`, conecta Google y pulsa Allow. La barra de dirección pasa por `https://exmanual.com/client/google/callback` y termina en `/client?connected=1` o `activated=`. Control del host viejo, sin completar el consentimiento si no quieres: en `https://app.srv1255804.hstgr.cloud/client` pulsa conectar y, en la URL de `accounts.google.com`, `redirect_uri` es `https://app.srv1255804.hstgr.cloud/client/google/callback`.
4. **Draft de n8n.** Ejecuta una vez el workflow del cliente (o espera una reseña). El borrador aparece en el portal. En el VPS:

   ```bash
   api_id=$(docker ps -qf name=api | head -1)
   docker logs --since 30m "$api_id" 2>&1 | grep -F '/internal/automations/google_reviews/drafts'
   code=$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
     https://exmanual.com/internal/automations/google_reviews/drafts \
     -H 'Content-Type: application/json' -d '{}')
   echo "drafts sin secreto: $code"
   ```

   El `POST` real del workflow tiene que ser 200. El `curl` sin secreto tiene que ser 401. Un 200 en ese `curl` significa que la comprobación del secreto no está cerrada: para y no sigas.

Los cuatro tienen que cumplirse antes de retirar nada del host viejo.

## 8. Cuándo retirar las URLs viejas

Cuando el smoke lleve tiempo en verde y el listado del paso 6 ya no muestre ninguna URL literal con `app.srv1255804.hstgr.cloud`. Hasta entonces el host viejo se queda.

Orden, el día que se decida:

1. **Stripe (dashboard).** Desactiva y borra el endpoint de `app.srv1255804.hstgr.cloud`. El de exmanual.com se queda. Luego, en el `.env` del VPS, mueve el `whsec_` de exmanual.com a `ZEROMANUAL_STRIPE_WEBHOOK_SECRET` y borra la línea `ZEROMANUAL_STRIPE_WEBHOOK_SECRETS`. Recrea `api` con los dos compose. Comprobación: un evento nuevo solo aparece en el endpoint de exmanual.com, con 200.
2. **Google (consola).** Borra solo la URI de `app.srv1255804.hstgr.cloud`. Deja `https://exmanual.com/client/google/callback`. **Save**. Comprobación: un conectar en exmanual.com sigue volviendo a exmanual.com. Conectar en el host viejo pasará a fallar en Google, y eso es el corte de OAuth en ese host.
3. **Hosts admitidos (terminal del VPS).** Añade `ZEROMANUAL_PUBLIC_HOSTS=exmanual.com,www.exmanual.com` al `.env` y recrea `api`. A partir de ahí un request con el host viejo también genera URLs de exmanual.com. Comprobación: checkout iniciado en el host viejo, si el router sigue vivo, vuelve a exmanual.com.
4. **Router Traefik del host viejo.** Está en `infra/docker-compose.vps.yml`, que no está en git. Quitarlo es otro cambio y otro recreate. No forma parte de este runbook. Hazlo solo después de los puntos 1 a 3, y conserva el override `infra/docker-compose.exmanual.yml`.

No retires `N8N_API_URL` ni el dominio `n8n.srv1255804.hstgr.cloud`.
