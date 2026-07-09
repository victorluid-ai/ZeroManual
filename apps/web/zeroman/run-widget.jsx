/* ZeroManual live demo: a Google review comes in → ZeroManual drafts a warm,
   on-brand reply → posts it. Loops through three reviews. Bilingual. */

const { useState, useEffect, useRef } = React;

const RV_CSS = `
.rv-shell { position: relative; max-width: 560px; margin: 0 auto; }
.rv-shell::before { content: ""; position: absolute; inset: -18px -12px -12px 12px; border: 1px dashed #D7DCE3; border-radius: 18px; pointer-events: none; z-index: 0; }
.rv-card { position: relative; z-index: 1; background: #fff; border: 1px solid #E6E9EE; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 50px -28px rgba(27,32,48,0.22), 0 2px 6px -2px rgba(27,32,48,0.06); }
.rv-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid #E6E9EE; }
.rv-title { display: flex; align-items: center; gap: 10px; font-family: 'Space Grotesk', sans-serif; font-weight: 500; font-size: 14px; letter-spacing: -0.005em; color: #0E1116; }
.rv-pulse { width: 8px; height: 8px; border-radius: 50%; background: #4F46E5; box-shadow: 0 0 0 4px color-mix(in srgb, #4F46E5 18%, transparent); animation: rvPulse 2s ease-in-out infinite; }
@keyframes rvPulse { 0%,100% { box-shadow: 0 0 0 4px color-mix(in srgb, #4F46E5 18%, transparent); } 50% { box-shadow: 0 0 0 8px color-mix(in srgb, #4F46E5 8%, transparent); } }
.rv-counter { font-family: 'Space Grotesk', sans-serif; font-weight: 500; font-size: 12px; color: #9099A6; font-variant-numeric: tabular-nums; }
.rv-stage { padding: 18px 18px 8px; min-height: 430px; display: flex; flex-direction: column; gap: 14px; }
.rv-review { opacity: 0; transform: translateY(-8px); transition: opacity 0.45s ease, transform 0.45s cubic-bezier(.2,.7,.3,1); }
.rv-review.in { opacity: 1; transform: translateY(0); }
.rv-bell { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-family: 'Space Grotesk', sans-serif; font-size: 12.5px; color: #9099A6; }
.rv-incoming { background: color-mix(in srgb, #4F46E5 16%, transparent); color: #4F46E5; font-weight: 600; padding: 2px 9px; border-radius: 100px; font-size: 11.5px; letter-spacing: 0.01em; }
.rv-source { letter-spacing: -0.005em; }
.rv-r-card { background: #fff; border: 1px solid #E6E9EE; border-radius: 12px; padding: 14px 14px 12px; }
.rv-r-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.rv-avatar { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 14px; color: #fff; flex-shrink: 0; }
.rv-avatar.tone-warm { background: #4f56c9; }
.rv-avatar.tone-great { background: oklch(0.6 0.12 145); }
.rv-avatar.tone-okay { background: oklch(0.62 0.1 250); }
.rv-r-meta { flex: 1; min-width: 0; }
.rv-r-name { font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 14px; letter-spacing: -0.005em; color: #0E1116; }
.rv-r-sub { display: flex; align-items: center; gap: 6px; margin-top: 1px; }
.rv-stars { display: inline-flex; gap: 1px; font-size: 12.5px; letter-spacing: 0.5px; color: #D7DCE3; line-height: 1; }
.rv-stars .on { color: oklch(0.78 0.16 75); }
.rv-time { font-size: 12px; color: #9099A6; }
.rv-r-title { font-family: 'Space Grotesk', sans-serif; font-weight: 500; font-size: 14px; color: #0E1116; margin-bottom: 5px; letter-spacing: -0.005em; }
.rv-r-body { font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-size: 14.5px; line-height: 1.4; color: #3A4150; }
.rv-draft { opacity: 0; transform: translateY(8px); transition: opacity 0.4s ease, transform 0.4s cubic-bezier(.2,.7,.3,1); border: 1px solid #E6E9EE; border-radius: 12px; background: linear-gradient(to bottom, color-mix(in srgb, #4F46E5 5%, transparent), transparent); padding: 12px 14px 12px; }
.rv-draft.in { opacity: 1; transform: translateY(0); }
.rv-draft-head { display: flex; align-items: center; gap: 8px; font-family: 'Space Grotesk', sans-serif; font-size: 12.5px; color: #3A4150; margin-bottom: 8px; }
.rv-mini-mark { width: 14px; height: 14px; border: 1.5px solid #4F46E5; border-radius: 50%; position: relative; flex-shrink: 0; }
.rv-mini-mark::after { content: ""; position: absolute; inset: 2.5px; background: #4F46E5; border-radius: 50%; }
.rv-draft-title { font-weight: 500; color: #0E1116; }
.rv-dots { display: inline-flex; gap: 3px; margin-left: 4px; }
.rv-dots i { display: inline-block; width: 4px; height: 4px; background: #4F46E5; border-radius: 50%; animation: rvDots 1s ease-in-out infinite; }
.rv-dots i:nth-child(2) { animation-delay: 0.15s; }
.rv-dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes rvDots { 0%,80%,100% { opacity: 0.25; } 40% { opacity: 1; } }
.rv-learn { margin-left: auto; font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-size: 12.5px; color: #9099A6; }
.rv-textarea { background: #fff; border: 1px solid #E6E9EE; border-radius: 10px; padding: 12px 12px 10px; min-height: 96px; font-size: 14px; line-height: 1.45; color: #0E1116; position: relative; }
.rv-reply-text { white-space: pre-wrap; }
.rv-caret { display: inline-block; width: 1.5px; height: 15px; background: #4F46E5; vertical-align: -3px; margin-left: 1px; animation: rvCaret 0.7s steps(1) infinite; }
@keyframes rvCaret { 50% { opacity: 0; } }
.rv-draft-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; gap: 12px; }
.rv-from { font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-size: 13px; color: #9099A6; }
.rv-post { background: #4F46E5; color: #fff; border: 0; font-family: 'Space Grotesk', sans-serif; font-weight: 500; font-size: 13px; padding: 7px 14px; border-radius: 8px; letter-spacing: -0.005em; position: relative; transition: transform 0.2s, box-shadow 0.2s, filter 0.2s; cursor: default; }
.rv-post.firing { transform: scale(0.96); filter: brightness(1.1); box-shadow: 0 0 0 4px color-mix(in srgb, #4F46E5 20%, transparent); }
.rv-post.done { background: oklch(0.65 0.12 150); color: #fff; }
.rv-foot { padding: 12px 18px; border-top: 1px solid #E6E9EE; background: #F8F9FB; font-family: Georgia, 'Times New Roman', serif; font-style: italic; font-size: 13.5px; color: #3A4150; }
`;

const REVIEWS = {
  es: [
    {
      name: "María L.",
      initial: "M",
      tone: "warm",
      stars: 2,
      time_pre: "hace 2 min",
      title: "Pizza buena pero servicio lento",
      body: "La pizza estaba riquísima pero esperamos más de 40 minutos para que nos atendieran. Casi nos vamos.",
      reply: "¡Hola María! Gracias por venir y por contarnos. Tienes toda la razón: 40 minutos es demasiado. El viernes fue un día complicado en cocina, pero no es excusa. Nos encantaría invitarte un postre la próxima vez — escríbenos a hola@ y lo arreglamos.",
      reply_name: "Carla · La Lupita",
    },
    {
      name: "Diego F.",
      initial: "D",
      tone: "great",
      stars: 5,
      time_pre: "hace 1 min",
      title: "El mejor brunch del barrio",
      body: "Llevo viniendo cada domingo y nunca me decepciona. Los huevos benedictinos son de otro planeta. Carla siempre nos atiende como en casa.",
      reply: "¡Diego, qué bonito leerte! 🤍 Le pasamos el mensaje a Carla — se va a poner contentísima. Te guardamos la mesa de la ventana para el próximo domingo. Gracias por seguir viniendo.",
      reply_name: "Carla · La Lupita",
    },
    {
      name: "Sofía R.",
      initial: "S",
      tone: "okay",
      stars: 4,
      time_pre: "hace 3 min",
      title: "Buena comida, ambiente algo ruidoso",
      body: "La comida estuvo deliciosa. Lo único: estaba muy ruidoso para platicar tranquilas. ¿Tienen mesas más quietas?",
      reply: "¡Hola Sofía! Gracias por el feedback — el ruido los sábados es algo que estamos trabajando. Tenemos dos mesas al fondo, junto a la cocina vieja, que son mucho más tranquilas. Si vienes en la semana avísanos y te las reservamos. ✨",
      reply_name: "Carla · La Lupita",
    },
  ],
  en: [
    {
      name: "Maria L.",
      initial: "M",
      tone: "warm",
      stars: 2,
      time_pre: "2 min ago",
      title: "Great pizza, slow service",
      body: "The pizza was delicious but we waited over 40 minutes to get served. We almost left.",
      reply: "Hi Maria — thank you for coming and for telling us straight. You're right, 40 minutes is too long. Friday was rough in the kitchen but that's not an excuse. We'd love to comp a dessert next time — drop us a note at hello@ and we'll sort it.",
      reply_name: "Carla · La Lupita",
    },
    {
      name: "Diego F.",
      initial: "D",
      tone: "great",
      stars: 5,
      time_pre: "1 min ago",
      title: "Best brunch in the neighborhood",
      body: "I come every Sunday and it never disappoints. Eggs benedict are out of this world. Carla always makes us feel at home.",
      reply: "Diego — this made our morning. 🤍 We'll pass it on to Carla, she'll be over the moon. We'll save the window table for you next Sunday. Thank you for keeping us in your routine.",
      reply_name: "Carla · La Lupita",
    },
    {
      name: "Sofia R.",
      initial: "S",
      tone: "okay",
      stars: 4,
      time_pre: "3 min ago",
      title: "Good food, room a bit loud",
      body: "Food was excellent. Only thing: it was very loud to actually have a conversation. Any quieter tables?",
      reply: "Hi Sofia — thank you for the honest note. Saturday noise is something we're working on. There are two tables at the back, near the old kitchen, that are much quieter. If you come midweek let us know and we'll hold them for you. ✨",
      reply_name: "Carla · La Lupita",
    },
  ],
};

const COPY = {
  es: {
    watching: "ZeroManual · vigilando tus reseñas",
    incoming: "Reseña nueva",
    on: "en Google",
    drafting: "ZeroManual está redactando una respuesta",
    learning: "tono cálido, igual al tuyo",
    postBtn: "Publicar respuesta",
    posted: "Respuesta publicada",
    secs: "hace un momento",
    foot: "Esto pasa con cada reseña nueva, día y noche.",
  },
  en: {
    watching: "ZeroManual · watching your reviews",
    incoming: "New review",
    on: "on Google",
    drafting: "ZeroManual is drafting a reply",
    learning: "warm voice, sounds like you",
    postBtn: "Post reply",
    posted: "Reply posted",
    secs: "just now",
    foot: "This happens for every new review, day and night.",
  },
};

function Stars({ n }) {
  return (
    <div className="rv-stars" aria-label={`${n} stars`}>
      {[1,2,3,4,5].map(i => (
        <span key={i} className={i <= n ? "on" : ""}>★</span>
      ))}
    </div>
  );
}

function ReviewReplyVideo({ lang = "es" }) {
  const reviews = REVIEWS[lang] || REVIEWS.es;
  const t = COPY[lang] || COPY.es;
  const [idx, setIdx] = useState(0);
  const [phase, setPhase] = useState(0);
  const [typed, setTyped] = useState(0);
  const review = reviews[idx];
  const replyLen = review.reply.length;

  useEffect(() => {
    if (document.getElementById("rv-demo-styles")) return;
    const el = document.createElement("style");
    el.id = "rv-demo-styles";
    el.textContent = RV_CSS;
    document.head.appendChild(el);
  }, []);

  useEffect(() => {
    setPhase(0);
    setTyped(0);
    const timers = [];
    timers.push(setTimeout(() => setPhase(1), 250));
    timers.push(setTimeout(() => setPhase(2), 1700));
    timers.push(setTimeout(() => setPhase(3), 2700));
    return () => timers.forEach(clearTimeout);
  }, [idx, lang]);

  useEffect(() => {
    if (phase !== 3) return;
    const start = performance.now();
    let raf;
    const totalMs = Math.min(4200, Math.max(2400, replyLen * 22));
    const tick = (now) => {
      const p = Math.min(1, (now - start) / totalMs);
      const chars = Math.floor(p * replyLen);
      setTyped(chars);
      if (p < 1) raf = requestAnimationFrame(tick);
      else {
        setTimeout(() => setPhase(4), 500);
        setTimeout(() => setPhase(5), 1200);
        setTimeout(() => setIdx(i => (i + 1) % reviews.length), 3700);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [phase, idx, lang]);

  const reviewVisible = phase >= 1;
  const draftVisible = phase >= 2;
  const postingNow = phase === 4;
  const posted = phase >= 5;
  const replyShown = review.reply.slice(0, typed);

  return (
    <div className="rv-shell">
      <div className="rv-card">
        <div className="rv-head">
          <div className="rv-title">
            <span className="rv-pulse"></span>
            {t.watching}
          </div>
          <div className="rv-counter">{idx + 1} / {reviews.length}</div>
        </div>

        <div className="rv-stage">
          <div className={`rv-review ${reviewVisible ? "in" : ""}`}>
            <div className="rv-bell">
              <span className="rv-incoming">{t.incoming}</span>
              <span className="rv-source">{t.on}</span>
            </div>
            <div className="rv-r-card">
              <div className="rv-r-head">
                <div className={`rv-avatar tone-${review.tone}`}>{review.initial}</div>
                <div className="rv-r-meta">
                  <div className="rv-r-name">{review.name}</div>
                  <div className="rv-r-sub">
                    <Stars n={review.stars} />
                    <span className="rv-time">· {review.time_pre}</span>
                  </div>
                </div>
              </div>
              <div className="rv-r-title">{review.title}</div>
              <div className="rv-r-body">"{review.body}"</div>
            </div>
          </div>

          <div className={`rv-draft ${draftVisible ? "in" : ""}`}>
            <div className="rv-draft-head">
              <span className="rv-mini-mark"></span>
              <span className="rv-draft-title">
                {posted ? t.posted : t.drafting}
                {phase === 2 && <span className="rv-dots"><i></i><i></i><i></i></span>}
              </span>
              {phase === 2 && <span className="rv-learn">{t.learning}</span>}
            </div>

            <div className="rv-textarea">
              <span className="rv-reply-text">{replyShown}</span>
              {phase === 3 && <span className="rv-caret"></span>}
            </div>

            <div className="rv-draft-foot">
              <span className="rv-from">— {review.reply_name}</span>
              <button className={`rv-post ${postingNow ? "firing" : ""} ${posted ? "done" : ""}`}>
                {posted ? `✓ ${t.posted}` : t.postBtn}
              </button>
            </div>
          </div>
        </div>

        <div className="rv-foot">{t.foot}</div>
      </div>
    </div>
  );
}

/* ============================================================
   REELS DEMO: ZeroManual detects new media → auto-edits a reel →
   writes caption + hashtags in your voice → posts to Instagram.
   Vertical phone preview cycles scenes like a real story. Bilingual.
   ============================================================ */

const RL_CSS = `
.rl-card { position: relative; z-index: 1; background: #fff; border: 1px solid #E6E9EE; border-radius: 16px; overflow: hidden; box-shadow: 0 20px 50px -28px rgba(27,32,48,0.22), 0 2px 6px -2px rgba(27,32,48,0.06); }
.rl-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid #E6E9EE; }
.rl-title { display: flex; align-items: center; gap: 10px; font-family: 'Space Grotesk', sans-serif; font-weight: 500; font-size: 14px; letter-spacing: -0.005em; color: #0E1116; }
.rl-pulse { width: 8px; height: 8px; border-radius: 50%; background: #4F46E5; box-shadow: 0 0 0 4px color-mix(in srgb, #4F46E5 18%, transparent); animation: rvPulse 2s ease-in-out infinite; }
.rl-counter { display: inline-flex; align-items: center; gap: 6px; font-family: 'Space Grotesk', sans-serif; font-weight: 500; font-size: 12px; color: #9099A6; }
.rl-rec { width: 7px; height: 7px; border-radius: 50%; background: #ff5b5b; animation: rvPulse 1.4s ease-in-out infinite; box-shadow: 0 0 0 0 rgba(255,91,91,.4); }
.rl-stage { display: flex; align-items: center; justify-content: center; padding: 22px; min-height: 430px; background: radial-gradient(120% 90% at 50% 8%, #1a1c2b 0%, #0b0c12 70%); position: relative; overflow: hidden; }
.rl-glow { position: absolute; width: 300px; height: 300px; border-radius: 50%; background: radial-gradient(circle, rgba(79,70,229,.4), transparent 70%); filter: blur(14px); z-index: 0; transition: background .6s ease; }
.rl-phone { position: relative; z-index: 1; width: 202px; height: 358px; border-radius: 32px; background: #05060a; padding: 6px; box-shadow: 0 28px 60px -20px rgba(0,0,0,.75), 0 0 0 1px rgba(255,255,255,.07); }
.rl-notch { position: absolute; top: 12px; left: 50%; transform: translateX(-50%); width: 50px; height: 5px; border-radius: 3px; background: #20232c; z-index: 8; }
.rl-screen { position: relative; width: 100%; height: 100%; border-radius: 26px; overflow: hidden; background: #000; }
.rl-slide { position: absolute; inset: 0; animation: rlIn .55s cubic-bezier(.2,.7,.3,1) both; }
@keyframes rlIn { from { opacity: 0; transform: scale(1.04); } to { opacity: 1; transform: none; } }
.rl-scrim { position: absolute; inset: 0; background: linear-gradient(to bottom, rgba(0,0,0,.28), transparent 24%, transparent 52%, rgba(0,0,0,.62)); z-index: 2; }
.rl-content { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 0 20px; color: #fff; z-index: 3; }
.rl-kicker { font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 10.5px; letter-spacing: .16em; text-transform: uppercase; color: rgba(255,255,255,.78); margin-bottom: 12px; padding: 3px 10px; border: 1px solid rgba(255,255,255,.28); border-radius: 100px; animation: rlPop .5s .05s cubic-bezier(.2,.7,.3,1) both; }
.rl-h { font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 25px; line-height: 1.06; letter-spacing: -.02em; white-space: pre-line; text-shadow: 0 2px 14px rgba(0,0,0,.3); animation: rlUp .55s .12s cubic-bezier(.2,.7,.3,1) both; }
.rl-sub { font-size: 12.5px; color: rgba(255,255,255,.85); margin-top: 12px; line-height: 1.4; max-width: 150px; animation: rlUp .55s .22s cubic-bezier(.2,.7,.3,1) both; }
@keyframes rlUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: none; } }
@keyframes rlPop { from { opacity: 0; transform: scale(.8); } to { opacity: 1; transform: none; } }
.rl-visual { margin-bottom: 18px; animation: rlUp .55s .04s cubic-bezier(.2,.7,.3,1) both; }
.rl-emoji { font-size: 58px; filter: drop-shadow(0 8px 18px rgba(0,0,0,.4)); }
.rl-photos { display: flex; gap: 9px; }
.rl-photo { width: 46px; height: 60px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 23px; box-shadow: 0 8px 16px rgba(0,0,0,.35); animation: rlDrop .5s cubic-bezier(.2,.9,.3,1.3) both; }
.rl-photo:nth-child(1){ transform: rotate(-7deg); animation-delay: .15s; }
.rl-photo:nth-child(2){ animation-delay: .3s; z-index: 2; }
.rl-photo:nth-child(3){ transform: rotate(7deg); animation-delay: .45s; }
@keyframes rlDrop { from { opacity: 0; transform: translateY(-26px) scale(.6); } }
.rl-strip { display: flex; gap: 4px; padding: 6px; background: rgba(255,255,255,.1); border-radius: 10px; }
.rl-frame { width: 26px; height: 40px; border-radius: 5px; display: flex; align-items: center; justify-content: center; font-size: 15px; }
.rl-cut { width: 2px; align-self: stretch; background: #fff; box-shadow: 0 0 8px rgba(255,255,255,.8); animation: rlBlink .6s steps(1) infinite; }
@keyframes rlBlink { 50% { opacity: .3; } }
.rl-cap2 { background: rgba(255,255,255,.12); backdrop-filter: blur(4px); border-radius: 12px; padding: 12px 13px; font-size: 12.5px; line-height: 1.4; text-align: left; max-width: 158px; min-height: 58px; border: 1px solid rgba(255,255,255,.16); }
.rl-cap2 .tg { color: #b9c6ff; }
.rl-caret2 { display: inline-block; width: 2px; height: 13px; background: #fff; vertical-align: -2px; margin-left: 1px; animation: rvCaret .7s steps(1) infinite; }
.rl-posted { width: 68px; height: 68px; border-radius: 50%; background: rgba(255,255,255,.16); border: 2px solid #fff; display: flex; align-items: center; justify-content: center; animation: rlPop .5s .05s cubic-bezier(.2,.9,.3,1.4) both; }
.rl-mark { width: 44px; height: 44px; border: 2.4px solid #fff; border-radius: 50%; position: relative; }
.rl-mark::after { content: ""; position: absolute; inset: 7px; background: #fff; border-radius: 50%; }
.rl-prog { position: absolute; top: 11px; left: 11px; right: 11px; display: flex; gap: 4px; z-index: 6; }
.rl-seg { flex: 1; height: 2.5px; border-radius: 2px; background: rgba(255,255,255,.35); overflow: hidden; }
.rl-seg > i { display: block; height: 100%; background: #fff; border-radius: 2px; }
.rl-tagbadge { position: absolute; top: 24px; left: 12px; z-index: 6; display: inline-flex; align-items: center; gap: 5px; background: rgba(0,0,0,.42); backdrop-filter: blur(4px); color: #fff; font-family: 'Space Grotesk', sans-serif; font-weight: 500; font-size: 10.5px; padding: 3px 9px; border-radius: 100px; }
.rl-live-dot { width: 5px; height: 5px; border-radius: 50%; background: #ff5b5b; }
.rl-side { position: absolute; right: 11px; bottom: 56px; display: flex; flex-direction: column; align-items: center; gap: 15px; z-index: 6; color: #fff; }
.rl-side > div { display: flex; flex-direction: column; align-items: center; gap: 2px; font-size: 9.5px; font-family: 'Space Grotesk', sans-serif; }
.rl-botbar { position: absolute; left: 12px; right: 52px; bottom: 13px; z-index: 6; color: #fff; }
.rl-acct2 { display: flex; align-items: center; gap: 6px; font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 11.5px; margin-bottom: 5px; }
.rl-ov-avatar { width: 19px; height: 19px; border-radius: 50%; background: linear-gradient(135deg,#f6b24a,#e8743b); display: flex; align-items: center; justify-content: center; font-size: 9.5px; font-weight: 700; }
.rl-follow { font-size: 9px; border: 1px solid rgba(255,255,255,.55); border-radius: 5px; padding: 1px 6px; margin-left: 2px; }
.rl-music2 { display: flex; align-items: center; gap: 6px; font-size: 10px; color: rgba(255,255,255,.92); overflow: hidden; }
.rl-eq { display: inline-flex; align-items: flex-end; gap: 1.5px; height: 11px; }
.rl-eq i { width: 2px; background: #fff; border-radius: 1px; animation: rlEq .9s ease-in-out infinite; }
.rl-eq i:nth-child(1){ animation-delay: 0s; } .rl-eq i:nth-child(2){ animation-delay: .2s; } .rl-eq i:nth-child(3){ animation-delay: .4s; } .rl-eq i:nth-child(4){ animation-delay: .15s; }
@keyframes rlEq { 0%,100% { height: 3px; } 50% { height: 11px; } }
.rl-mticker { white-space: nowrap; }
.rl-foot { padding: 12px 18px; border-top: 1px solid #E6E9EE; background: #F8F9FB; font-family: Georgia, serif; font-style: italic; font-size: 13.5px; color: #3A4150; }
`;

const REEL_SCENES = {
  es: [
    { type: "hook",    dur: 2600, bg: "linear-gradient(165deg,#5b53f0,#2a2580)", glow: "rgba(91,83,240,.45)", kicker: "POV", title: "Nunca más\neditas un reel", sub: "lo hace ZeroManual por ti", emoji: "🎬" },
    { type: "upload",  dur: 2700, bg: "linear-gradient(165deg,#1d2233,#0b0d16)", glow: "rgba(120,130,160,.3)", kicker: "Paso 1", title: "Sube tus fotos", sub: "o las toma de tu galería", photos: ["🍳", "🥐", "☕"] },
    { type: "edit",    dur: 2900, bg: "linear-gradient(165deg,#3a2f9a,#16182a)", glow: "rgba(79,70,229,.5)", kicker: "Paso 2", title: "La IA las edita", sub: "cortes, ritmo y audio en tendencia", frames: ["🍳", "🥐", "☕", "🪟"] },
    { type: "caption", dur: 4400, bg: "linear-gradient(165deg,#141622,#0b0d14)", glow: "rgba(79,70,229,.4)", kicker: "Paso 3", title: "Escribe tu pie", caption: "Domingo de brunch en La Lupita 🍳 te guardamos mesa ", tags: "#LaLupita #brunch" },
    { type: "publish", dur: 2800, bg: "linear-gradient(165deg,#11885b,#0a3a2b)", glow: "rgba(16,185,129,.45)", kicker: "Paso 4", title: "Y lo publica\nsolo", sub: "en Instagram y TikTok" },
    { type: "end",     dur: 3000, bg: "linear-gradient(165deg,#5b53f0,#3730a3)", glow: "rgba(91,83,240,.5)", title: "Tus reels,\nen piloto automático", sub: "ZeroManual" },
  ],
  en: [
    { type: "hook",    dur: 2600, bg: "linear-gradient(165deg,#5b53f0,#2a2580)", glow: "rgba(91,83,240,.45)", kicker: "POV", title: "You never\nedit a reel again", sub: "ZeroManual does it for you", emoji: "🎬" },
    { type: "upload",  dur: 2700, bg: "linear-gradient(165deg,#1d2233,#0b0d16)", glow: "rgba(120,130,160,.3)", kicker: "Step 1", title: "Drop your photos", sub: "or it grabs them from your gallery", photos: ["🍳", "🥐", "☕"] },
    { type: "edit",    dur: 2900, bg: "linear-gradient(165deg,#3a2f9a,#16182a)", glow: "rgba(79,70,229,.5)", kicker: "Step 2", title: "AI edits them", sub: "cuts, pacing and trending audio", frames: ["🍳", "🥐", "☕", "🪟"] },
    { type: "caption", dur: 4400, bg: "linear-gradient(165deg,#141622,#0b0d14)", glow: "rgba(79,70,229,.4)", kicker: "Step 3", title: "Writes the caption", caption: "Sunday brunch at La Lupita 🍳 we'll save you a table ", tags: "#LaLupita #brunch" },
    { type: "publish", dur: 2800, bg: "linear-gradient(165deg,#11885b,#0a3a2b)", glow: "rgba(16,185,129,.45)", kicker: "Step 4", title: "And posts it\nfor you", sub: "to Instagram and TikTok" },
    { type: "end",     dur: 3000, bg: "linear-gradient(165deg,#5b53f0,#3730a3)", glow: "rgba(91,83,240,.5)", title: "Your reels,\non autopilot", sub: "ZeroManual" },
  ],
};

const RL_COPY = {
  es: {
    watching: "ZeroManual · creando tu contenido",
    preview: "Reel",
    music: "Sunny Mornings · audio en tendencia",
    acct: "lalupita", follow: "Seguir",
    foot: "Tus fotos se vuelven reels y se publican solas, cada semana.",
  },
  en: {
    watching: "ZeroManual · creating your content",
    preview: "Reel",
    music: "Sunny Mornings · trending audio",
    acct: "lalupita", follow: "Follow",
    foot: "Your photos become reels and post themselves, every week.",
  },
};

function HeartIco(){ return (<svg width="22" height="22" viewBox="0 0 24 24" fill="rgba(255,255,255,.92)"><path d="M12 21s-7.5-4.6-9.7-9C1 9.3 2.4 6 5.6 6c1.9 0 3.2 1.1 4 2.2C10.4 7.1 11.7 6 13.6 6 16.8 6 20 9.3 18.3 12 16.1 16.4 12 21 12 21z"/></svg>); }
function CommentIco(){ return (<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,.92)" strokeWidth="1.8"><path d="M21 12a8 8 0 01-11.5 7.2L4 20.5l1.3-5A8 8 0 1121 12z"/></svg>); }
function ShareIco(){ return (<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,.92)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M22 3L11 14"/><path d="M22 3l-7 19-4-8-8-4 19-7z"/></svg>); }

function ReelScene({ scene, prog, lang }) {
  if (scene.type === "hook" || scene.type === "publish" || scene.type === "end") {
    const visual = scene.emoji
      ? <div className="rl-visual"><div className="rl-emoji">{scene.emoji}</div></div>
      : scene.type === "publish"
        ? <div className="rl-visual"><div className="rl-posted"><svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5"/></svg></div></div>
        : scene.type === "end"
          ? <div className="rl-visual"><div style={{ width: 56, height: 56, border: "2.4px solid #fff", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center" }}><span style={{ width: 24, height: 24, borderRadius: "50%", background: "#fff" }}></span></div></div>
          : null;
    return (
      <div className="rl-content">
        {visual}
        {scene.kicker && <div className="rl-kicker">{scene.kicker}</div>}
        <div className="rl-h">{scene.title}</div>
        {scene.sub && <div className="rl-sub" style={scene.type === "end" ? { fontFamily: "'Space Grotesk',sans-serif", fontWeight: 600, letterSpacing: ".02em", fontSize: 14, color: "#fff" } : null}>{scene.sub}</div>}
      </div>
    );
  }
  if (scene.type === "upload") {
    return (
      <div className="rl-content">
        <div className="rl-visual"><div className="rl-photos">{scene.photos.map((p, i) => (<div key={i} className="rl-photo" style={{ background: ["linear-gradient(150deg,#f6b24a,#e8743b)", "linear-gradient(150deg,#e9a05c,#a85f2c)", "linear-gradient(150deg,#7c5a43,#3f2a1d)"][i] }}>{p}</div>))}</div></div>
        <div className="rl-kicker">{scene.kicker}</div>
        <div className="rl-h">{scene.title}</div>
        <div className="rl-sub">{scene.sub}</div>
      </div>
    );
  }
  if (scene.type === "edit") {
    const cut = Math.floor(prog * scene.frames.length);
    return (
      <div className="rl-content">
        <div className="rl-visual"><div className="rl-strip">{scene.frames.map((f, i) => (<React.Fragment key={i}>{i === cut && <div className="rl-cut"></div>}<div className="rl-frame" style={{ background: ["linear-gradient(150deg,#f6b24a,#e8743b)", "linear-gradient(150deg,#e9a05c,#a85f2c)", "linear-gradient(150deg,#7c5a43,#3f2a1d)", "linear-gradient(150deg,#6aa9a0,#2f6f6a)"][i], opacity: i <= cut ? 1 : 0.4 }}>{f}</div></React.Fragment>))}</div></div>
        <div className="rl-kicker">{scene.kicker}</div>
        <div className="rl-h">{scene.title}</div>
        <div className="rl-sub">{scene.sub}</div>
      </div>
    );
  }
  if (scene.type === "caption") {
    const total = scene.caption.length;
    const shown = Math.min(total, Math.floor(prog * total * 1.5));
    const done = shown >= total;
    return (
      <div className="rl-content">
        <div className="rl-kicker">{scene.kicker}</div>
        <div className="rl-h" style={{ fontSize: 20, marginBottom: 14 }}>{scene.title}</div>
        <div className="rl-visual rl-cap2" style={{ marginBottom: 0 }}>
          {scene.caption.slice(0, shown)}
          {done && <span className="tg">{scene.tags}</span>}
          {!done && <span className="rl-caret2"></span>}
        </div>
      </div>
    );
  }
  return null;
}

function ReelsPostVideo({ lang = "es" }) {
  const scenes = REEL_SCENES[lang] || REEL_SCENES.es;
  const t = RL_COPY[lang] || RL_COPY.es;
  const [i, setI] = useState(0);
  const [prog, setProg] = useState(0);
  const [likes, setLikes] = useState(842);

  useEffect(() => {
    if (document.getElementById("rl-demo-styles")) return;
    const el = document.createElement("style");
    el.id = "rl-demo-styles";
    el.textContent = RL_CSS;
    document.head.appendChild(el);
  }, []);

  // auto-advancing playhead — drives the whole reel like a video
  useEffect(() => {
    setProg(0);
    const dur = scenes[i].dur || 2600;
    const start = performance.now();
    let raf;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / dur);
      setProg(p);
      if (p < 1) raf = requestAnimationFrame(tick);
      else setI(v => (v + 1) % scenes.length);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [i, lang]);

  // likes tick up while it "plays"
  useEffect(() => {
    const iv = setInterval(() => setLikes(l => l + 1 + Math.floor(Math.random() * 3)), 650);
    return () => clearInterval(iv);
  }, []);

  const scene = scenes[i];
  const likesLabel = likes >= 1000 ? (likes / 1000).toFixed(1) + "k" : String(likes);

  return (
    <div className="rv-shell">
      <div className="rl-card">
        <div className="rl-head">
          <div className="rl-title"><span className="rl-pulse"></span>{t.watching}</div>
          <div className="rl-counter"><span className="rl-rec"></span>{t.preview}</div>
        </div>

        <div className="rl-stage">
          <div className="rl-glow" style={{ background: `radial-gradient(circle, ${scene.glow}, transparent 70%)` }}></div>
          <div className="rl-phone">
            <div className="rl-notch"></div>
            <div className="rl-screen">
              <div key={i} className="rl-slide" style={{ background: scene.bg }}>
                <div className="rl-scrim"></div>
                <ReelScene scene={scene} prog={prog} lang={lang} />
              </div>

              <div className="rl-prog">
                {scenes.map((s, j) => (
                  <div key={j} className="rl-seg"><i style={{ width: j < i ? "100%" : j === i ? `${prog * 100}%` : "0%" }}></i></div>
                ))}
              </div>

              <div className="rl-tagbadge"><span className="rl-live-dot"></span>@{t.acct}</div>

              <div className="rl-side">
                <div><HeartIco /><span>{likesLabel}</span></div>
                <div><CommentIco /><span>84</span></div>
                <div><ShareIco /></div>
              </div>

              <div className="rl-botbar">
                <div className="rl-acct2"><span className="rl-ov-avatar">L</span>@{t.acct}<span className="rl-follow">{t.follow}</span></div>
                <div className="rl-music2">
                  <span className="rl-eq"><i></i><i></i><i></i><i></i></span>
                  <span className="rl-mticker">{t.music}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="rl-foot">{t.foot}</div>
      </div>
    </div>
  );
}

/* ============================================================
   CAROUSEL: swipe / arrows / tabs between the live demos.
   ============================================================ */

const LD_CSS = `
.ld-wrap { max-width: 600px; margin: 0 auto; }
.ld-viewport { overflow: hidden; touch-action: pan-y; cursor: grab; }
.ld-viewport.drag { cursor: grabbing; }
.ld-track { display: flex; }
.ld-slide { flex: 0 0 100%; min-width: 0; padding: 18px 12px 6px; }
.ld-nav { display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 16px; }
.ld-arrow { width: 38px; height: 38px; border-radius: 50%; border: 1px solid #E6E9EE; background: #fff; color: #3A4150; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: border-color .15s, background .15s, color .15s, opacity .15s; flex-shrink: 0; }
.ld-arrow:hover { border-color: #4F46E5; color: #4F46E5; }
.ld-arrow:disabled { opacity: .35; cursor: default; border-color: #E6E9EE; color: #3A4150; }
.ld-tabs { display: flex; gap: 6px; }
.ld-tab { font-family: 'Space Grotesk', sans-serif; font-weight: 500; font-size: 13px; padding: 7px 14px; border-radius: 100px; border: 1px solid #E6E9EE; background: #fff; color: #5B6472; cursor: pointer; transition: all .15s; white-space: nowrap; }
.ld-tab:hover { border-color: #CBD2DC; }
.ld-tab.on { background: #4F46E5; border-color: #4F46E5; color: #fff; }
`;

const LD_TABS = {
  es: ["Reseñas de Google", "Reels en redes"],
  en: ["Google reviews", "Social reels"],
};

function LiveDemoCarousel({ lang = "es" }) {
  const [active, setActive] = useState(0);
  const [dragging, setDragging] = useState(false);
  const tabs = LD_TABS[lang] || LD_TABS.es;
  const count = 2;

  const viewportRef = useRef(null);
  const trackRef = useRef(null);
  const posRef = useRef(0);       // current animated offset, in slide units
  const targetRef = useRef(0);    // destination slide index
  const dragRef = useRef(0);      // live drag offset in px
  const widthRef = useRef(1);
  const rafRef = useRef(null);
  const startX = useRef(null);
  const draggingRef = useRef(false);

  useEffect(() => {
    if (!document.getElementById("ld-demo-styles")) {
      const el = document.createElement("style");
      el.id = "ld-demo-styles";
      el.textContent = LD_CSS;
      document.head.appendChild(el);
    }
    const measure = () => {
      widthRef.current = (viewportRef.current && viewportRef.current.offsetWidth) || 1;
      paint();
    };
    measure();
    window.addEventListener("resize", measure);
    return () => { window.removeEventListener("resize", measure); if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, []);

  // Directly set the track transform — bypasses React so the
  // continuously-animating demo children can't freeze the slide.
  const paint = () => {
    if (trackRef.current) trackRef.current.style.transform = `translateX(${-posRef.current * widthRef.current + dragRef.current}px)`;
  };

  const animate = () => {
    if (rafRef.current) return;
    const tick = () => {
      const diff = targetRef.current - posRef.current;
      if (Math.abs(diff) < 0.0015) {
        posRef.current = targetRef.current;
        paint();
        rafRef.current = null;
        return;
      }
      posRef.current += diff * 0.2;
      paint();
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  };

  const go = (n) => {
    n = Math.max(0, Math.min(count - 1, n));
    setActive(n);
    targetRef.current = n;
    animate();
  };

  const onDown = (e) => {
    if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null; }
    startX.current = e.clientX;
    widthRef.current = (viewportRef.current && viewportRef.current.offsetWidth) || 1;
    draggingRef.current = true;
    setDragging(true);
    if (e.currentTarget.setPointerCapture && e.pointerId != null) {
      try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) {}
    }
  };
  const onMove = (e) => {
    if (startX.current == null) return;
    let dx = e.clientX - startX.current;
    const at = Math.round(posRef.current);
    if ((at === 0 && dx > 0) || (at === count - 1 && dx < 0)) dx *= 0.32; // rubber-band ends
    dragRef.current = dx;
    paint();
  };
  const onUp = () => {
    if (startX.current == null) return;
    const dx = dragRef.current;
    const threshold = widthRef.current * 0.16;
    let next = targetRef.current;
    if (dx < -threshold) next = Math.min(count - 1, targetRef.current + 1);
    else if (dx > threshold) next = Math.max(0, targetRef.current - 1);
    startX.current = null;
    dragRef.current = 0;
    draggingRef.current = false;
    setDragging(false);
    go(next);
  };

  return (
    <div className="ld-wrap">
      <div
        ref={viewportRef}
        className={`ld-viewport ${dragging ? "drag" : ""}`}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onPointerLeave={() => { if (draggingRef.current) onUp(); }}
      >
        <div className="ld-track" ref={trackRef}>
          <div className="ld-slide"><ReviewReplyVideo lang={lang} /></div>
          <div className="ld-slide"><ReelsPostVideo lang={lang} /></div>
        </div>
      </div>
      <div className="ld-nav">
        <button className="ld-arrow" onClick={() => go(active - 1)} disabled={active === 0} aria-label="Prev">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 6l-6 6 6 6"/></svg>
        </button>
        <div className="ld-tabs">
          {tabs.map((label, i) => (
            <button key={i} className={`ld-tab ${active === i ? "on" : ""}`} onClick={() => go(i)}>{label}</button>
          ))}
        </div>
        <button className="ld-arrow" onClick={() => go(active + 1)} disabled={active === count - 1} aria-label="Next">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 6l6 6-6 6"/></svg>
        </button>
      </div>
    </div>
  );
}

window.ReviewReplyVideo = ReviewReplyVideo;
window.ReelsPostVideo = ReelsPostVideo;
window.LiveDemoCarousel = LiveDemoCarousel;
module.exports = { ReviewReplyVideo, ReelsPostVideo, LiveDemoCarousel };
