"""Bucle simulado: reseña → borrador en /client → aceptar, editar o rechazar.

La publicación a Google no sale de estos tests: ``trigger_publish_reply`` está mockeado.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def no_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_AI_MODE", "off")
    monkeypatch.setenv("ZEROMANUAL_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("MANUALZERO_STRIPE_SECRET_KEY", "")
    monkeypatch.setenv("ZEROMANUAL_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("MANUALZERO_WEBHOOK_SECRET", "test-webhook-secret")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ZEROMANUAL_DB_PATH", str(tmp_path / "draft-loop.db"))
    import importlib
    import apps.interface.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


def _activate(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, str]:
    import apps.interface.api as api_module

    monkeypatch.setenv("N8N_TEMPLATE_IDS", '{"google_reviews": "tpl-1"}')
    reg = client.post(
        "/client/register",
        json={"name": "Reviews Biz", "email": "loop@example.com", "password": "secret123"},
    )
    assert reg.status_code == 200
    body = reg.json()
    client_id = body["client"]["client_id"]
    auth = {"Authorization": f"Bearer {body['token']}"}
    api_module.runtime.store.save_google_creds(
        client_id=client_id,
        refresh_token="reftok",
        access_token="tok",
        token_expiry=None,
        google_email="biz@example.com",
        location_id="accounts/1/locations/1",
    )
    monkeypatch.setattr(api_module._n8n, "duplicate_template", lambda **kwargs: "wf-reviews-1")
    activated = client.post("/client/automations/google_reviews/activate", headers=auth)
    assert activated.status_code == 200
    return auth, client_id


def _push(client: TestClient, client_id: str, review_id: str, reply: str) -> dict:
    resp = client.post(
        "/internal/automations/google_reviews/drafts",
        headers={"X-Webhook-Secret": "test-webhook-secret"},
        json={
            "client_id": client_id,
            "review_id": review_id,
            "reviewer_name": "Ana",
            "rating": "FIVE",
            "source_text": "Muy bueno",
            "suggested_reply": reply,
        },
    )
    assert resp.status_code == 200
    return resp.json()


def test_simulated_review_accept_edit_and_reject(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate(client, monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append(payload),
    )

    pushed = _push(client, client_id, "rev-accept", "Gracias Ana")
    draft_id = pushed["draft"]["draft_id"]
    assert pushed["draft"]["status"] == "pending"
    assert calls == []

    listed = client.get("/client/automations/google_reviews/drafts?status=pending", headers=auth)
    assert listed.status_code == 200
    pending = listed.json()["drafts"]
    assert len(pending) == 1
    assert pending[0]["draft_id"] == draft_id
    assert pending[0]["suggested_reply"] == "Gracias Ana"
    assert pending[0]["review_id"] == "rev-accept"

    accepted = client.post(
        f"/client/drafts/{draft_id}/approve",
        headers=auth,
        json={"final_reply": "Gracias Ana"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["draft"]["status"] == "approved"
    assert calls == [
        {
            "draft_id": draft_id,
            "client_id": client_id,
            "business_id": calls[0]["business_id"] if calls else None,
            "review_id": "rev-accept",
            "final_reply": "Gracias Ana",
        }
    ]
    assert calls[0]["final_reply"] == "Gracias Ana"

    edited_push = _push(client, client_id, "rev-edit", "Texto sugerido")
    edited = client.post(
        f"/client/drafts/{edited_push['draft']['draft_id']}/approve",
        headers=auth,
        json={"final_reply": "Texto editado por el cliente"},
    )
    assert edited.status_code == 200
    assert edited.json()["draft"]["status"] == "edited"
    assert edited.json()["draft"]["final_reply"] == "Texto editado por el cliente"
    assert calls[-1]["review_id"] == "rev-edit"
    assert calls[-1]["final_reply"] == "Texto editado por el cliente"

    rejected_push = _push(client, client_id, "rev-reject", "No enviar")
    before = len(calls)
    rejected = client.post(
        f"/client/drafts/{rejected_push['draft']['draft_id']}/reject",
        headers=auth,
    )
    assert rejected.status_code == 200
    assert rejected.json()["draft"]["status"] == "rejected"
    assert len(calls) == before

    again = client.post(
        f"/client/drafts/{rejected_push['draft']['draft_id']}/reject",
        headers=auth,
    )
    assert again.status_code == 400
    assert len(calls) == before

    history = client.get("/client/automations/google_reviews/drafts", headers=auth)
    statuses = {row["review_id"]: row["status"] for row in history.json()["drafts"]}
    assert statuses == {
        "rev-accept": "approved",
        "rev-edit": "edited",
        "rev-reject": "rejected",
    }


def test_repeat_push_is_idempotent_and_does_not_republish(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate(client, monkeypatch)
    business_id = api_module.runtime.store.ensure_default_business(client_id)["business_id"]
    api_module.runtime.store.update_automation_settings(
        client_id, business_id, "google_reviews", "auto"
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append(payload),
    )

    first = _push(client, client_id, "rev-same", "Gracias")
    second = _push(client, client_id, "rev-same", "Gracias otra vez")
    assert first["draft"]["draft_id"] == second["draft"]["draft_id"]
    assert second["draft"]["status"] == "auto_sent"
    assert second["draft"]["suggested_reply"] == "Gracias"
    assert len(calls) == 1

    listed = client.get("/client/automations/google_reviews/drafts", headers=auth)
    assert len(listed.json()["drafts"]) == 1


def test_empty_approve_does_not_publish(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apps.interface.api as api_module

    auth, client_id = _activate(client, monkeypatch)
    calls: list[dict] = []
    monkeypatch.setattr(
        api_module._n8n,
        "trigger_publish_reply",
        lambda cid, bid, payload: calls.append(payload),
    )
    pushed = _push(client, client_id, "rev-empty", "Borrador")
    resp = client.post(
        f"/client/drafts/{pushed['draft']['draft_id']}/approve",
        headers=auth,
        json={"final_reply": "   "},
    )
    assert resp.status_code == 400
    assert calls == []
    still = client.get("/client/automations/google_reviews/drafts?status=pending", headers=auth)
    assert len(still.json()["drafts"]) == 1


def test_client_ui_offers_edit_accept_and_reject() -> None:
    html = Path("apps/interface/client.html").read_text(encoding="utf-8")
    assert "Puedes editar el texto" in html
    assert 'class="draft-text"' in html
    assert "/approve" in html
    assert "/reject" in html
    assert 'data-action="approve"' in html
    assert 'data-action="reject"' in html
    assert "Aprobar y publicar" in html
    assert "Aceptar todas (" in html
    assert "Respuestas automáticas" in html
    assert "Buscar por nombre" in html
    assert "Aprobada por ti" in html
    assert "Editada por ti" in html
    assert "Automática" in html
    assert "¿Activar respuestas automáticas?" in html
    assert "Activar y publicar pendientes" in html
    assert "topbar-brand-mark" in html
    assert 'reply_mode' in html
    assert "Se publicarán en Google" in html
    assert "Automatizaciones" in html
    assert "view: 'automations'" in html
    assert "Gestionar suscripción" in html
    assert "Pausar automatización" in html
    assert "Cancelar suscripción" in html
    assert "Ya la tienes" in html
    assert "Próximamente" in html
    assert "Añadir automatización" in html
    assert "También en Ajustes" in html
    assert 'label: \'Catálogo\'' not in html
    assert 'label: \'Ajustes\'' not in html


def _extract_js_function(source: str, name: str) -> str:
    marker = f"function {name}("
    start = source.find(marker)
    assert start != -1, name
    line_start = source.rfind("\n", 0, start) + 1
    if source[line_start:start].strip() == "async":
        start = line_start + source[line_start:start].find("async")
    brace = source.find("{", start)
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"función sin cerrar: {name}")


def _js_const_line(source: str, name: str) -> str:
    match = re.search(rf"const {name} = [^;]+;", source)
    assert match, name
    return match.group(0)


def test_open_reviews_refresh_pending_without_reload(client: TestClient, tmp_path: Path) -> None:
    """La vista abierta vuelve a pedir borradores al recuperar el foco y, unos minutos, por polling."""
    page = client.get("/client")
    assert page.status_code == 200
    html = page.text
    assert "document.addEventListener('visibilitychange', onReviewSurfaceResume)" in html
    assert "window.addEventListener('focus', onReviewSurfaceResume)" in html
    assert "armReviewWatch();" in html
    assert "activatedType === 'google_reviews') reviewsActivatedAt = Date.now();" in html
    assert "refreshOpenReviews('poll')" in html
    assert "refreshOpenReviews('resume')" in html
    assert "}, REVIEW_POLL_MS);" in html

    functions = [
        "reviewRefreshPlan",
        "currentReviewInput",
        "draftsSignature",
        "stopReviewPoll",
        "scheduleReviewPoll",
        "applyReviewPlan",
        "armReviewWatch",
        "runReviewRefresh",
        "refreshOpenReviews",
        "onReviewSurfaceResume",
    ]
    script = "\n".join(
        [
            _js_const_line(html, "REVIEW_POLL_MS"),
            _js_const_line(html, "REVIEW_WATCH_MS"),
            r"""
let now = 0;
Date.now = function () { return now; };
let token = 'tok';
let activeView = 'google_reviews';
let pendingReviewCount = 0;
let cachedDrafts = [];
let reviewLoadError = '';
let reviewsActivatedAt = 0;
let reviewWatchUntil = 0;
let reviewPollTimer = null;
let reviewResumeTimer = null;
let reviewRefreshInFlight = null;
let document = {
  visibilityState: 'visible',
  activeElement: null,
  querySelectorAll: function () { return []; },
};
function activeReviewRows() {
  return [{ automation_type: 'google_reviews', status: 'active', business_id: 'BIZ-1' }];
}
const fetches = [];
const paints = [];
function draftRow(id) {
  return {
    draft_id: id, status: 'pending', suggested_reply: id, final_reply: null,
    reviewer_name: id, rating: 'FIVE', source_text: 'Bien',
    created_at: '2026-10-08T08:00:00Z', updated_at: '2026-10-08T08:00:00Z',
  };
}
async function refreshReviewCache() {
  fetches.push(now);
  let rows = [];
  if (now >= 150000) rows = [draftRow('DRF-1'), draftRow('DRF-2')];
  else if (now >= 120001) rows = [draftRow('DRF-1')];
  cachedDrafts = rows.map(function (row) { return Object.assign({}, row); });
  pendingReviewCount = cachedDrafts.length;
  reviewLoadError = '';
}
function captureReviewFocus() { return null; }
function restoreReviewFocus() {}
function syncChrome() {}
function paintReviewList() { paints.push({ t: now, n: pendingReviewCount }); }
function renderNav() {}
function $(id) { return id === 'review-list' ? { id: id } : null; }
const queue = [];
let seq = 0;
function setTimeout(fn, ms) {
  const id = ++seq;
  queue.push({ id: id, fn: fn, at: now + ms, cancelled: false, ran: false });
  return id;
}
function clearTimeout(id) {
  queue.forEach(function (item) { if (item.id === id) item.cancelled = true; });
}
async function settle() {
  for (let i = 0; i < 20; i++) await Promise.resolve();
}
async function flushUntil(limit) {
  while (true) {
    await settle();
    let next = null;
    queue.forEach(function (item) {
      if (item.cancelled || item.ran || item.at > limit) return;
      if (!next || item.at < next.at) next = item;
    });
    if (!next) { now = limit; return; }
    now = next.at;
    next.ran = true;
    next.fn();
  }
}
""",
            *[_extract_js_function(html, name) for name in functions],
            r"""
async function main() {
  const sample = reviewRefreshPlan({
    now: 0, activeView: 'google_reviews', hasAutomation: true, pendingCount: 0,
    activatedAt: 0, watchUntil: 0, visibility: 'visible', reason: 'arm', arm: true,
  });
  armReviewWatch();
  const firstAt = 120001;
  const secondAt = 150000;
  await flushUntil(reviewWatchUntil + sample.pollMs * 2);
  const watchEnd = sample.watchMs;
  const lateFetches = fetches.filter(function (t) { return t > watchEnd; });
  const beforeResume = fetches.length;
  now = watchEnd + sample.pollMs * 3;
  document.visibilityState = 'visible';
  await refreshOpenReviews('resume');
  await settle();
  const resumeFetched = fetches.length > beforeResume;
  const beforeHidden = fetches.length;
  document.visibilityState = 'hidden';
  await refreshOpenReviews('poll');
  await settle();
  const hiddenFetched = fetches.length > beforeHidden;
  document.visibilityState = 'hidden';
  const queuedBefore = queue.length;
  onReviewSurfaceResume();
  const hiddenArmedTimer = queue.length > queuedBefore;
  document.visibilityState = 'visible';
  const beforeFocus = fetches.length;
  onReviewSurfaceResume();
  await flushUntil(now + 1000);
  activeView = 'home';
  armReviewWatch();
  const queuedAfterLeave = queue.filter(function (item) { return !item.cancelled && !item.ran; }).length;
  const activated = reviewRefreshPlan({
    now: now, activeView: 'google_reviews', hasAutomation: true, pendingCount: 2,
    activatedAt: now - 60000, watchUntil: 0, visibility: 'visible', reason: 'arm', arm: true,
  });
  const idle = reviewRefreshPlan({
    now: now, activeView: 'google_reviews', hasAutomation: true, pendingCount: 2,
    activatedAt: 0, watchUntil: 0, visibility: 'visible', reason: 'arm', arm: true,
  });
  console.log(JSON.stringify({
    pollMs: sample.pollMs,
    watchMs: sample.watchMs,
    firstFetch: fetches[0],
    paints: paints,
    lateFetches: lateFetches,
    resumeFetched: resumeFetched,
    hiddenFetched: hiddenFetched,
    queuedAfterLeave: queuedAfterLeave,
    activatedSchedules: activated.schedulePoll,
    idleSchedules: idle.schedulePoll,
    hiddenArmedTimer: hiddenArmedTimer,
    focusFetched: fetches.length > beforeFocus,
    firstAt: firstAt,
    secondAt: secondAt,
  }));
}
main();
""",
        ]
    )
    path = tmp_path / "reviews-refresh.js"
    path.write_text(script, encoding="utf-8")
    proc = subprocess.run(["node", str(path)], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert 15000 <= result["pollMs"] <= 30000
    assert 3 * 60 * 1000 <= result["watchMs"] <= 8 * 60 * 1000
    assert result["firstFetch"] == result["pollMs"]
    assert result["paints"]
    first = result["paints"][0]
    second = next(item for item in result["paints"] if item["n"] == 2)
    assert first["n"] == 1
    assert 0 < first["t"] - result["firstAt"] <= 30000
    assert 0 < second["t"] - result["secondAt"] <= 30000
    assert result["lateFetches"] == []
    assert result["resumeFetched"] is True
    assert result["hiddenFetched"] is False
    assert result["queuedAfterLeave"] == 0
    assert result["activatedSchedules"] is True
    assert result["idleSchedules"] is False
    assert result["hiddenArmedTimer"] is False
    assert result["focusFetched"] is True
