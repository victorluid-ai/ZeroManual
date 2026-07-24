/* ZeroManual — bilingual (ES default / EN) automation marketplace, ported
   faithfully from the Claude Design source (ZeroManual.dc.html). The fake
   credit-card checkout step is replaced with the site's real register +
   activate flow — there is no payment backend to charge against yet. */
const { useState, useEffect } = React;

const CART_HANDOFF_KEY = "zm_pending_activations";

// Only these have a real automation_type in the backend today; the rest
// (reminders, requests) stay in the catalog for content parity but are
// silently skipped on handoff since /client/automations would 400 on them.
const AUTOMATION_TYPE_MAP = {
  reviews: "google_reviews",
  reels: "instagram_posts",
  newsletter: "newsletter",
  dms: "dms",
};

const T = {
  en: {
    nav: { automations: "Automations", how: "How it works", pricing: "Pricing", cart: "Cart", account: "Client area", getStarted: "Get started", login: "Log in" },
    hero: { eyebrow: "AI automations for local business", h1: "Stop doing the busywork.", sub: "ZeroManual puts the repetitive jobs — replying to reviews, posting reels, sending newsletters — on autopilot. Pick an automation, subscribe, and it just runs.", browse: "Browse automations", how: "See how it works", t3: "Live in 5 minutes" },
    grid: { title: "Browse automations", sub: "Flat monthly price each. Subscribe in one click — no contracts, cancel anytime.", annual: "Billed annually · 2 months free", kicker: "Marketplace" },
    filters: { all: "All", reviews: "Reviews", social: "Social", email: "Email", messaging: "Messaging" },
    card: { subscribe: "Subscribe", added: "Added", details: "View details →", active: "Active ✓", activating: "Activating…", comingSoon: "Coming soon" },
    badge: { popular: "Most popular", new: "New" },
    how: { kicker: "How it works", title: "Live in three steps", sub: "No agencies, no setup projects. Connect your accounts and ZeroManual handles the rest.", s1t: "Pick your automations", s1b: "Choose from the menu above. Mix and match — every one is a flat monthly price.", s2t: "Connect your accounts", s2b: "Link Google, Instagram, or email in a couple of taps. We never post without your rules.", s3t: "It runs 24/7", s3b: "ZeroManual works around the clock and reports back. Adjust or cancel anytime." },
    band: { sub: "No contracts. No setup fees. Cancel anytime from your dashboard.", cta: "Start free →" },
    footer: "Small automations, big AI. © 2026 ZeroManual.",
    example: { kicker: "Live demo", title: "See it work, live", sub: "A task comes in. ZeroManual handles it in your voice. You do nothing. Swipe to see more." },
    integrations: { title: "Connects to the tools you already use" },
    faq: { kicker: "FAQ", title: "Frequently asked questions", sub: "Everything you need to know before you start.", items: [
      { q: "Does ZeroManual post without my permission?", a: "No. You set the rules and can review or approve before anything goes out. Negative reviews are always flagged for you to handle." },
      { q: "Is it safe to connect my accounts?", a: "Yes. We use official, encrypted connections and never access more than we need or share your data." },
      { q: "Can I cancel anytime?", a: "Anytime, right from your dashboard. No contracts and no penalties." },
      { q: "Does it work in my language?", a: "Yes. It replies and posts in English, Spanish and more — always in your business’s tone." },
      { q: "Do I need technical skills?", a: "None. Connect your accounts in a few taps and ZeroManual handles the rest." },
      { q: "How much does it cost?", a: "A flat monthly price per automation, from $19/mo. Mix and match, cancel anytime." },
    ] },
    drawer: { checkout: "Checkout", cart: "Your automations" },
    checkout: { start: "Create account & start free trial", disclaimer: "You won't be charged until your trial ends. Cancel anytime." },
    cart: { remove: "Remove", total: "Total", checkout: "Checkout →", emptyTitle: "Your cart is empty.", emptySub: "Pick an automation to get started." },
    detail: { what: "What it does", connects: "Connects to", subscribe: "Subscribe", inCart: "In cart — view", example: "See it in action", auto: "Automatic", setup: "Setup", setupVal: "~5 minutes", langsK: "Languages", langsV: "Spanish · English", trialK: "Free trial" },
    per: { mo: "/mo", yr: "/yr" },
    bandTitle: (n) => "Every automation comes with a " + n + "-day free trial.",
    checkoutTrial: (n) => n + "-day free trial",
    countLabel: (n) => n + (n === 1 ? " automation" : " automations"),
    talkToUs: { note: "Prefer we set it up for you, tailored to your business?", link: "Talk to us", email: "hello@zeroman.co" },
    login: {
      title: "Private area", sub: "Sign in with your username or email.",
      registerTitle: "Create account", registerSub: "Register as a client.",
      identLabel: "Username or email", nameLabel: "Name", passLabel: "Password",
      submit: "Sign in →", submitting: "Signing in…", registerSubmit: "Create account →", registering: "Creating…",
      error: "Incorrect username or password.", registerError: "Could not create account.", passMin: "Minimum 8 characters.",
      switchToRegister: "No account? Register", switchToLogin: "Already have an account? Sign in",
    },
    subscribe: {
      sub: "Create your account or sign in — it activates instantly, right after this.",
      cta: "Subscribe & continue →", ctaLogin: "Sign in & continue →",
      connecting: "Connecting Google…", activating: "Activating…",
      error: "Couldn't complete the subscription. Try again.",
    },
  },
  es: {
    nav: { automations: "Automatizaciones", how: "Cómo funciona", pricing: "Precios", cart: "Carrito", account: "Área privada", getStarted: "Empezar", login: "Iniciar sesión" },
    hero: { eyebrow: "Automatizaciones con IA para negocios locales", h1: "Deja de hacer el trabajo repetitivo.", sub: "ZeroManual pone en piloto automático las tareas repetitivas — responder reseñas, publicar reels, enviar newsletters. Elige una automatización, suscríbete y funciona sola.", browse: "Ver automatizaciones", how: "Ver cómo funciona", t3: "Listo en 5 minutos" },
    grid: { title: "Explora las automatizaciones", sub: "Precio mensual fijo cada una. Suscríbete con un clic — sin contratos, cancela cuando quieras.", annual: "Facturación anual · 2 meses gratis", kicker: "Catálogo" },
    filters: { all: "Todas", reviews: "Reseñas", social: "Redes", email: "Correo", messaging: "Mensajes" },
    card: { subscribe: "Suscribirse", added: "Añadido", details: "Ver detalles →", active: "Activa ✓", activating: "Activando…", comingSoon: "Próximamente" },
    badge: { popular: "Más popular", new: "Nuevo" },
    how: { kicker: "Cómo funciona", title: "Listo en tres pasos", sub: "Sin agencias ni proyectos de configuración. Conecta tus cuentas y ZeroManual hace el resto.", s1t: "Elige tus automatizaciones", s1b: "Elige del menú de arriba. Combínalas — todas con un precio mensual fijo.", s2t: "Conecta tus cuentas", s2b: "Vincula Google, Instagram o tu correo en un par de toques. Nunca publicamos sin tus reglas.", s3t: "Funciona 24/7", s3b: "ZeroManual trabaja sin parar y te informa. Ajusta o cancela cuando quieras." },
    band: { sub: "Sin contratos. Sin costes de instalación. Cancela cuando quieras desde tu panel.", cta: "Empezar gratis →" },
    footer: "Pequeñas automatizaciones, gran IA. © 2026 ZeroManual.",
    example: { kicker: "Demo en vivo", title: "Míralo funcionar, en vivo", sub: "Entra una tarea. ZeroManual la resuelve con tu tono. Tú no haces nada. Desliza para ver más." },
    integrations: { title: "Se conecta con las herramientas que ya usas" },
    faq: { kicker: "Ayuda", title: "Preguntas frecuentes", sub: "Todo lo que necesitas saber antes de empezar.", items: [
      { q: "¿ZeroManual publica sin mi permiso?", a: "No. Tú defines las reglas y puedes revisar o aprobar antes de publicar. Las reseñas negativas siempre se marcan para que respondas tú." },
      { q: "¿Es seguro conectar mis cuentas?", a: "Sí. Usamos conexiones oficiales y cifradas, y nunca accedemos a más de lo necesario ni compartimos tus datos." },
      { q: "¿Puedo cancelar cuando quiera?", a: "Cuando quieras, desde tu panel. Sin contratos ni penalizaciones." },
      { q: "¿Funciona en español?", a: "Sí. Responde y publica en español, inglés y más idiomas — siempre con el tono de tu negocio." },
      { q: "¿Necesito conocimientos técnicos?", a: "Ninguno. Conectas tus cuentas en unos toques y ZeroManual hace el resto." },
      { q: "¿Cuánto cuesta?", a: "Precio mensual fijo por automatización, desde 19 $/mes. Combínalas como quieras y cancela cuando quieras." },
    ] },
    drawer: { checkout: "Pago", cart: "Tus automatizaciones" },
    checkout: { start: "Crear cuenta y empezar prueba gratis", disclaimer: "No se te cobrará hasta que acabe la prueba. Cancela cuando quieras." },
    cart: { remove: "Quitar", total: "Total", checkout: "Pagar →", emptyTitle: "Tu carrito está vacío.", emptySub: "Elige una automatización para empezar." },
    detail: { what: "Qué hace", connects: "Se conecta con", subscribe: "Suscribirse", inCart: "En el carrito — ver", example: "Míralo en acción", auto: "Automático", setup: "Configuración", setupVal: "~5 minutos", langsK: "Idiomas", langsV: "Español · Inglés", trialK: "Prueba gratis" },
    per: { mo: "/mes", yr: "/año" },
    bandTitle: (n) => "Cada automatización incluye " + n + " días de prueba gratis.",
    checkoutTrial: (n) => n + " días de prueba gratis",
    countLabel: (n) => n + (n === 1 ? " automatización" : " automatizaciones"),
    talkToUs: { note: "¿Prefieres que lo montemos nosotros, a medida?", link: "Hablemos", email: "hola@zeroman.co" },
    login: {
      title: "Área privada", sub: "Accede con tu usuario o email.",
      registerTitle: "Crear cuenta", registerSub: "Regístrate como cliente.",
      identLabel: "Usuario o email", nameLabel: "Nombre", passLabel: "Contraseña",
      submit: "Entrar →", submitting: "Entrando…", registerSubmit: "Crear cuenta →", registering: "Creando…",
      error: "Usuario o contraseña incorrectos.", registerError: "No se pudo crear la cuenta.", passMin: "Mínimo 8 caracteres.",
      switchToRegister: "¿Sin cuenta? Regístrate", switchToLogin: "¿Ya tienes cuenta? Acceder",
    },
    subscribe: {
      sub: "Crea tu cuenta o accede — se activa al instante, justo después de esto.",
      cta: "Suscribirme y continuar →", ctaLogin: "Entrar y continuar →",
      connecting: "Conectando Google…", activating: "Activando…",
      error: "No se pudo completar la suscripción. Inténtalo de nuevo.",
    },
  },
};

const PRODUCTS = [
  { id: "reviews", cat: "reviews", price: 29, badge: "popular",
    en: { name: "Reply to Google Reviews", catLabel: "Reviews", connect: "Google Business Profile", tagline: "On-brand replies to every review, drafted and posted in your voice.", features: ["Replies within minutes, 24/7", "Matches your tone and business", "Flags angry reviews for you"], about: "Every time a customer leaves a review, ZeroManual writes a thoughtful, on-brand reply and posts it for you — usually within minutes. Negative reviews are flagged so you can step in, while the rest are handled automatically.", exInLabel: "Review received · ★★★★★", exIn: "“Best experience ever, the team is amazing. I’ll definitely be back!” — María G.", exOutLabel: "Reply posted", exOut: "Thank you, María! We’re so glad you enjoyed your visit. See you again soon." },
    es: { name: "Responder reseñas de Google", catLabel: "Reseñas", connect: "Perfil de Empresa de Google", tagline: "Respuestas con tu tono para cada reseña, redactadas y publicadas por ti.", features: ["Responde en minutos, 24/7", "Se adapta a tu tono y tu negocio", "Te avisa de las reseñas negativas"], about: "Cada vez que un cliente deja una reseña, ZeroManual redacta una respuesta cuidada y con tu tono, y la publica por ti — normalmente en minutos. Las reseñas negativas se marcan para que intervengas, y el resto se gestionan automáticamente.", exInLabel: "Reseña recibida · ★★★★★", exIn: "«La mejor experiencia, el equipo es increíble. ¡Volveré seguro!» — María G.", exOutLabel: "Respuesta publicada", exOut: "¡Gracias, María! Nos alegra mucho que disfrutaras tu visita. Te esperamos pronto." } },
  { id: "reels", cat: "social", price: 39, badge: "",
    en: { name: "Post Social Reels", catLabel: "Social", connect: "Instagram & TikTok", tagline: "Turn your photos and clips into scheduled reels for Instagram and TikTok.", features: ["Auto-edits clips to trending formats", "Writes captions and hashtags", "Posts on your schedule"], about: "Drop in your photos and clips and ZeroManual edits them into short-form reels with trending cuts, captions, and hashtags, then posts them on the schedule you choose.", exInLabel: "New content", exIn: "3 photos and 2 clips from Sunday brunch, straight from your gallery", exOutLabel: "Reel posted", exOut: "20-second reel with trending cuts + “Sunday brunch at La Lupita 🍳” #brunch #LaLupita" },
    es: { name: "Publicar reels en redes", catLabel: "Redes", connect: "Instagram y TikTok", tagline: "Convierte tus fotos y clips en reels programados para Instagram y TikTok.", features: ["Edita clips a formatos de tendencia", "Escribe descripciones y hashtags", "Publica según tu calendario"], about: "Sube tus fotos y clips y ZeroManual los edita en reels cortos con cortes de tendencia, descripciones y hashtags, y los publica en el calendario que elijas.", exInLabel: "Contenido nuevo", exIn: "3 fotos y 2 clips del brunch del domingo, directos de tu galería", exOutLabel: "Reel publicado", exOut: "Reel de 20 s con cortes de tendencia + «Domingo de brunch en La Lupita 🍳» #brunch #LaLupita" } },
  { id: "newsletter", cat: "email", price: 24, badge: "",
    en: { name: "Send Newsletters", catLabel: "Email", connect: "Mailchimp or Gmail", tagline: "Recurring email newsletters written from what is new at your business.", features: ["Drafts from your updates and offers", "Branded, mobile-ready emails", "Sends weekly or monthly"], about: "ZeroManual turns your latest offers, events, and updates into a clean, branded newsletter and sends it to your list on a weekly or monthly cadence — no writing required.", exInLabel: "What’s new", exIn: "Summer menu launch and new opening hours", exOutLabel: "Newsletter sent", exOut: "Subject: “The summer menu is here 🌞” — sent to 1,240 subscribers" },
    es: { name: "Enviar newsletters", catLabel: "Correo", connect: "Mailchimp o Gmail", tagline: "Boletines por correo creados a partir de las novedades de tu negocio.", features: ["Redacta desde tus novedades y ofertas", "Correos con tu marca, listos para móvil", "Envía cada semana o cada mes"], about: "ZeroManual convierte tus últimas ofertas, eventos y novedades en un boletín limpio y con tu marca, y lo envía a tu lista cada semana o cada mes — sin escribir nada.", exInLabel: "Novedades", exIn: "Lanzamiento del menú de verano y nuevo horario", exOutLabel: "Newsletter enviada", exOut: "Asunto: «Ya está aquí el menú de verano 🌞» — enviada a 1.240 suscriptores" } },
  { id: "dms", cat: "messaging", price: 34, badge: "",
    en: { name: "Reply to DMs & Comments", catLabel: "Messaging", connect: "Instagram & Facebook", tagline: "Answers Instagram and Facebook messages and comments instantly.", features: ["Answers FAQs, hours and pricing", "Books and routes real leads", "Hands off to you when it matters"], about: "ZeroManual replies to your Instagram and Facebook messages and comments instantly — answering common questions, sharing hours and pricing, and routing real leads straight to you.", exInLabel: "Instagram DM", exIn: "“Do you have a table for 4 this Saturday at 9pm?”", exOutLabel: "Reply sent", exOut: "Hi! Yes, we have a table for Saturday at 9pm. Want me to book it for you? Confirm here 👉" },
    es: { name: "Responder DMs y comentarios", catLabel: "Mensajes", connect: "Instagram y Facebook", tagline: "Responde al instante los mensajes y comentarios de Instagram y Facebook.", features: ["Responde dudas, horarios y precios", "Capta y dirige clientes reales", "Te lo pasa cuando hace falta"], about: "ZeroManual responde al instante tus mensajes y comentarios de Instagram y Facebook — resuelve dudas habituales, comparte horarios y precios, y te dirige los clientes reales directamente.", exInLabel: "DM de Instagram", exIn: "«¿Tenéis mesa para 4 este sábado a las 21:00?»", exOutLabel: "Respuesta enviada", exOut: "¡Hola! Sí, nos queda mesa el sábado a las 21:00. ¿Te la reservo? Confirma aquí 👉" } },
  { id: "reminders", cat: "messaging", price: 19, badge: "",
    en: { name: "Appointment Reminders", catLabel: "Messaging", connect: "Your calendar + SMS", tagline: "Texts customers reminders so you cut no-shows automatically.", features: ["SMS and email reminders", "One-tap confirm or reschedule", "Syncs with your calendar"], about: "ZeroManual texts and emails your customers ahead of their appointment and lets them confirm or reschedule with one tap, cutting no-shows automatically.", exInLabel: "Upcoming appointment", exIn: "Ana Ruiz — cut & color, tomorrow 10:00", exOutLabel: "SMS sent", exOut: "Hi Ana 👋 a reminder of your appointment tomorrow at 10:00. Reply 1 to confirm or 2 to reschedule." },
    es: { name: "Recordatorios de citas", catLabel: "Mensajes", connect: "Tu calendario + SMS", tagline: "Envía recordatorios por SMS para reducir las ausencias automáticamente.", features: ["Recordatorios por SMS y correo", "Confirmar o reprogramar con un toque", "Se sincroniza con tu calendario"], about: "ZeroManual envía a tus clientes un recordatorio por SMS y correo antes de su cita y les permite confirmar o reprogramar con un solo toque, reduciendo las ausencias automáticamente.", exInLabel: "Cita en tu calendario", exIn: "Ana Ruiz — corte y color, mañana 10:00", exOutLabel: "SMS enviado", exOut: "Hola Ana 👋 te recordamos tu cita de mañana a las 10:00. Responde 1 para confirmar o 2 para cambiarla." } },
  { id: "requests", cat: "reviews", price: 19, badge: "new",
    en: { name: "Request Reviews", catLabel: "Reviews", connect: "Google + SMS / email", tagline: "Asks happy customers for a Google review at the perfect moment.", features: ["Times requests after a visit", "One-tap review links", "Grows your star rating"], about: "After a visit or purchase, ZeroManual sends your happy customers a one-tap link to leave a Google review at exactly the right moment — steadily growing your rating.", exInLabel: "Visit completed", exIn: "Juan P. — paid his bill 2 hours ago", exOutLabel: "SMS sent", exOut: "Thanks for coming in, Juan! Would you leave us a quick review? One tap: g.page/lalupita" },
    es: { name: "Pedir reseñas", catLabel: "Reseñas", connect: "Google + SMS / correo", tagline: "Pide una reseña en Google a tus clientes felices en el momento ideal.", features: ["Pide la reseña tras la visita", "Enlaces de reseña con un toque", "Sube tu puntuación de estrellas"], about: "Tras una visita o compra, ZeroManual envía a tus clientes felices un enlace de un toque para dejar una reseña en Google justo en el momento adecuado — subiendo tu puntuación poco a poco.", exInLabel: "Visita completada", exIn: "Juan P. — pagó su cuenta hace 2 h", exOutLabel: "SMS enviado", exOut: "¡Gracias por tu visita, Juan! ¿Nos dejas una reseña? Solo un toque: g.page/lalupita" } },
];

const INTEGRATIONS = [{ name: "Google", abbr: "G" }, { name: "Instagram", abbr: "IG" }, { name: "TikTok", abbr: "TT" }, { name: "Facebook", abbr: "f" }, { name: "Mailchimp", abbr: "M" }, { name: "Gmail", abbr: "@" }];

const TRIAL_DAYS = 14;

function Ico({ paths, size = 24, fill = "none", strokeWidth = 1.7, ...rest }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke={fill === "none" ? "currentColor" : undefined} strokeWidth={fill === "none" ? strokeWidth : undefined} strokeLinecap="round" strokeLinejoin="round" {...rest}>
      {paths.map((p, i) => (typeof p === "string" ? <path key={i} d={p} /> : React.createElement(p.t, { key: i, ...p.a })))}
    </svg>
  );
}

const ICON_PATHS = {
  reviews: ["M12 3.2l2.5 5.2 5.7.8-4.1 4 1 5.7-5.1-2.7-5.1 2.7 1-5.7-4.1-4 5.7-.8z"],
  reels: [{ t: "rect", a: { x: 3, y: 3, width: 18, height: 18, rx: 4 } }, "M10 8.5l5 3.5-5 3.5z"],
  newsletter: [{ t: "rect", a: { x: 3, y: 5, width: 18, height: 14, rx: 2 } }, "M3.6 6.6l8.4 5.9 8.4-5.9"],
  dms: ["M4 5h16v10H8l-4 4z", "M8 9h8", "M8 12h5"],
  reminders: ["M6 9a6 6 0 1112 0c0 4 1.4 5.5 2 6H4c.6-.5 2-2 2-6z", "M10 20a2 2 0 004 0"],
  requests: ["M7 10.5V20H4v-9.5z", "M7 10.5l3.4-6.4c1.3 0 2 .8 2 1.8V9h4.8c1.1 0 1.9 1 1.6 2l-1.5 6c-.2.9-.9 1.4-1.7 1.4H7"],
};

function ProductIcon({ id, size = 24 }) {
  const paths = ICON_PATHS[id] || [];
  if (id === "reviews") return <Ico paths={paths} size={size} fill="currentColor" />;
  return <Ico paths={paths} size={size} />;
}

function fmtPrice(n) { return "$" + n; }

function LoginModal({ tt, onClose, initialMode = "login", stayOnPage = false, onLoginSuccess }) {
  const [mode, setMode] = useState(initialMode);
  const [identifier, setIdentifier] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const tl = tt.login;

  const switchMode = (m) => { setMode(m); setError(""); };

  const doLogin = async () => {
    if (!identifier || !password) return;
    setLoading(true); setError("");
    try {
      const adminRes = await fetch("/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: identifier, password }),
      });
      if (adminRes.ok) {
        const d = await adminRes.json();
        sessionStorage.setItem("mz_token", d.token);
        window.location.href = "/admin";
        return;
      }
      const clientRes = await fetch("/client/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: identifier, password }),
      });
      if (clientRes.ok) {
        const d = await clientRes.json();
        localStorage.setItem("mz_client_token", d.token);
        if (stayOnPage) { onLoginSuccess && onLoginSuccess(); return; }
        window.location.href = "/client";
        return;
      }
      setError(tl.error);
    } catch { setError(tl.error); }
    finally { setLoading(false); }
  };

  const doRegister = async () => {
    if (!name || !identifier || !password) return;
    if (password.length < 8) { setError(tl.passMin); return; }
    setLoading(true); setError("");
    try {
      const r = await fetch("/client/register", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email: identifier, password }),
      });
      if (!r.ok) {
        const d = await r.json();
        setError(d.detail || tl.registerError);
        return;
      }
      const loginRes = await fetch("/client/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: identifier, password }),
      });
      if (loginRes.ok) {
        const d = await loginRes.json();
        localStorage.setItem("mz_client_token", d.token);
        if (stayOnPage) { onLoginSuccess && onLoginSuccess(); }
        else window.location.href = "/client";
      } else { setError(tl.error); }
    } catch { setError(tl.registerError); }
    finally { setLoading(false); }
  };

  const onKey = (e) => { if (e.key === "Enter") mode === "login" ? doLogin() : doRegister(); };
  const isLogin = mode === "login";

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(14,17,22,.42)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 900 }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ background: "#fff", border: "1px solid #E6E9EE", borderRadius: 16, padding: "32px 28px", width: 320, boxShadow: "0 30px 80px rgba(14,17,22,.3)", position: "relative" }}>
        <button onClick={onClose} aria-label="Cerrar" style={{ position: "absolute", top: 12, right: 14, background: "none", border: "none", fontSize: 18, cursor: "pointer", color: "#9099A6", lineHeight: 1 }}>×</button>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 18 }}>
          <span style={{ width: 20, height: 20, borderRadius: "50%", background: "#4F46E5", display: "inline-block" }}></span>
          <span style={{ fontWeight: 700, fontSize: 15, fontFamily: "'Space Grotesk',sans-serif" }}>ZeroManual</span>
        </div>
        <div style={{ fontWeight: 600, fontSize: 17, marginBottom: 4 }}>{isLogin ? tl.title : tl.registerTitle}</div>
        <div style={{ color: "#6B7280", fontSize: 13, marginBottom: 20 }}>{isLogin ? tl.sub : tl.registerSub}</div>
        {!isLogin && (
          <>
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#3A4150", marginBottom: 5 }}>{tl.nameLabel}</label>
            <input className="zm2-input" style={{ width: "100%", padding: "9px 11px", background: "#F8F9FB", border: "1px solid #E1E5EB", borderRadius: 8, font: "inherit", fontSize: 14, outline: "none", marginBottom: 12, boxSizing: "border-box" }}
              type="text" autoComplete="name" autoFocus={!isLogin} value={name} onChange={(e) => setName(e.target.value)} onKeyDown={onKey} />
          </>
        )}
        <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#3A4150", marginBottom: 5 }}>{tl.identLabel}</label>
        <input className="zm2-input" style={{ width: "100%", padding: "9px 11px", background: "#F8F9FB", border: "1px solid #E1E5EB", borderRadius: 8, font: "inherit", fontSize: 14, outline: "none", marginBottom: 12, boxSizing: "border-box" }}
          type="text" autoComplete={isLogin ? "username" : "email"} autoFocus={isLogin} value={identifier} onChange={(e) => setIdentifier(e.target.value)} onKeyDown={onKey} />
        <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#3A4150", marginBottom: 5 }}>{tl.passLabel}</label>
        <input className="zm2-input" style={{ width: "100%", padding: "9px 11px", background: "#F8F9FB", border: "1px solid #E1E5EB", borderRadius: 8, font: "inherit", fontSize: 14, outline: "none", marginBottom: error ? 8 : 14, boxSizing: "border-box" }}
          type="password" autoComplete={isLogin ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={onKey} />
        {error && <div style={{ color: "#E5484D", fontSize: 12, marginBottom: 10, minHeight: 16 }}>{error}</div>}
        <button className="zm2-pill-primary" disabled={loading} onClick={isLogin ? doLogin : doRegister}
          style={{ width: "100%", padding: 10, background: "#4F46E5", color: "#fff", border: "none", borderRadius: 8, font: "inherit", fontSize: 14, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.6 : 1, marginBottom: 14 }}>
          {loading ? (isLogin ? tl.submitting : tl.registering) : (isLogin ? tl.submit : tl.registerSubmit)}
        </button>
        <button onClick={() => switchMode(isLogin ? "register" : "login")} style={{ display: "block", width: "100%", textAlign: "center", fontSize: 12, color: "#9099A6", cursor: "pointer", textDecoration: "underline", background: "none", border: "none", font: "inherit" }}>
          {isLogin ? tl.switchToRegister : tl.switchToLogin}
        </button>
      </div>
    </div>
  );
}

function SubscribeModal({ product, lang, t, onClose, onDone }) {
  const [mode, setMode] = useState("register");
  const [identifier, setIdentifier] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [phase, setPhase] = useState("form"); // form | connecting | activating
  const tl = t.login;
  const ts = t.subscribe;
  const automationType = AUTOMATION_TYPE_MAP[product.id];
  const loc = product[lang];
  const busy = phase !== "form";

  const switchMode = (m) => { if (!busy) { setMode(m); setError(""); } };

  const afterAuth = async (token) => {
    localStorage.setItem("mz_client_token", token);
    try {
      const statusRes = await fetch("/client/google/status", { headers: { Authorization: "Bearer " + token } });
      const status = statusRes.ok ? await statusRes.json() : { connected: false };
      if (status.connected) {
        setPhase("activating");
        const actRes = await fetch(`/client/automations/${automationType}/activate`, {
          method: "POST", headers: { Authorization: "Bearer " + token },
        });
        if (!actRes.ok) throw new Error("activate failed");
        onDone({ activatedId: product.id });
        return;
      }
      setPhase("connecting");
      await fetch("/client/pending-automation", {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify({ automation_type: automationType }),
      });
      const connRes = await fetch("/client/google/connect", { headers: { Authorization: "Bearer " + token } });
      if (!connRes.ok) throw new Error("connect failed");
      const conn = await connRes.json();
      window.location.href = conn.redirect_url;
    } catch {
      setError(ts.error);
      setPhase("form");
    }
  };

  const doLogin = async () => {
    if (!identifier || !password || busy) return;
    setError("");
    try {
      const r = await fetch("/client/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: identifier, password }),
      });
      if (!r.ok) { setError(tl.error); return; }
      const d = await r.json();
      await afterAuth(d.token);
    } catch { setError(tl.error); }
  };

  const doRegister = async () => {
    if (!name || !identifier || !password || busy) return;
    if (password.length < 8) { setError(tl.passMin); return; }
    setError("");
    try {
      const r = await fetch("/client/register", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email: identifier, password }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setError(d.detail || tl.registerError);
        return;
      }
      const d = await r.json();
      await afterAuth(d.token);
    } catch { setError(tl.registerError); }
  };

  const onKey = (e) => { if (e.key === "Enter") (mode === "login" ? doLogin() : doRegister()); };
  const isLogin = mode === "login";

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(14,17,22,.42)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 900 }} onClick={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div style={{ background: "#fff", border: "1px solid #E6E9EE", borderRadius: 16, padding: "32px 28px", width: 340, boxShadow: "0 30px 80px rgba(14,17,22,.3)", position: "relative" }}>
        {!busy && (
          <button onClick={onClose} aria-label="Cerrar" style={{ position: "absolute", top: 12, right: 14, background: "none", border: "none", fontSize: 18, cursor: "pointer", color: "#9099A6", lineHeight: 1 }}>×</button>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <span style={{ width: 40, height: 40, borderRadius: 11, background: "#EEF0FE", color: "#4F46E5", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <ProductIcon id={product.id} />
          </span>
          <div>
            <div style={{ fontWeight: 600, fontSize: 15 }}>{loc.name}</div>
            <div style={{ color: "#6B7280", fontSize: 12.5 }}>{ts.sub}</div>
          </div>
        </div>
        {busy ? (
          <div style={{ padding: "20px 0", textAlign: "center", color: "#3A4150", fontSize: 14 }}>
            {phase === "activating" ? ts.activating : ts.connecting}
          </div>
        ) : (
          <>
            {!isLogin && (
              <>
                <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#3A4150", marginBottom: 5 }}>{tl.nameLabel}</label>
                <input className="zm2-input" style={{ width: "100%", padding: "9px 11px", background: "#F8F9FB", border: "1px solid #E1E5EB", borderRadius: 8, font: "inherit", fontSize: 14, outline: "none", marginBottom: 12, boxSizing: "border-box" }}
                  type="text" autoComplete="name" autoFocus={!isLogin} value={name} onChange={(e) => setName(e.target.value)} onKeyDown={onKey} />
              </>
            )}
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#3A4150", marginBottom: 5 }}>{tl.identLabel}</label>
            <input className="zm2-input" style={{ width: "100%", padding: "9px 11px", background: "#F8F9FB", border: "1px solid #E1E5EB", borderRadius: 8, font: "inherit", fontSize: 14, outline: "none", marginBottom: 12, boxSizing: "border-box" }}
              type="text" autoComplete={isLogin ? "username" : "email"} autoFocus={isLogin} value={identifier} onChange={(e) => setIdentifier(e.target.value)} onKeyDown={onKey} />
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#3A4150", marginBottom: 5 }}>{tl.passLabel}</label>
            <input className="zm2-input" style={{ width: "100%", padding: "9px 11px", background: "#F8F9FB", border: "1px solid #E1E5EB", borderRadius: 8, font: "inherit", fontSize: 14, outline: "none", marginBottom: error ? 8 : 14, boxSizing: "border-box" }}
              type="password" autoComplete={isLogin ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={onKey} />
            {error && <div style={{ color: "#E5484D", fontSize: 12, marginBottom: 10, minHeight: 16 }}>{error}</div>}
            <button className="zm2-pill-primary" disabled={busy} onClick={isLogin ? doLogin : doRegister}
              style={{ width: "100%", padding: 10, background: "#4F46E5", color: "#fff", border: "none", borderRadius: 8, font: "inherit", fontSize: 14, fontWeight: 600, cursor: "pointer", marginBottom: 14 }}>
              {isLogin ? ts.ctaLogin : ts.cta}
            </button>
            <button onClick={() => switchMode(isLogin ? "register" : "login")} style={{ display: "block", width: "100%", textAlign: "center", fontSize: 12, color: "#9099A6", cursor: "pointer", textDecoration: "underline", background: "none", border: "none", font: "inherit" }}>
              {isLogin ? tl.switchToRegister : tl.switchToLogin}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function ProductCard({ product, lang, t, inCart, annual, active, subscribing, onToggleCart, onDetail }) {
  const loc = product[lang];
  const price = annual ? product.price * 10 : product.price;
  const comingSoon = product.id !== "reviews";
  return (
    <article className="zm2-card" style={{ background: "#fff", border: "1px solid #E6E9EE", borderRadius: 16, padding: 22, display: "flex", flexDirection: "column", gap: 15, ...(comingSoon ? { opacity: 0.6, filter: "grayscale(.35)" } : {}) }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <span style={{ width: 46, height: 46, borderRadius: 13, background: "#EEF0FE", color: "#4F46E5", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <ProductIcon id={product.id} />
        </span>
        {comingSoon ? (
          <span style={{ fontSize: 12, fontWeight: 600, padding: "5px 11px", borderRadius: 999, whiteSpace: "nowrap", background: "#F1F3F6", color: "#6B7280" }}>
            {t.card.comingSoon}
          </span>
        ) : product.badge && (
          <span style={{ fontSize: 12, fontWeight: 600, padding: "5px 11px", borderRadius: 999, whiteSpace: "nowrap", background: product.badge === "new" ? "#E7F6EF" : "#EEF0FE", color: product.badge === "new" ? "#047857" : "#4F46E5" }}>
            {t.badge[product.badge]}
          </span>
        )}
      </div>
      <div>
        <h3 style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, fontSize: 19, letterSpacing: "-.01em", margin: 0 }}>{loc.name}</h3>
        <p style={{ margin: "7px 0 0", color: "#5B6472", fontSize: 14, lineHeight: 1.5 }}>{loc.tagline}</p>
      </div>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
        {loc.features.map((f) => (
          <li key={f} style={{ display: "flex", alignItems: "flex-start", gap: 9, fontSize: 13.5, color: "#3A4150" }}>
            <span style={{ color: "#10B981", fontWeight: 700, flexShrink: 0, lineHeight: 1.4 }}>✓</span><span>{f}</span>
          </li>
        ))}
      </ul>
      <div style={{ borderTop: "1px solid #EDEFF3", marginTop: 2, paddingTop: 15, display: "flex", alignItems: "baseline", gap: 6 }}>
        <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: 26, letterSpacing: "-.02em" }}>{fmtPrice(price)}</span>
        <span style={{ color: "#6B7280", fontSize: 14 }}>{annual ? t.per.yr : t.per.mo}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        <button className="zm2-pill-primary" disabled={comingSoon || active || subscribing} onClick={() => onToggleCart(product.id)}
          style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, width: "100%", padding: "11px 14px", borderRadius: 10, fontSize: 14.5, fontWeight: 600, cursor: comingSoon || active || subscribing ? "default" : "pointer", border: "1px solid", ...(comingSoon ? { background: "#F1F3F6", color: "#9099A6", borderColor: "#E6E9EE" } : active || inCart ? { background: "#E7F6EF", color: "#047857", borderColor: "#BCE7D1" } : { background: "#4F46E5", color: "#fff", borderColor: "#4F46E5" }) }}>
          {comingSoon ? t.card.comingSoon : active ? t.card.active : subscribing ? t.card.activating : inCart ? "✓ " + t.card.added : t.card.subscribe}
        </button>
        <button className="zm2-link-muted" onClick={() => onDetail(product.id)} style={{ background: "transparent", border: "none", color: "#6B7280", fontSize: 13.5, fontWeight: 500, cursor: "pointer", padding: 2 }}>
          {t.card.details}
        </button>
      </div>
    </article>
  );
}

function CartDrawer({ open, onClose, cartIds, lang, t, annual, onRemove, onCheckout }) {
  if (!open) return null;
  const items = cartIds.map((id) => PRODUCTS.find((p) => p.id === id)).filter(Boolean);
  const per = annual ? t.per.yr : t.per.mo;
  const total = items.reduce((s, p) => s + (annual ? p.price * 10 : p.price), 0);
  return (
    <>
      <div style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(14,17,22,.42)", backdropFilter: "blur(2px)", animation: "zmFade .2s ease" }} onClick={onClose} />
      <aside style={{ position: "fixed", top: 0, right: 0, bottom: 0, zIndex: 61, width: "min(430px,100%)", background: "#fff", boxShadow: "-16px 0 50px rgba(14,17,22,.18)", animation: "zmSlide .26s cubic-bezier(.22,.8,.3,1)", display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "20px 22px", borderBottom: "1px solid #EDEFF3" }}>
          <h3 style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, fontSize: 18, margin: 0 }}>{t.drawer.cart}</h3>
          <button className="zm2-iconbtn-sq" onClick={onClose} style={{ background: "#F1F3F6", border: "none", width: 34, height: 34, borderRadius: 9, color: "#3A4150", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Ico paths={["M6 6l12 12", "M6 18L18 6"]} size={18} />
          </button>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: "18px 22px" }}>
          {items.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
              {items.map((p) => (
                <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 12, border: "1px solid #EDEFF3", borderRadius: 13, padding: 13 }}>
                  <span style={{ width: 42, height: 42, borderRadius: 11, background: "#EEF0FE", color: "#4F46E5", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <ProductIcon id={p.id} />
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14.5, fontWeight: 600 }}>{p[lang].name}</div>
                    <div style={{ fontSize: 13, color: "#6B7280", marginTop: 2 }}>{fmtPrice(annual ? p.price * 10 : p.price)}{per}</div>
                  </div>
                  <button className="zm2-remove" onClick={() => onRemove(p.id)} style={{ background: "transparent", border: "none", color: "#9099A6", fontSize: 13, cursor: "pointer", padding: 6 }}>{t.cart.remove}</button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ textAlign: "center", padding: "46px 16px", color: "#9099A6" }}>
              <span style={{ display: "inline-flex", color: "#CBD2DC" }}>
                <Ico paths={["M3.5 4h2l2.2 11.2a1 1 0 001 .8h8.5a1 1 0 001-.79L20.5 7H6", { t: "circle", a: { cx: 9, cy: 20, r: 1.4 } }, { t: "circle", a: { cx: 18, cy: 20, r: 1.4 } }]} size={40} />
              </span>
              <p style={{ margin: "14px 0 0", fontSize: 14.5 }}>{t.cart.emptyTitle}<br />{t.cart.emptySub}</p>
            </div>
          )}
        </div>
        {items.length > 0 && (
          <div style={{ borderTop: "1px solid #EDEFF3", padding: "18px 22px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 14 }}>
              <span style={{ fontSize: 14.5, color: "#5B6472" }}>{t.cart.total}</span>
              <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: 24 }}>{fmtPrice(total)}<span style={{ fontSize: 14, color: "#6B7280", fontWeight: 500 }}>{per}</span></span>
            </div>
            <button className="zm2-pill-primary" onClick={onCheckout} style={{ width: "100%", background: "#4F46E5", color: "#fff", border: "none", padding: 14, borderRadius: 11, fontSize: 15, fontWeight: 600, cursor: "pointer" }}>
              {t.checkout.start}
            </button>
            <p style={{ textAlign: "center", color: "#9099A6", fontSize: 12, margin: "12px 0 0" }}>{t.checkout.disclaimer}</p>
          </div>
        )}
      </aside>
    </>
  );
}

function DetailModal({ id, lang, t, inCart, annual, onClose, onSubscribe }) {
  if (!id) return null;
  const product = PRODUCTS.find((p) => p.id === id);
  if (!product) return null;
  const loc = product[lang];
  const price = annual ? product.price * 10 : product.price;
  const per = annual ? t.per.yr : t.per.mo;
  const comingSoon = product.id !== "reviews";
  const facts = [
    { k: t.detail.setup, v: t.detail.setupVal },
    { k: t.detail.connects, v: loc.connect },
    { k: t.detail.langsK, v: t.detail.langsV },
    { k: t.detail.trialK, v: TRIAL_DAYS + (lang === "es" ? " días" : " days") },
  ];
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 70, background: "rgba(14,17,22,.5)", backdropFilter: "blur(3px)", animation: "zmFade .2s ease", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 22, width: "100%", maxWidth: 560, maxHeight: "88vh", overflowY: "auto", animation: "zmPop .26s cubic-bezier(.22,.8,.3,1)", boxShadow: "0 30px 80px rgba(14,17,22,.3)" }}>
        <div style={{ padding: "26px 26px 0", display: "flex", alignItems: "flex-start", gap: 16 }}>
          <span style={{ width: 54, height: 54, borderRadius: 15, background: "#EEF0FE", color: "#4F46E5", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <ProductIcon id={product.id} />
          </span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "#4F46E5", textTransform: "uppercase", letterSpacing: ".06em" }}>{loc.catLabel}</div>
            <h3 style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: 23, letterSpacing: "-.02em", margin: "5px 0 0" }}>{loc.name}</h3>
          </div>
          <button className="zm2-iconbtn-sq" onClick={onClose} style={{ background: "#F1F3F6", border: "none", width: 34, height: 34, borderRadius: 9, color: "#3A4150", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <Ico paths={["M6 6l12 12", "M6 18L18 6"]} size={18} />
          </button>
        </div>
        <div style={{ padding: "18px 26px 0" }}>
          <p style={{ color: "#3A4150", fontSize: 15, lineHeight: 1.6, margin: 0 }}>{loc.about}</p>
          <div style={{ marginTop: 20, fontSize: 12.5, fontWeight: 600, color: "#6B7280", textTransform: "uppercase", letterSpacing: ".05em" }}>{t.detail.example}</div>
          <div style={{ marginTop: 12, background: "#F8F9FB", border: "1px solid #EDEFF3", borderRadius: 14, padding: 13, display: "flex", flexDirection: "column", gap: 9 }}>
            <div style={{ background: "#fff", border: "1px solid #E6E9EE", borderRadius: 11, padding: "11px 13px" }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#9099A6", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 5 }}>{loc.exInLabel}</div>
              <div style={{ fontSize: 13.5, color: "#1E2430", lineHeight: 1.5 }}>{loc.exIn}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 2px" }}>
              <span style={{ width: 16, height: 16, border: "1.5px solid #4F46E5", borderRadius: "50%", display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "#4F46E5" }}></span></span>
              <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: 12, fontWeight: 600, color: "#4F46E5" }}>ZeroManual</span>
              <Ico paths={["M12 4v16", "M6 14l6 6 6-6"]} size={13} strokeWidth={2} stroke="#9099A6" />
            </div>
            <div style={{ background: "#EEF0FE", border: "1px solid #DDE1FC", borderRadius: 11, padding: "11px 13px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 5 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#4F46E5", textTransform: "uppercase", letterSpacing: ".05em" }}>{loc.exOutLabel}</span>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#047857", background: "#E7F6EF", padding: "2px 8px", borderRadius: 999, whiteSpace: "nowrap" }}>{t.detail.auto}</span>
              </div>
              <div style={{ fontSize: 13.5, color: "#1E2430", lineHeight: 1.5 }}>{loc.exOut}</div>
            </div>
          </div>
          <div style={{ marginTop: 20, fontSize: 12.5, fontWeight: 600, color: "#6B7280", textTransform: "uppercase", letterSpacing: ".05em" }}>{t.detail.what}</div>
          <ul style={{ listStyle: "none", margin: "12px 0 0", padding: 0, display: "flex", flexDirection: "column", gap: 11 }}>
            {loc.features.map((f) => (
              <li key={f} style={{ display: "flex", alignItems: "flex-start", gap: 10, fontSize: 14.5, color: "#1E2430" }}>
                <span style={{ color: "#10B981", fontWeight: 700, flexShrink: 0 }}>✓</span><span>{f}</span>
              </li>
            ))}
          </ul>
          <div style={{ marginTop: 18, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {facts.map((fa) => (
              <div key={fa.k} style={{ background: "#F8F9FB", border: "1px solid #EDEFF3", borderRadius: 11, padding: "11px 13px" }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "#9099A6", textTransform: "uppercase", letterSpacing: ".05em" }}>{fa.k}</div>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: "#1E2430", marginTop: 3 }}>{fa.v}</div>
              </div>
            ))}
          </div>
        </div>
        <div style={{ position: "sticky", bottom: 0, background: "#fff", borderTop: "1px solid #EDEFF3", marginTop: 22, padding: "18px 26px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
            <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: 26, letterSpacing: "-.02em" }}>{fmtPrice(price)}</span>
            <span style={{ color: "#6B7280", fontSize: 14 }}>{per}</span>
          </div>
          <button className="zm2-pill-primary" disabled={comingSoon} onClick={() => onSubscribe(product.id)} style={{ border: "none", padding: "13px 22px", borderRadius: 11, fontSize: 15, fontWeight: 600, cursor: comingSoon ? "default" : "pointer", ...(comingSoon ? { background: "#F1F3F6", color: "#9099A6" } : { background: "#4F46E5", color: "#fff" }) }}>
            {comingSoon ? t.card.comingSoon : inCart ? t.detail.inCart : t.detail.subscribe}
          </button>
        </div>
      </div>
    </div>
  );
}

function App() {
  const [lang, setLang] = useState("es");
  const [cart, setCart] = useState([]);
  const [filter, setFilter] = useState("all");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detailId, setDetailId] = useState(null);
  const [annual, setAnnual] = useState(false);
  const [faqOpen, setFaqOpen] = useState(0);
  const [showLogin, setShowLogin] = useState(false);
  const [loginInitialMode, setLoginInitialMode] = useState("login");
  const [loginStayOnPage, setLoginStayOnPage] = useState(false);
  const [clientToken, setClientToken] = useState(() => { try { return localStorage.getItem("mz_client_token"); } catch { return null; } });
  const [clientName, setClientName] = useState("");
  const [googleConnected, setGoogleConnected] = useState(false);
  const [activeAutomations, setActiveAutomations] = useState([]);
  const [subscribingId, setSubscribingId] = useState(null);
  const [subscribeModalId, setSubscribeModalId] = useState(null);

  const t = T[lang] || T.es;

  useEffect(() => {
    document.body.style.overflow = drawerOpen || detailId ? "hidden" : "";
  }, [drawerOpen, detailId]);

  // Returning logged-in visitor: learn which automations are already active
  // and whether Google is connected, so the grid can show "Activa" state and
  // offer the 1-click path without a modal or redirect.
  useEffect(() => {
    if (!clientToken) { setGoogleConnected(false); setActiveAutomations([]); setClientName(""); return; }
    let cancelled = false;
    (async () => {
      try {
        const meRes = await fetch("/client/me", { headers: { Authorization: "Bearer " + clientToken } });
        if (!meRes.ok) throw new Error("unauthorized");
        const meData = await meRes.json();
        if (!cancelled) setClientName(meData?.client?.name || "");
        const [autoRes, statusRes] = await Promise.all([
          fetch("/client/automations", { headers: { Authorization: "Bearer " + clientToken } }),
          fetch("/client/google/status", { headers: { Authorization: "Bearer " + clientToken } }),
        ]);
        if (cancelled) return;
        if (autoRes.ok) {
          const d = await autoRes.json();
          setActiveAutomations((d.active || []).filter((a) => a.status === "active").map((a) => a.automation_type));
        }
        if (statusRes.ok) {
          const d = await statusRes.json();
          setGoogleConnected(!!d.connected);
        }
      } catch {
        if (!cancelled) {
          try { localStorage.removeItem("mz_client_token"); } catch {}
          setClientToken(null);
          setClientName("");
        }
      }
    })();
    return () => { cancelled = true; };
  }, [clientToken]);

  const isAutomationActive = (id) => {
    const type = AUTOMATION_TYPE_MAP[id];
    return type ? activeAutomations.includes(type) : false;
  };

  const clientInitial = (clientName || "").trim().charAt(0).toUpperCase() || "?";

  const activateDirect = async (id) => {
    const type = AUTOMATION_TYPE_MAP[id];
    setSubscribingId(id);
    try {
      const r = await fetch(`/client/automations/${type}/activate`, {
        method: "POST", headers: { Authorization: "Bearer " + clientToken },
      });
      if (r.ok) setActiveAutomations((a) => (a.includes(type) ? a : [...a, type]));
    } catch {}
    finally { setSubscribingId(null); }
  };

  const startPendingAndConnect = async (id) => {
    const type = AUTOMATION_TYPE_MAP[id];
    setSubscribingId(id);
    try {
      await fetch("/client/pending-automation", {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + clientToken },
        body: JSON.stringify({ automation_type: type }),
      });
      const r = await fetch("/client/google/connect", { headers: { Authorization: "Bearer " + clientToken } });
      const d = await r.json();
      window.location.href = d.redirect_url;
    } catch { setSubscribingId(null); }
  };

  // Dispatches "Suscribirme" clicks by session state: automations without a
  // real backend type fall back to the legacy multi-item cart; the rest take
  // the fast path (1 click if logged in + Google connected, otherwise a
  // single combined modal, per the onboarding UX brief).
  const handleCardAction = (id) => {
    const type = AUTOMATION_TYPE_MAP[id];
    if (!type) { toggleCart(id); return; }
    if (activeAutomations.includes(type)) return;
    if (!clientToken) { setSubscribeModalId(id); return; }
    if (googleConnected) { activateDirect(id); return; }
    startPendingAndConnect(id);
  };

  const onSubscribeModalDone = ({ activatedId }) => {
    const type = AUTOMATION_TYPE_MAP[activatedId];
    if (type) setActiveAutomations((a) => (a.includes(type) ? a : [...a, type]));
    setClientToken(localStorage.getItem("mz_client_token"));
    setSubscribeModalId(null);
  };

  const toggleCart = (id) => setCart((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  const removeFromCart = (id) => setCart((c) => c.filter((x) => x !== id));
  const subscribeFromDetail = (id) => {
    setCart((c) => (c.includes(id) ? c : [...c, id]));
    setDetailId(null);
    setDrawerOpen(true);
  };

  const openAccount = () => {
    if (clientToken) { window.location.href = "/client"; return; }
    setLoginInitialMode("login"); setLoginStayOnPage(true); setShowLogin(true);
  };

  const onLoginModalSuccess = () => {
    setClientToken(localStorage.getItem("mz_client_token"));
    setShowLogin(false);
  };

  // No payment backend exists yet — checkout hands the cart to the real
  // register/activate flow instead of a fake card charge. client.html reads
  // CART_HANDOFF_KEY after login and activates each recognized automation for free.
  // Defaults to login (not register) so existing clients can get straight into
  // their account; new users still reach registration via the modal's switch link.
  const handleCheckout = () => {
    const pending = cart.map((id) => AUTOMATION_TYPE_MAP[id]).filter(Boolean);
    try { localStorage.setItem(CART_HANDOFF_KEY, JSON.stringify(pending)); } catch {}
    setDrawerOpen(false);
    setLoginInitialMode("login");
    setLoginStayOnPage(false);
    setShowLogin(true);
  };

  const cards = PRODUCTS.filter((p) => filter === "all" || p.cat === filter);
  const filterDefs = [
    { key: "all", label: t.filters.all }, { key: "reviews", label: t.filters.reviews }, { key: "social", label: t.filters.social },
    { key: "email", label: t.filters.email }, { key: "messaging", label: t.filters.messaging },
  ];
  const detailProduct = detailId ? PRODUCTS.find((p) => p.id === detailId) : null;

  return (
    <div id="top" style={{ minHeight: "100vh" }}>
      <header style={{ position: "sticky", top: 0, zIndex: 40, background: "rgba(246,247,249,.82)", backdropFilter: "blur(12px)", borderBottom: "1px solid #E6E9EE" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "13px 24px", display: "flex", alignItems: "center", gap: 18 }}>
          <a href="#top" style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", color: "#0E1116" }}>
            <span style={{ width: 27, height: 27, border: "1.6px solid #0E1116", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <span style={{ width: 13, height: 13, borderRadius: "50%", background: "#4F46E5", animation: "zmPulse 2.4s ease-in-out infinite" }}></span>
            </span>
            <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, fontSize: 19, letterSpacing: "-.01em" }}>Zero<span style={{ fontWeight: 300 }}>Manual</span></span>
          </a>
          <nav className="zm-nav" style={{ display: "flex", gap: 4, marginLeft: 6 }}>
            <a href="#zm-grid" className="zm2-navlink" style={{ textDecoration: "none", color: "#3A4150", fontSize: 14.5, fontWeight: 500, padding: "7px 12px", borderRadius: 8 }}>{t.nav.automations}</a>
            <a href="#zm-how" className="zm2-navlink" style={{ textDecoration: "none", color: "#3A4150", fontSize: 14.5, fontWeight: 500, padding: "7px 12px", borderRadius: 8 }}>{t.nav.how}</a>
            <a href="#zm-grid" className="zm2-navlink" style={{ textDecoration: "none", color: "#3A4150", fontSize: 14.5, fontWeight: 500, padding: "7px 12px", borderRadius: 8 }}>{t.nav.pricing}</a>
          </nav>
          <div style={{ flex: 1 }}></div>
          <div style={{ display: "flex", alignItems: "center", gap: 2, background: "#fff", border: "1px solid #E6E9EE", borderRadius: 9, padding: 3 }}>
            <button onClick={() => setLang("es")} style={{ padding: "6px 11px", borderRadius: 6, fontSize: 13, fontWeight: 600, border: "none", cursor: "pointer", background: lang === "es" ? "#4F46E5" : "transparent", color: lang === "es" ? "#fff" : "#6B7280" }}>ES</button>
            <button onClick={() => setLang("en")} style={{ padding: "6px 11px", borderRadius: 6, fontSize: 13, fontWeight: 600, border: "none", cursor: "pointer", background: lang === "en" ? "#4F46E5" : "transparent", color: lang === "en" ? "#fff" : "#6B7280" }}>EN</button>
          </div>
          <button className="zm2-iconbtn" onClick={() => setDrawerOpen(true)} style={{ position: "relative", display: "flex", alignItems: "center", gap: 8, background: "#fff", border: "1px solid #E6E9EE", color: "#0E1116", fontSize: 14, fontWeight: 500, padding: "9px 14px", borderRadius: 10, cursor: "pointer" }}>
            <Ico paths={["M3.5 4h2l2.2 11.2a1 1 0 001 .8h8.5a1 1 0 001-.79L20.5 7H6", { t: "circle", a: { cx: 9, cy: 20, r: 1.4 } }, { t: "circle", a: { cx: 18, cy: 20, r: 1.4 } }]} size={19} />
            <span className="zm-cart-label">{t.nav.cart}</span>
            {cart.length > 0 && <span style={{ minWidth: 20, height: 20, padding: "0 5px", borderRadius: 999, background: "#4F46E5", color: "#fff", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center" }}>{cart.length}</span>}
          </button>
          {clientToken && (
            <button className="zm2-iconbtn" onClick={openAccount} style={{ display: "flex", alignItems: "center", gap: 8, background: "#fff", border: "1px solid #E6E9EE", color: "#0E1116", fontSize: 14, fontWeight: 500, padding: "9px 14px", borderRadius: 10, cursor: "pointer" }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="3.4"></circle><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6"></path></svg>
              <span className="zm-acct-label">{t.nav.account}</span>
            </button>
          )}
          {clientToken ? (
            <button onClick={openAccount} title={clientName || t.nav.account} style={{ width: 36, height: 36, borderRadius: "50%", background: "#4F46E5", color: "#fff", fontSize: 15, fontWeight: 600, border: "none", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              {clientInitial}
            </button>
          ) : (
            <button onClick={openAccount} className="zm2-cta zm2-arrowhost" style={{ background: "#4F46E5", color: "#fff", fontSize: 14.5, fontWeight: 600, padding: "10px 18px", borderRadius: 999, display: "inline-flex", alignItems: "center", gap: 6, border: "none", cursor: "pointer" }}>{t.nav.login} <span className="zm2-arrow" style={{ fontSize: 13 }}>→</span></button>
          )}
        </div>
      </header>

      <div style={{ position: "relative" }}>
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(100deg,#EDEBFC 0%,#E7E9FD 30%,#E3F0FB 58%,#E6F6F0 82%,#F6F7F9 100%)", clipPath: "polygon(0 0,100% 0,100% 62%,0 100%)" }}></div>
        <section style={{ position: "relative", maxWidth: 1040, margin: "0 auto", padding: "84px 24px 92px", textAlign: "center" }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "#fff", border: "1px solid #E6E9EE", borderRadius: 999, padding: "6px 14px", fontSize: 13, fontWeight: 500, color: "#3A4150", boxShadow: "0 2px 8px rgba(14,17,22,.05)" }}>
            <span style={{ width: 7, height: 7, borderRadius: 999, background: "#10B981", boxShadow: "0 0 0 3px rgba(16,185,129,.16)" }}></span>
            {t.hero.eyebrow}
          </div>
          <h1 style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: "clamp(38px,6vw,64px)", lineHeight: 1.05, letterSpacing: "-.035em", margin: "20px 0 0", background: "linear-gradient(95deg,#0E1116 35%,#37317F 75%,#4F46E5 100%)", WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent" }}>{t.hero.h1}</h1>
          <p style={{ fontSize: 19, color: "#3A4150", maxWidth: 620, margin: "22px auto 0", lineHeight: 1.55 }}>{t.hero.sub}</p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 30, flexWrap: "wrap" }}>
            <a href="#zm-grid" className="zm2-cta-lg zm2-arrowhost" style={{ textDecoration: "none", background: "#4F46E5", color: "#fff", fontSize: 16, fontWeight: 600, padding: "14px 26px", borderRadius: 999, display: "inline-flex", alignItems: "center", gap: 8, boxShadow: "0 8px 22px rgba(79,70,229,.28)" }}>{t.hero.browse} <span className="zm2-arrow">→</span></a>
            <a href="#zm-how" className="zm2-cta-ghost" style={{ textDecoration: "none", background: "#fff", color: "#0E1116", fontSize: 16, fontWeight: 600, padding: "14px 26px", borderRadius: 999, border: "1px solid #E6E9EE", boxShadow: "0 2px 8px rgba(14,17,22,.05)" }}>{t.hero.how}</a>
          </div>
          <div style={{ display: "flex", gap: 10, justifyContent: "center", alignItems: "center", marginTop: 34, fontSize: 13.5, color: "#6B7280", flexWrap: "wrap" }}>
            <span>{t.hero.t3}</span>
          </div>
        </section>
      </div>

      <section id="zm-grid" style={{ maxWidth: 1200, margin: "0 auto", padding: "26px 24px 18px", scrollMarginTop: 80 }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 20, flexWrap: "wrap", marginBottom: 20 }}>
          <div>
            <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", textTransform: "uppercase", color: "#4F46E5", margin: "0 0 8px" }}>{t.grid.kicker}</div>
            <h2 style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: 30, letterSpacing: "-.025em", margin: 0 }}>{t.grid.title}</h2>
            <p style={{ margin: "7px 0 0", color: "#6B7280", fontSize: 15.5 }}>{t.grid.sub}</p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ display: "inline-flex", border: "1px solid #E6E9EE", borderRadius: 999, padding: 3, background: "#fff" }}>
              <button onClick={() => setAnnual(false)} style={{ padding: "6px 13px", borderRadius: 999, fontSize: 13, fontWeight: 600, border: "none", cursor: "pointer", background: !annual ? "#4F46E5" : "transparent", color: !annual ? "#fff" : "#6B7280" }}>{t.per.mo === "/mes" ? "Mensual" : "Monthly"}</button>
              <button onClick={() => setAnnual(true)} style={{ padding: "6px 13px", borderRadius: 999, fontSize: 13, fontWeight: 600, border: "none", cursor: "pointer", background: annual ? "#4F46E5" : "transparent", color: annual ? "#fff" : "#6B7280" }}>{t.per.yr === "/año" ? "Anual" : "Annual"}</button>
            </div>
            {annual && <span style={{ background: "#E7F6EF", color: "#047857", fontSize: 12.5, fontWeight: 600, padding: "6px 12px", borderRadius: 999, whiteSpace: "nowrap" }}>{t.grid.annual}</span>}
          </div>
        </div>

        <div style={{ display: "flex", gap: 9, flexWrap: "wrap", marginBottom: 24 }}>
          {filterDefs.map((f) => (
            <button key={f.key} onClick={() => setFilter(f.key)} style={{ padding: "8px 15px", borderRadius: 999, fontSize: 13.5, fontWeight: 500, cursor: "pointer", border: "1px solid", background: filter === f.key ? "#4F46E5" : "#fff", color: filter === f.key ? "#fff" : "#3A4150", borderColor: filter === f.key ? "#4F46E5" : "#E6E9EE" }}>
              {f.label}
            </button>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(332px,1fr))", gap: 18 }}>
          {cards.map((p) => (
            <ProductCard key={p.id} product={p} lang={lang} t={t} inCart={cart.includes(p.id)} annual={annual} active={isAutomationActive(p.id)} subscribing={subscribingId === p.id} onToggleCart={handleCardAction} onDetail={setDetailId} />
          ))}
        </div>
      </section>

      <section id="zm-example" style={{ maxWidth: 1200, margin: "0 auto", padding: "64px 24px 8px", scrollMarginTop: 80 }}>
        <div style={{ textAlign: "center", marginBottom: 34 }}>
          <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", textTransform: "uppercase", color: "#4F46E5", margin: "0 0 8px" }}>{t.example.kicker}</div>
          <h2 style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: 30, letterSpacing: "-.025em", margin: 0 }}>{t.example.title}</h2>
          <p style={{ margin: "7px 0 0", color: "#6B7280", fontSize: 15.5 }}>{t.example.sub}</p>
        </div>
        <window.LiveDemoCarousel lang={lang} key={lang} />
      </section>

      <section style={{ maxWidth: 1200, margin: "0 auto", padding: "46px 24px 8px" }}>
        <p style={{ textAlign: "center", color: "#9099A6", fontSize: 13, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".08em", margin: "0 0 20px" }}>{t.integrations.title}</p>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 12 }}>
          {INTEGRATIONS.map((ig) => (
            <div key={ig.name} style={{ display: "flex", alignItems: "center", gap: 10, background: "#fff", border: "1px solid #E6E9EE", borderRadius: 12, padding: "10px 16px" }}>
              <span style={{ width: 28, height: 28, borderRadius: 8, background: "#EEF0FE", color: "#4F46E5", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontFamily: "'Space Grotesk',sans-serif", fontSize: 13 }}>{ig.abbr}</span>
              <span style={{ fontSize: 15, fontWeight: 500, color: "#0E1116" }}>{ig.name}</span>
            </div>
          ))}
        </div>
      </section>

      <section id="zm-how" style={{ maxWidth: 1200, margin: "0 auto", padding: "60px 24px 20px", scrollMarginTop: 80 }}>
        <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", textTransform: "uppercase", color: "#4F46E5", margin: "0 0 8px", textAlign: "center" }}>{t.how.kicker}</div>
        <h2 style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: 30, letterSpacing: "-.025em", margin: "0 0 6px", textAlign: "center" }}>{t.how.title}</h2>
        <p style={{ margin: "0 auto 32px", color: "#6B7280", fontSize: 15.5, textAlign: "center", maxWidth: 540 }}>{t.how.sub}</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 18 }}>
          {[["01", t.how.s1t, t.how.s1b], ["02", t.how.s2t, t.how.s2b], ["03", t.how.s3t, t.how.s3b]].map(([n, title, body]) => (
            <div key={n} style={{ background: "#fff", border: "1px solid #E6E9EE", borderRadius: 16, padding: 26 }}>
              <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: 15, color: "#4F46E5", background: "#EEF0FE", width: 38, height: 38, borderRadius: 11, display: "flex", alignItems: "center", justifyContent: "center" }}>{n}</div>
              <h3 style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, fontSize: 18, margin: "16px 0 7px" }}>{title}</h3>
              <p style={{ margin: 0, color: "#5B6472", fontSize: 14.5, lineHeight: 1.55 }}>{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section style={{ maxWidth: 1200, margin: "54px auto 0", padding: "0 24px" }}>
        <div style={{ position: "relative", overflow: "hidden", background: "#0E1116", borderRadius: 22, padding: "48px 40px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 28, flexWrap: "wrap" }}>
          <div style={{ position: "absolute", top: "-55%", right: "-6%", width: 460, height: 460, borderRadius: "50%", background: "radial-gradient(circle,rgba(79,70,229,.38),transparent 68%)", pointerEvents: "none" }}></div>
          <div style={{ position: "absolute", bottom: "-65%", left: "18%", width: 380, height: 380, borderRadius: "50%", background: "radial-gradient(circle,rgba(16,185,129,.14),transparent 68%)", pointerEvents: "none" }}></div>
          <div style={{ position: "relative", maxWidth: 580 }}>
            <h2 style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: "clamp(26px,3.4vw,36px)", letterSpacing: "-.025em", color: "#fff", margin: 0, lineHeight: 1.1 }}>{t.bandTitle(TRIAL_DAYS)}</h2>
            <p style={{ color: "#A8B0BD", fontSize: 16, margin: "14px 0 0", lineHeight: 1.55 }}>{t.band.sub}</p>
          </div>
          <a href="#zm-grid" className="zm2-cta" style={{ position: "relative", textDecoration: "none", background: "#4F46E5", color: "#fff", fontSize: 16, fontWeight: 600, padding: "14px 28px", borderRadius: 999, whiteSpace: "nowrap", boxShadow: "0 8px 22px rgba(79,70,229,.4)" }}>{t.band.cta}</a>
        </div>
      </section>

      <section id="zm-faq" style={{ maxWidth: 920, margin: "0 auto", padding: "64px 24px 20px", scrollMarginTop: 80 }}>
        <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, fontSize: 12.5, letterSpacing: ".14em", textTransform: "uppercase", color: "#4F46E5", margin: "0 0 8px", textAlign: "center" }}>{t.faq.kicker}</div>
        <h2 style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 700, fontSize: 30, letterSpacing: "-.025em", margin: "0 0 6px", textAlign: "center" }}>{t.faq.title}</h2>
        <p style={{ margin: "0 auto 32px", color: "#6B7280", fontSize: 15.5, textAlign: "center", maxWidth: 540 }}>{t.faq.sub}</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {t.faq.items.map((fq, i) => (
            <div key={fq.q} className="zm2-faq-item" style={{ background: "#fff", border: "1px solid #E6E9EE", borderRadius: 14, overflow: "hidden" }}>
              <button onClick={() => setFaqOpen(faqOpen === i ? -1 : i)} style={{ width: "100%", display: "flex", alignItems: "center", gap: 12, background: "transparent", border: "none", cursor: "pointer", textAlign: "left", padding: "20px 22px" }}>
                <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, fontSize: 16.5, color: "#0E1116", lineHeight: 1.3, flex: 1 }}>{fq.q}</span>
                <Ico paths={["M12 5v14", "M5 12h14"]} size={18} strokeWidth={2} stroke="#4F46E5" style={{ flexShrink: 0, transition: "transform .22s ease", transform: faqOpen === i ? "rotate(45deg)" : "none" }} />
              </button>
              {faqOpen === i && <p style={{ margin: 0, padding: "0 22px 20px", color: "#5B6472", fontSize: 14.5, lineHeight: 1.6, animation: "zmFade .25s ease" }}>{fq.a}</p>}
            </div>
          ))}
        </div>
      </section>

      <section style={{ maxWidth: 920, margin: "0 auto", padding: "8px 24px 20px", textAlign: "center" }}>
        <p style={{ color: "#6B7280", fontSize: 14.5, margin: 0 }}>
          {t.talkToUs.note} <a href={`mailto:${t.talkToUs.email}`} className="zm2-link-muted" style={{ color: "#4F46E5", fontWeight: 600, textDecoration: "none" }}>{t.talkToUs.link} →</a>
        </p>
      </section>

      <footer style={{ maxWidth: 1200, margin: "60px auto 0", padding: "34px 24px 44px", borderTop: "1px solid #E6E9EE", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 18, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <span style={{ width: 23, height: 23, border: "1.5px solid #0E1116", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <span style={{ width: 11, height: 11, borderRadius: "50%", background: "#4F46E5", animation: "zmPulse 2.4s ease-in-out infinite" }}></span>
          </span>
          <span style={{ fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, fontSize: 16, letterSpacing: "-.01em" }}>Zero<span style={{ fontWeight: 300 }}>Manual</span></span>
        </div>
        <p style={{ margin: 0, color: "#9099A6", fontSize: 13.5 }}>{t.footer}</p>
      </footer>

      {showLogin && <LoginModal tt={t} onClose={() => setShowLogin(false)} initialMode={loginInitialMode} stayOnPage={loginStayOnPage} onLoginSuccess={onLoginModalSuccess} />}
      {subscribeModalId && (
        <SubscribeModal product={PRODUCTS.find((p) => p.id === subscribeModalId)} lang={lang} t={t}
          onClose={() => setSubscribeModalId(null)} onDone={onSubscribeModalDone} />
      )}
      <CartDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} cartIds={cart} lang={lang} t={t} annual={annual} onRemove={removeFromCart} onCheckout={handleCheckout} />
      <DetailModal id={detailId} lang={lang} t={t} inCart={detailId ? cart.includes(detailId) : false} annual={annual} onClose={() => setDetailId(null)} onSubscribe={subscribeFromDetail} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("app")).render(<App />);
