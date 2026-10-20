"""Páginas legales públicas de ExManual. Sin datos fiscales inventados."""

from __future__ import annotations

_MARK = (
    '<svg viewBox="0 0 32 32" width="27" height="27" aria-hidden="true">'
    '<circle cx="16" cy="16" r="15.11" fill="none" stroke="currentColor" stroke-width="1.78"/>'
    '<circle cx="16" cy="16" r="7.7" fill="#4f46e5"/></svg>'
)

_GOOGLE_LIMITED_USE = (
    "El uso y la transferencia de la información recibida de las API de Google "
    "por parte de ExManual se ajustará a la Política de datos de usuario de los "
    "servicios de API de Google, incluidos los requisitos de uso limitado"
)

_SHELL = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>__TITLE__ — ExManual</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='15.11' fill='none' stroke='%230e1116' stroke-width='1.78'/><circle cx='16' cy='16' r='7.7' fill='%234f46e5'/></svg>" />
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root { --bg:#f6f7f9; --fg:#0e1116; --fg-2:#3a4150; --fg-3:#6b7280; --line:#e6e9ee; --accent:#4f46e5; --card:#fff; }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); color: var(--fg); }
  body { font-family: "Space Grotesk", system-ui, sans-serif; font-size: 16px; line-height: 1.6; }
  a { color: var(--accent); }
  header { position: sticky; top: 0; z-index: 20; background: rgba(246,247,249,.86); backdrop-filter: blur(12px); border-bottom: 1px solid var(--line); }
  .bar { max-width: 920px; margin: 0 auto; padding: 13px 24px; display: flex; align-items: center; gap: 18px; }
  .brand { display: flex; align-items: center; gap: 10px; color: var(--fg); text-decoration: none; font-weight: 500; font-size: 19px; letter-spacing: -.02em; }
  nav { display: flex; gap: 4px; flex-wrap: wrap; }
  nav a { color: #3a4150; text-decoration: none; font-size: 14.5px; font-weight: 500; padding: 7px 12px; border-radius: 8px; }
  nav a:hover { color: var(--accent); }
  main { max-width: 800px; margin: 0 auto; padding: 48px 24px 24px; overflow-wrap: break-word; }
  h1 { font-size: clamp(32px, 5vw, 44px); letter-spacing: -.03em; line-height: 1.1; margin: 0 0 8px; }
  .updated { color: var(--fg-3); margin: 0 0 28px; font-size: 14px; }
  h2 { font-size: 22px; letter-spacing: -.02em; margin: 32px 0 8px; }
  p, li { color: var(--fg-2); }
  ul { padding-left: 1.2rem; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 18px 20px; margin: 16px 0; }
  .pending, .review { font-weight: 600; color: #0e1116; }
  table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid var(--line); border-radius: 16px; overflow: hidden; font-size: 14.5px; table-layout: fixed; }
  th, td { text-align: left; vertical-align: top; padding: 12px 14px; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
  th { color: var(--fg-3); font-size: 12px; letter-spacing: .04em; text-transform: uppercase; }
  tr:last-child td { border-bottom: 0; }
  code { font-size: .92em; overflow-wrap: anywhere; }
  footer { max-width: 920px; margin: 48px auto 0; padding: 28px 24px 40px; border-top: 1px solid var(--line); display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; color: #9099a6; font-size: 13.5px; }
  footer nav { gap: 14px; }
  footer a { color: #3a4150; padding: 0; font-size: 13.5px; }
  @media (max-width: 720px) { .bar { align-items: flex-start; flex-direction: column; gap: 8px; } }
</style>
</head>
<body>
<header>
  <div class="bar">
    <a class="brand" href="/">__MARK__<span>exmanual</span></a>
    <nav aria-label="Principal">
      <a href="/#zm-grid">Automatizaciones</a>
      <a href="/#zm-how">Cómo funciona</a>
      <a href="/#zm-grid">Precios</a>
      <a href="/client">Área privada</a>
    </nav>
  </div>
</header>
<main>
  <h1>__TITLE__</h1>
  <p class="updated">Última actualización: 20 de octubre de 2026 · hola@exmanual.com</p>
  __BODY__
</main>
<footer>
  <span>ExManual</span>
  <nav aria-label="Información legal">
    <a href="/aviso-legal">Aviso legal</a>
    <a href="/privacidad">Privacidad</a>
    <a href="/cookies">Cookies</a>
    <a href="/terminos">Términos</a>
  </nav>
</footer>
</body>
</html>
"""


def _page(title: str, body: str) -> str:
    return (
        _SHELL.replace("__TITLE__", title)
        .replace("__MARK__", _MARK)
        .replace("__BODY__", body)
    )


def render_legal_page(slug: str) -> str:
    try:
        title, body = _PAGES[slug]
    except KeyError as exc:
        raise KeyError(slug) from exc
    return _page(title, body)


_AVISO = """
<p>Información exigida por el artículo 10 de la Ley 34/2002, de servicios de la sociedad de la información y de comercio electrónico (LSSI-CE).</p>
<div class="card">
  <p><strong>Marca:</strong> ExManual</p>
  <p><strong>Titular:</strong> <span class="pending">[PENDIENTE]</span> nombre fiscal. Solo lo conoce el titular.</p>
  <p><strong>Forma jurídica:</strong> <span class="pending">[PENDIENTE]</span> autónomo o sociedad. No se indica aquí hasta que el titular lo confirme.</p>
  <p><strong>NIF:</strong> <span class="pending">[PENDIENTE]</span></p>
  <p><strong>Domicilio:</strong> <span class="pending">[PENDIENTE]</span></p>
  <p><strong>Correo:</strong> <a href="mailto:hola@exmanual.com">hola@exmanual.com</a></p>
  <p><strong>Datos registrales:</strong> <span class="pending">[PENDIENTE]</span> Registro Mercantil (tomo, folio, hoja e inscripción) si es una sociedad. Si es autónomo, este apartado no aplica y se retirará la mención.</p>
</div>
<h2>Actividad</h2>
<p>ExManual ofrece a negocios suscripciones de automatización: responder reseñas de Google y, cuando estén disponibles, otras tareas del catálogo (reels, newsletters, mensajes). El servicio se contrata en este sitio y se usa desde el portal de cliente.</p>
<h2>Precios y condiciones</h2>
<p>Los precios, la prueba y la cancelación están en los <a href="/terminos">términos de la suscripción</a>. El tratamiento de datos está en la <a href="/privacidad">política de privacidad</a> y el almacenamiento técnico en la <a href="/cookies">política de cookies</a>.</p>
"""

_PRIVACIDAD = f"""
<p>Esta política explica cómo ExManual trata datos personales según el Reglamento (UE) 2016/679 (RGPD) y la Ley Orgánica 3/2018 (LOPDGDD).</p>
<h2>Responsable</h2>
<div class="card">
  <p><strong>Marca:</strong> ExManual</p>
  <p><strong>Titular:</strong> <span class="pending">[PENDIENTE]</span> nombre fiscal.</p>
  <p><strong>NIF:</strong> <span class="pending">[PENDIENTE]</span></p>
  <p><strong>Domicilio:</strong> <span class="pending">[PENDIENTE]</span></p>
  <p><strong>Forma jurídica:</strong> <span class="pending">[PENDIENTE]</span> autónomo o sociedad.</p>
  <p><strong>Contacto:</strong> <a href="mailto:hola@exmanual.com">hola@exmanual.com</a></p>
</div>
<h2>Qué datos tratamos</h2>
<ul>
  <li>Cuenta: nombre del negocio, correo y contraseña (la contraseña se guarda como huella, no en claro).</li>
  <li>Suscripción: producto contratado, precio, moneda, estado y los identificadores que devuelve Stripe.</li>
  <li>Google, cuando conectas Business Profile: correo de esa cuenta de Google; cuentas y ficha (nombre del local y dirección del establecimiento); reseñas (nombre público de quien reseña, estrellas, texto e identificador).</li>
  <li>Borradores de respuesta y el modo elegido: aprobación previa o publicación automática.</li>
  <li>Datos técnicos de la visita: dirección IP y agente de usuario al cargar la página o llamar a la API.</li>
</ul>
<h2>Finalidades y base jurídica</h2>
<ul>
  <li>Crear la cuenta, prestar la automatización y atenderla. Base: ejecución del contrato (art. 6.1.b RGPD).</li>
  <li>Cobrar la suscripción, emitir la factura y llevar la contabilidad. Base: obligación legal (art. 6.1.c RGPD).</li>
  <li>Leer la ficha y las reseñas, y publicar la respuesta que apruebas o que el modo automático publica. Base: el contrato del producto de reseñas, con el permiso que concedes en la pantalla de Google.</li>
  <li>Mantener la sesión, recordar la moneda que eliges y completar el alta tras el pago. Base: el servicio que pides (art. 6.1.b RGPD y art. 22.2 LSSI para el almacenamiento técnico).</li>
  <li>Seguridad y diagnóstico de fallos. Base: interés legítimo (art. 6.1.f RGPD), limitado a ese fin.</li>
</ul>
<h2>Plazos de conservación</h2>
<ul>
  <li>Cuenta y suscripción: mientras el contrato sigue vivo. Después, bloqueados durante los plazos legales (en general, cuatro años de obligaciones tributarias y seis años de documentación mercantil).</li>
  <li>Credenciales de Google: hasta que desconectas la cuenta en el portal o revocas el permiso en Google.</li>
  <li>Borradores de reseñas: mientras la automatización sigue de alta. El código no aplica un plazo de borrado más corto.</li>
  <li>Sesión del portal: hasta que cierras sesión. La del área de administración, hasta que cierras la pestaña.</li>
</ul>
<h2>Destinatarios y encargados</h2>
<p>No vendemos datos personales ni los cedemos para que un tercero los use por su cuenta. Intervienen estos encargados:</p>
<ul>
  <li><strong>Stripe.</strong> Alta, cobro y cancelación de la suscripción.</li>
  <li><strong>Google.</strong> Acceso a Business Profile, identidad de la cuenta (correo) y, en la web, las tipografías servidas desde sus servidores.</li>
  <li><strong>Hostinger.</strong> Alojamiento del servicio en un VPS situado en la Unión Europea.</li>
  <li><strong>OpenRouter.</strong> Es el proveedor de IA que redacta las respuestas a las reseñas. El flujo de n8n llama a <code>https://openrouter.ai/api/v1/chat/completions</code>. El modelo indicado en ese flujo es <code>nvidia/nemotron-3-super-120b-a12b:free</code>, con reserva <code>gemma-4-31b-it:free</code> y <code>gemma-4-26b-a4b-it:free</code>.</li>
  <li><strong>Anthropic (Claude).</strong> Los agentes internos de la empresa pueden llamar a la API de Anthropic si hay una clave configurada (<code>apps/llm/claude_client.py</code>). Ese canal no es el que redacta las respuestas a reseñas del portal.</li>
  <li><strong>n8n autoalojado</strong> en el VPS de Hostinger. Orquesta la automatización (leer reseñas, pedir el borrador y devolverlo al portal). No es n8n Cloud.</li>
</ul>
<p>Al abrir la landing, el navegador pide librerías a unpkg.com y tipografías a Google. Esas peticiones muestran la IP y el agente de usuario a esos prestadores. No instalan cookies en la carga comprobada. El portal solo pide las tipografías.</p>
<h2>Transferencias internacionales</h2>
<p>Hostinger (VPS en la UE) y el n8n autoalojado en ese VPS tratan los datos en la Unión Europea.</p>
<p>Stripe, Google, OpenRouter y Anthropic pueden tratar datos fuera del Espacio Económico Europeo, en particular en Estados Unidos. La transferencia se ampara en las cláusulas contractuales tipo de la Comisión Europea u otra garantía del artículo 46 del RGPD cuando no hay una decisión de adecuación. <span class="review">[REVISAR]</span> Confirmar que el titular ha firmado con cada uno el contrato de encargo y esas cláusulas.</p>
<h2>Datos de Google</h2>
<p><a href="https://developers.google.com/terms/api-services-user-data-policy">{_GOOGLE_LIMITED_USE}</a>.</p>
<p><strong>Qué se lee.</strong> Reseñas de Google Business Profile (nombre público, estrellas, texto e identificador) y la ficha (cuentas, nombre del local y dirección). También el correo de la cuenta de Google, solo para saber qué cuenta quedó conectada. Los permisos que pide el código son <code>business.manage</code>, <code>userinfo.email</code> y <code>openid</code>.</p>
<p><strong>Gmail.</strong> El código del newsletter no usa Gmail. No hay permiso de la API de Gmail ni un flujo que lea el buzón. El catálogo describe «Mailchimp o Gmail» como conexión prevista de ese producto, que todavía no está implementada. El correo SMTP de las facturas de la propia empresa, si se configura, no es el buzón del cliente.</p>
<p><strong>Para qué.</strong> Conectar la ficha, redactar una respuesta a cada reseña y publicarla cuando tú la apruebas o, si activas ese modo, de forma automática.</p>
<p><strong>Qué no se hace.</strong> Esos datos no se venden. No se usan para publicidad. No se usan para entrenar modelos generales de ExManual. <span class="review">[REVISAR]</span> El texto de la reseña sale hacia OpenRouter para redactar la respuesta. Hay que dejar cerrado por escrito con ese proveedor que no entrena modelos generales con datos procedentes de las API de Google.</p>
<p><strong>Cómo revocar el acceso.</strong> En el portal, Cuentas, desconecta Google: se borran las credenciales guardadas. También puedes retirar el permiso de la aplicación en <a href="https://myaccount.google.com/permissions">la cuenta de Google</a>. A partir de ese momento la automatización deja de leer reseñas y de publicar.</p>
<h2>Derechos (ARSOPL) y la AEPD</h2>
<p>Puedes pedir acceso, rectificación, supresión, oposición, limitación del tratamiento y portabilidad, y oponerte a decisiones automatizadas que te afecten de forma jurídica o similar. Para publicar respuestas sin revisión tienes que haber activado tú ese modo, y puedes volver a la aprobación en el portal.</p>
<p>Escríbenos a <a href="mailto:hola@exmanual.com">hola@exmanual.com</a>. También puedes reclamar ante la Agencia Española de Protección de Datos (<a href="https://www.aepd.es">www.aepd.es</a>).</p>
"""

_COOKIES = """
<p>Inventario de la landing (<code>/</code>) y del portal (<code>/client</code>), revisado en el código y al cargar las dos páginas en local, sin iniciar sesión.</p>
<div class="card">
  <p>Todo lo que hay es técnico. No hay cookies de análisis, de publicidad ni de terceros no técnicas. Por eso esta web no muestra un banner de cookies (art. 22.2 de la LSSI-CE).</p>
</div>
<h2>Cookies HTTP</h2>
<p>Ninguna. Ni la aplicación ni los recursos externos de esa carga (tipografías de Google y librerías de unpkg en la landing) enviaron <code>Set-Cookie</code>. <code>document.cookie</code> quedó vacío.</p>
<h2>Almacenamiento del navegador</h2>
<p>En esa misma carga, <code>localStorage</code> y <code>sessionStorage</code> quedaron vacíos. El código solo escribe una clave cuando ocurre la acción de la tabla.</p>
<table>
  <thead>
    <tr><th>Nombre</th><th>Finalidad</th><th>Duración</th><th>Tipo</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><code>mz_client_token</code><br>localStorage</td>
      <td>Sesión del portal de cliente después de entrar o crear la cuenta.</td>
      <td>Hasta que cierras sesión o el servidor rechaza el token. Sigue al cerrar el navegador.</td>
      <td>Técnica</td>
    </tr>
    <tr>
      <td><code>mz_token</code><br>sessionStorage</td>
      <td>Sesión de administración, solo si el acceso de administrador tiene éxito (desde la landing o desde <code>/admin</code>).</td>
      <td>Hasta cerrar la pestaña.</td>
      <td>Técnica</td>
    </tr>
    <tr>
      <td><code>zm_pending_activations</code><br>localStorage</td>
      <td>Recordar las automatizaciones elegidas para activarlas tras el pago o el alta.</td>
      <td>Hasta que la activación termina. Si falla, se conserva la lista pendiente.</td>
      <td>Técnica</td>
    </tr>
    <tr>
      <td><code>zm_currency</code><br>localStorage</td>
      <td>Recordar si elegiste ver los precios en euros o en dólares.</td>
      <td>Hasta que cambias la moneda o borras los datos del sitio. No se crea hasta que usas el selector.</td>
      <td>Técnica (preferencia que tú eliges)</td>
    </tr>
    <tr>
      <td><code>zm_tweaks</code><br>localStorage</td>
      <td>El código de la landing puede guardar ajustes de interfaz. La pantalla publicada no llama a esa escritura.</td>
      <td>No se crea en una visita normal. Si llegara a existir, duraría hasta borrar los datos del sitio.</td>
      <td>Técnica (preferencia de interfaz, no usada)</td>
    </tr>
  </tbody>
</table>
<p>No hay otras claves de <code>localStorage</code> ni de <code>sessionStorage</code> en la landing ni en el portal.</p>
"""

_TERMINOS = """
<p>Estas condiciones regulan la suscripción a las automatizaciones de ExManual. El público del servicio es de empresa a empresa (B2B): negocios y profesionales que contratan para su actividad.</p>
<h2>Prueba de 14 días</h2>
<p>Cada suscripción incluye una prueba de 14 días. Para empezarla se pide una tarjeta. No se cobra hasta que la prueba termina. Si cancelas antes, no sigue el cobro de los periodos siguientes.</p>
<h2>Precio mensual, IVA incluido</h2>
<p>El precio es fijo al mes, por automatización, con el IVA del 21&nbsp;% incluido. Son los importes del catálogo de cobro (céntimos de euro al mes):</p>
<ul>
  <li>Responder reseñas de Google: 29,00&nbsp;€ al mes.</li>
  <li>Publicar reels en redes: 39,00&nbsp;€ al mes.</li>
  <li>Enviar newsletters: 24,00&nbsp;€ al mes.</li>
  <li>Responder mensajes directos y comentarios: 34,00&nbsp;€ al mes.</li>
</ul>
<p>Hoy el alta desde la web está abierta para las reseñas de Google. El resto figura en el catálogo y se cobra con estas cifras cuando se puede contratar.</p>
<p>Si eliges facturación anual, el importe de ese año es diez veces el precio mensual (equivale a dos meses sin cargo). Si eliges dólares en la web, el catálogo usa la misma cifra en USD. A partir del segundo negocio de la misma automatización en un mismo pago, ese negocio adicional queda al 80&nbsp;% del precio (20&nbsp;% de descuento).</p>
<h2>Cancelación</h2>
<p>Puedes cancelar en cualquier momento desde el portal de cliente, con el botón «Cancelar suscripción» de la automatización.</p>
<p><span class="review">[REVISAR]</span> El efecto previsto es que la baja opere al final del periodo ya pagado y que el servicio siga hasta entonces. Hay que confirmarlo antes de dar esta frase por cerrada: la llamada actual a Stripe cancela la suscripción en el acto, no al final del periodo.</p>
<h2>Qué se publica</h2>
<p>En reseñas de Google, el modo inicial es de aprobación: la respuesta se publica cuando tú la apruebas. Si activas las respuestas automáticas, ExManual la publica sin esa revisión. Puedes volver a la aprobación desde el portal cuando quieras. El texto lo redacta el flujo de IA a partir de la reseña; tú sigues siendo responsable de lo que queda publicado en tu ficha.</p>
<h2>Responsabilidad</h2>
<p>ExManual presta una herramienta de automatización. No garantiza un volumen de reseñas, un resultado comercial ni que Google, Stripe u otros terceros estén siempre disponibles. Nada de lo anterior limita la responsabilidad que la ley española no permita excluir.</p>
<h2>Ley aplicable</h2>
<p>Estos términos se rigen por la ley española. En los contratos con clientes que actúan en su actividad empresarial, conocen de los conflictos los juzgados españoles. El fuero concreto depende del domicilio del titular, que está <span class="pending">[PENDIENTE]</span> en el <a href="/aviso-legal">aviso legal</a>.</p>
<h2>Desistimiento</h2>
<p><span class="review">[REVISAR]</span> Las personas consumidoras tienen, con carácter general, 14 días para desistir. El servicio se dirige a empresas y profesionales (B2B). Confirmar si esta nota debe quedarse, adaptarse o retirarse.</p>
"""

_PAGES: dict[str, tuple[str, str]] = {
    "aviso-legal": ("Aviso legal", _AVISO),
    "privacidad": ("Política de privacidad", _PRIVACIDAD),
    "cookies": ("Política de cookies", _COOKIES),
    "terminos": ("Términos de la suscripción", _TERMINOS),
}
