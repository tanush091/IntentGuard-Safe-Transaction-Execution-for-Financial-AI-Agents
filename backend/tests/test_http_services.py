"""
End to end over HTTP: the gateway API talks to the provider API through the real HttpProvider
(the provider app is mounted in-process, so no ports are needed).
"""

from __future__ import annotations


def test_end_to_end_lost_response_over_http(api):
    h = api.login("op-asha")
    iid = api.authorize(h)
    api.fault("TIMEOUT_AFTER_EXECUTION")

    bad = api.propose(h, iid, amount="15000.00")
    assert bad.status_code == 200  # a decision is not an HTTP error
    assert bad.json()["decision"] == "REJECT" and bad.json()["reason"] == "AMOUNT_EXCEEDS_AUTHORIZATION"
    assert bad.json()["state"] == "AUTHORIZED" and bad.json()["verified"] is False

    ok = api.client.post(f"/api/intents/{iid}/agent", headers=h, json={}).json()
    assert ok["decision"] == "ALLOW" and ok["extraction"]["source"] == "rules"
    detail = api.client.get(f"/api/intents/{iid}", headers=h).json()
    assert detail["state"] == "COMPLETED" and detail["verified"] is True
    assert [e["classification"] for e in detail["effects"]] == ["INTENDED"]
    ledger = api.provider.get("/v1/ledger", params={"order_id": "ORD-204"}).json()
    assert len(ledger) == 1  # the lost response was reconciled, not repeated


def test_review_flow_over_http(api):
    asha, meera = api.login("op-asha"), api.login("rev-meera")
    iid = api.authorize(asha)
    api.fault("CORRUPT_AMOUNT", factor=2)  # settles immediately (delay 0): cannot be cancelled
    r = api.propose(asha, iid).json()
    assert r["state"] == "ESCALATED"
    cases = api.client.get("/api/review-cases", headers=meera).json()["items"]
    assert len(cases) == 1 and cases[0]["reason"] == "IRREVERSIBLE_DISCREPANCY"
    assert cases[0]["discrepancy_amount"] == "1500.00" and cases[0]["case_id"].startswith("RC-")

    forbidden = api.client.post(f"/api/review-cases/{cases[0]['case_id']}/resolve", headers=asha,
                                json={"resolution": "REFUND_RECOVERED_OUT_OF_BAND"})
    assert forbidden.status_code == 403  # operators cannot resolve review cases

    done = api.client.post(f"/api/review-cases/{cases[0]['case_id']}/resolve", headers=meera,
                           json={"resolution": "REFUND_RECOVERED_OUT_OF_BAND", "note": "clawed back"})
    assert done.status_code == 200 and done.json()["intent_state"] == "COMPLETED"
    amounts = sorted(t["amount_minor"] for t in api.provider.get("/v1/ledger").json())
    assert amounts == [150000, 300000]  # the remediated wrong refund stays in the provider's history


def test_unknown_intent_is_404_and_bad_authorization_is_422(api):
    ravi = api.login("op-ravi")
    r = api.client.get("/api/intents/INT-9999", headers=ravi)
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    r = api.client.post("/api/authorizations", headers=ravi, json={
        "customer_id": "C-17", "order_id": "ORD-240", "authorized_amount": "6000.00"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "OPERATOR_LIMIT_EXCEEDED"
    assert r.json()["error"]["request_id"].startswith("req_")
