"""
The REST contract in docs/API.md: error envelope, decisions as HTTP 200, pagination, client
Idempotency-Key replay, strict request bodies, ISO timestamps, prefixed identifiers, and the rule
that the derived provider idempotency key is never exposed.
"""

from __future__ import annotations

import json
import re

# Every path documented in docs/API.md (sections 2-12), relative to /api.
DOCUMENTED = [
    ("post", "/auth/login"), ("post", "/auth/refresh"), ("post", "/auth/logout"), ("get", "/auth/me"),
    ("post", "/authorizations"), ("get", "/intents"), ("get", "/intents/{intent_id}"),
    ("get", "/intents/{intent_id}/timeline"), ("get", "/intents/{intent_id}/history"),
    ("post", "/intents/{intent_id}/cancel"), ("post", "/intents/{intent_id}/proposals"),
    ("post", "/intents/{intent_id}/agent"), ("post", "/attempts/{attempt_id}/reconcile"),
    ("get", "/reconciliation/runs"), ("post", "/reconciliation/runs"), ("get", "/reconciliation/mismatches"),
    ("get", "/exceptions"), ("post", "/exceptions/{intent_id}/investigate"),
    ("get", "/investigations/{investigation_id}"), ("get", "/review-cases"), ("get", "/review-cases/{case_id}"),
    ("post", "/review-cases/{case_id}/resolve"), ("post", "/webhooks/{provider}"), ("get", "/audit"),
    ("get", "/audit/verify"), ("get", "/metrics/summary"), ("get", "/experiments/latest"),
    ("get", "/admin/users"), ("post", "/admin/users"), ("patch", "/admin/users/{user_id}"),
    ("post", "/admin/service-tokens"), ("get", "/admin/policies"), ("put", "/admin/policies"),
    ("get", "/admin/providers"), ("put", "/admin/providers/{name}"), ("get", "/health"), ("get", "/ready"),
    ("post", "/dev/faults"),
]


def test_every_documented_endpoint_exists_in_the_openapi_schema(api):
    paths = api.client.get("/openapi.json").json()["paths"]
    missing = [(m, p) for m, p in DOCUMENTED if m not in paths.get("/api" + p, {})]
    assert not missing, missing


def test_error_envelope(api):
    h = api.login()
    r = api.client.get("/api/intents/INT-404", headers={**h, "X-Request-ID": "req_contract_test"})
    assert r.status_code == 404
    err = r.json()["error"]
    assert set(err) == {"code", "message", "details", "request_id"} and err["request_id"] == "req_contract_test"
    assert r.headers["x-request-id"] == "req_contract_test"


def test_malformed_json_is_400_and_unknown_fields_are_422(api):
    h = api.login()
    r = api.client.post("/api/authorizations", headers={**h, "Content-Type": "application/json"}, content=b"{oops")
    assert r.status_code == 400 and r.json()["error"]["code"] == "MALFORMED_REQUEST"
    r = api.client.post("/api/authorizations", headers=h, json={
        "customer_id": "C-17", "order_id": "ORD-204", "authorized_amount": "10.00", "approve_myself": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    r = api.client.post("/api/authorizations", headers=h, json={
        "customer_id": "C-17", "order_id": "ORD-204", "authorized_amount": "-5"})
    assert r.status_code == 422


def test_decisions_are_http_200_with_reason_codes(api):
    h = api.login()
    iid = api.authorize(h)
    for kw, decision, reason in [({"order_id": "ORD-240"}, "REJECT", "ORDER_MISMATCH"),
                                 ({"customer_id": "C-71"}, "REJECT", "CUSTOMER_MISMATCH"),
                                 ({"amount": "15.00"}, "REJECT", "AMOUNT_BELOW_AUTHORIZATION"),
                                 ({}, "ALLOW", None), ({}, "DUPLICATE", "ALREADY_COMPLETED")]:
        r = api.propose(h, iid, **kw)
        assert r.status_code == 200
        assert (r.json()["decision"], r.json()["reason"]) == (decision, reason)
        assert r.json()["proposal_id"].startswith("PRP-")


def test_pagination_cursor(api):
    h = api.login()
    ids = [api.authorize(h, amount=f"{100 + i}.00", ticket=None) for i in range(5)]
    seen, cursor = [], None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = api.client.get("/api/intents", headers=h, params=params).json()
        assert len(page["items"]) <= 2
        seen += [i["intent_id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == list(reversed(ids))  # newest first, nothing skipped or repeated
    assert api.client.get("/api/intents", headers=h, params={"limit": 500}).status_code == 422
    assert api.client.get("/api/intents", headers=h, params={"cursor": "!!"}).status_code == 400


def test_idempotency_key_replays_the_original_response(api):
    h = api.login()
    body = {"customer_id": "C-17", "order_id": "ORD-204", "authorized_amount": "100.00"}
    k = {**h, "Idempotency-Key": "create-intent-1"}
    a = api.client.post("/api/authorizations", headers=k, json=body)
    b = api.client.post("/api/authorizations", headers=k, json=body)
    assert a.status_code == b.status_code == 201 and a.json() == b.json()
    assert b.headers.get("idempotent-replay") == "true"
    assert len(api.client.get("/api/intents", headers=h).json()["items"]) == 1
    c = api.client.post("/api/authorizations", headers=k, json={**body, "authorized_amount": "200.00"})
    assert c.status_code == 422 and c.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSE"


def test_provider_idempotency_key_is_never_exposed(api):
    h, meera = api.login(), api.login("rev-meera")
    iid = api.authorize(h)
    api.propose(h, iid)
    pages = [api.client.get(p, headers=meera).text for p in (
        f"/api/intents/{iid}", f"/api/intents/{iid}/history", f"/api/intents/{iid}/timeline",
        f"/api/audit?intent_id={iid}")]
    for text in pages:
        assert f"ig-{iid}" not in text
    assert "[redacted]" in pages[3]  # attempt.reserved carries the key in the stored payload


def test_timestamps_are_iso8601_and_ids_are_prefixed(api):
    h = api.login()
    iid = api.authorize(h)
    assert re.fullmatch(r"INT-\d+", iid)
    api.propose(h, iid)
    detail = api.client.get(f"/api/intents/{iid}", headers=h).json()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", detail["created_at"])
    assert detail["attempts"][0]["attempt_id"] == "ATT-001" and detail["effects"][0]["effect_id"].startswith("EFF-")
    assert detail["authorized_amount"] == "1500.00" and detail["currency"] == "INR"


def test_unknown_states_are_never_reported_as_failed(api):
    h = api.login()
    iid = api.authorize(h)
    api.fault("TIMEOUT_AFTER_EXECUTION")
    api.fault("LOOKUP_OUTAGE", times=-1)
    r = api.propose(h, iid).json()
    assert r["decision"] == "ALLOW" and r["state"] == "UNKNOWN" and r["verified"] is False
    assert json.dumps(r).find("FAILED") == -1


def test_security_headers(api):
    r = api.client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in r.headers["content-security-policy"]
