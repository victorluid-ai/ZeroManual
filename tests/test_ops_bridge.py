from __future__ import annotations

from apps.integrations.ops_bridge import OpsCenterBridge


def test_bridge_disabled_without_config(monkeypatch) -> None:
    monkeypatch.delenv("ZEROMANUAL_OPS_URL", raising=False)
    monkeypatch.delenv("ZEROMANUAL_OPS_API_KEY", raising=False)
    bridge = OpsCenterBridge()
    assert bridge.enabled is False
    assert bridge.emit_event("AgentBillingOps", "create_invoice", {}) is None


def test_bridge_posts_event(monkeypatch) -> None:
    monkeypatch.setenv("ZEROMANUAL_OPS_URL", "http://ops.test")
    monkeypatch.setenv("ZEROMANUAL_OPS_API_KEY", "k")
    monkeypatch.setenv("ZEROMANUAL_OPS_TENANT_ID", "zeromanual")

    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"status": "COMPLETED"}

    class FakeClient:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            calls.append({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr("apps.integrations.ops_bridge.httpx.Client", FakeClient)
    bridge = OpsCenterBridge()
    assert bridge.enabled is True
    result = bridge.emit_event(
        "AgentBillingOps",
        "create_invoice",
        {"amount_eur": 10, "client_name": "X"},
    )
    assert result == {"status": "COMPLETED"}
    assert calls[0]["url"] == "http://ops.test/api/v1/events"
    assert calls[0]["headers"]["X-API-Key"] == "k"
    assert calls[0]["json"]["tenant_id"] == "zeromanual"
