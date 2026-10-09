"""
Provider webhooks (docs/API.md section 8, docs/SECURITY.md section 7, ADR-021, TEST_PLAN section 11).
Events are delivered by paysim's real WebhookEmitter into the gateway app.
"""

from __future__ import annotations

import json
import time

from paysim.webhooks import WebhookEmitter, sign
from tests.api_support import WEBHOOK_SECRET


def _emitter(api, delivered=None):
    def post(_url, body, headers):
        if delivered is not None:
            delivered.append(body)
        return api.client.post("/api/webhooks/paysim", content=body, headers=headers).status_code
    return WebhookEmitter(api.sim, "http://gateway/api/webhooks/paysim", WEBHOOK_SECRET, post=post)


def _post_event(api, event, *, secret=WEBHOOK_SECRET, ts=None):
    body = json.dumps(event).encode()
    ts = int(time.time()) if ts is None else ts
    return api.client.post("/api/webhooks/paysim", content=body,
                           headers={"Content-Type": "application/json", "Paysim-Signature": sign(secret, ts, body)})


def test_webhook_resolves_a_lost_response_hidden_from_search(api):
    h = api.login()
    iid = api.authorize(h)
    api.fault("TIMEOUT_AFTER_EXECUTION")
    api.fault("DELAYED_VISIBILITY", lag_s=600)  # search will not show it for 10 minutes
    assert api.propose(h, iid).json()["state"] == "UNKNOWN"
    _emitter(api).step()
    detail = api.client.get(f"/api/intents/{iid}", headers=h).json()
    assert detail["state"] == "COMPLETED"  # the event was a hint; the gateway re-fetched the transaction
    hist = api.client.get(f"/api/intents/{iid}/history", headers=h).json()
    assert [e["outcome"] for e in hist["webhook_events"]] == ["absorbed"]
    assert len(api.provider.get("/v1/ledger").json()) == 1


def test_bad_signature_and_stale_timestamp_are_rejected(api):
    event = {"id": "evt_1", "type": "refund.completed", "created": time.time(), "sequence": 1,
             "data": {"object": {"id": "rf_x", "kind": "REFUND", "status": "COMPLETED", "metadata": {}}}}
    r = _post_event(api, event, secret="wrong-secret-0123456789")
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_SIGNATURE"
    r = _post_event(api, event, ts=int(time.time()) - 3600)
    assert r.status_code == 400 and r.json()["error"]["code"] == "STALE_EVENT"
    r = api.client.post("/api/webhooks/paysim", content=json.dumps(event).encode())
    assert r.status_code == 400  # unsigned


def test_duplicate_and_delayed_deliveries_are_safe(api):
    h = api.login()
    iid = api.authorize(h)
    api.fault("WEBHOOK_DUPLICATE")
    api.propose(h, iid)
    delivered = []
    _emitter(api, delivered).step()
    assert len(delivered) == 2 and delivered[0] == delivered[1]
    events = api.client.get(f"/api/intents/{iid}/history", headers=h).json()["webhook_events"]
    assert len(events) == 1 and events[0]["deliveries"] == 2
    assert api.client.get(f"/api/intents/{iid}", headers=h).json()["state"] == "COMPLETED"


def test_out_of_order_events_converge_on_the_provider_state(api):
    h = api.login()
    iid = api.authorize(h)
    api.propose(h, iid)
    [tx] = api.provider.get("/v1/ledger").json()
    obj = {**tx, "status": "PENDING"}
    newer = {"id": f"evt_{tx['id']}_completed", "type": "refund.completed", "created": time.time(), "sequence": 2,
             "data": {"object": tx}}
    older = {"id": f"evt_{tx['id']}_pending", "type": "refund.pending", "created": time.time() - 5, "sequence": 1,
             "data": {"object": obj}}
    assert _post_event(api, newer).json()["status"] == "accepted"
    assert _post_event(api, older).json()["status"] == "accepted"  # arrives late
    assert api.client.get(f"/api/intents/{iid}", headers=h).json()["state"] == "COMPLETED"


def test_event_for_an_unknown_intent_becomes_a_mismatch(api):
    meera = api.login("rev-meera")
    api.provider.post("/v1/refunds", json={"order_id": "ORD-311", "customer_id": "C-17", "amount_minor": 50000})
    _emitter(api).step()
    items = api.client.get("/api/reconciliation/mismatches", headers=meera).json()["items"]
    assert [m["kind"] for m in items] == ["MISSING"] and items[0]["details"]["source"] == "webhook"


def test_emitter_delay_fault_delivers_later(api):
    h = api.login()
    iid = api.authorize(h)
    api.fault("WEBHOOK_DELAY", delay_s=0.3)
    api.propose(h, iid)
    delivered = []
    em = _emitter(api, delivered)
    em.step()
    assert delivered == []
    time.sleep(0.4)
    em.deliver_due()
    assert len(delivered) == 1
