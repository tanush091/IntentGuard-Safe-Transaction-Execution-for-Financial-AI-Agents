"""
End-to-end over HTTP: the gateway API talks to the provider API through the real HttpProvider
(the provider app is mounted in-process via httpx's ASGI transport, so no ports are needed).
"""

from __future__ import annotations

import importlib

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("PAYSIM_STATE_PATH", str(tmp_path / "paysim.json"))
    monkeypatch.setenv("PAYSIM_SETTLE_DELAY_S", "0")
    import provider_api.main as provider_main

    provider_main = importlib.reload(provider_main)
    provider_client = TestClient(provider_main.app)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'gw.db').as_posix()}")
    monkeypatch.setenv("PAYMENT_PROVIDER", "http")
    monkeypatch.setenv("DEMO_SEED", "false")
    import gateway_api.settings as gw_settings
    import gateway_api.main as gw_main

    importlib.reload(gw_settings)
    gw_main = importlib.reload(gw_main)
    from intentguard.providers.http import HttpProvider

    http = HttpProvider("http://provider", client=provider_client)
    monkeypatch.setattr(gw_main, "build_provider", lambda: (http, None))
    monkeypatch.setattr(gw_main, "seed_provider_order",
                        lambda _sim, oid, cust, cur, amt: provider_client.post(
                            "/v1/orders", json={"order_id": oid, "customer_id": cust, "currency": cur,
                                                "amount_minor": amt}))
    with TestClient(gw_main.app) as gateway:
        yield gateway, provider_client


def _setup(gateway):
    assert gateway.post("/api/operators", json={"id": "op-1", "name": "Asha", "permitted_operations": ["REFUND"],
                                                "limit": "10000"}).status_code == 201
    assert gateway.post("/api/orders", json={"id": "ORD-204", "customer_id": "C-17", "amount": "5000"}).status_code == 201
    r = gateway.post("/api/intents", json={"operator_id": "op-1", "customer_id": "C-17", "order_id": "ORD-204",
                                           "amount": "1500.00", "ticket": "Refund ₹1,500 for ORD-204 to C-17"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_end_to_end_lost_response_over_http(services):
    gateway, provider = services
    iid = _setup(gateway)
    provider.post("/v1/faults", json={"kind": "TIMEOUT_AFTER_EXECUTION", "order_id": "ORD-204"})

    bad = gateway.post(f"/api/intents/{iid}/proposals", json={
        "operation": "REFUND", "customer_id": "C-17", "order_id": "ORD-204", "amount": "15000.00"}).json()
    assert bad["decision"] == "REJECT"

    ok = gateway.post(f"/api/intents/{iid}/agent", json={}).json()
    assert ok["extracted"]["amount_minor"] == 150000
    assert ok["result"]["decision"] == "ALLOW"
    assert ok["result"]["intent_state"] == "COMPLETED"  # lost 504 response, found by reconciliation

    again = gateway.post(f"/api/intents/{iid}/proposals", json={
        "operation": "REFUND", "customer_id": "C-17", "order_id": "ORD-204", "amount": "1500.00"}).json()
    assert again["decision"] == "DUPLICATE"
    assert len(provider.get("/v1/ledger").json()) == 1

    timeline = gateway.get(f"/api/intents/{iid}").json()
    assert {"proposals", "attempts", "effects", "reviews", "audit"} <= set(timeline)
    assert gateway.get("/api/audit/verify").json()["ok"] is True
    metrics = gateway.get("/api/metrics").json()
    assert metrics["intents_by_state"] == {"COMPLETED": 1}


def test_review_flow_over_http(services):
    gateway, provider = services
    iid = _setup(gateway)
    provider.post("/v1/faults", json={"kind": "CORRUPT_AMOUNT", "order_id": "ORD-204", "params": {"factor": 2}})
    gateway.post(f"/api/intents/{iid}/proposals", json={
        "operation": "REFUND", "customer_id": "C-17", "order_id": "ORD-204", "amount": "1500.00"})
    cases = gateway.get("/api/reviews").json()
    assert len(cases) == 1 and cases[0]["reason"] == "IRREVERSIBLE_DISCREPANCY"
    r = gateway.post(f"/api/reviews/{cases[0]['id']}/resolve",
                     json={"reviewer_id": "lead", "resolution": "REFUND_RECOVERED_OUT_OF_BAND", "notes": "clawed back"})
    assert r.status_code == 200
    # After remediation the authorized refund is still owed; the gateway retries it under a fresh key.
    assert gateway.get(f"/api/intents/{iid}").json()["intent"]["state"] == "COMPLETED"
    amounts = sorted(t["amount_minor"] for t in provider.get("/v1/ledger").json())
    assert amounts == [150000, 300000]  # the remediated wrong refund stays in the provider's history


def test_unknown_intent_is_404_and_bad_authorization_is_422(services):
    gateway, _ = services
    assert gateway.get("/api/intents/nope").status_code == 404
    gateway.post("/api/operators", json={"id": "op-2", "name": "R", "permitted_operations": ["REFUND"], "limit": "100"})
    gateway.post("/api/orders", json={"id": "ORD-1", "customer_id": "C-1", "amount": "5000"})
    r = gateway.post("/api/intents", json={"operator_id": "op-2", "customer_id": "C-1", "order_id": "ORD-1",
                                           "amount": "500"})
    assert r.status_code == 422  # above the operator's limit


_ = httpx  # the HttpProvider under test is httpx-based
