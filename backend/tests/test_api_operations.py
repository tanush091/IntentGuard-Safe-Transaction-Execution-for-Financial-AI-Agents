"""
Operational endpoints: reconciliation matching runs and mismatches, policies (kill switch, limits),
the agent endpoint's output validation, simulator-only endpoints, metrics, providers, orders.
"""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from intentguard.agents import llm as llm_mod
from paysim import TxKind


def _intent_states(api, h):
    return {i["intent_id"]: i["state"] for i in api.client.get("/api/intents", headers=h).json()["items"]}


# ------------------------------------------------------------ matching runs


def test_matching_run_reports_mismatches_without_changing_anything(api_inprocess):
    api = api_inprocess
    asha, meera = api.login(), api.login("rev-meera")
    clean = api.authorize(asha)
    api.propose(asha, clean)
    wrong = api.authorize(asha, order="ORD-311", amount="1000.00", ticket=None)
    api.fault("CORRUPT_AMOUNT", order_id="ORD-311", factor=2)  # completes at once: irreversible
    api.propose(asha, wrong, order_id="ORD-311", amount="1000.00")
    api.sim.create(TxKind.REFUND, order_id="ORD-240", customer_id="C-17", amount_minor=50_00, currency="INR")
    before = _intent_states(api, asha)

    run = api.client.post("/api/reconciliation/runs?wait=true", headers=meera).json()
    assert run["status"] == "finished" and run["mismatches_found"] == 2
    kinds = {m["kind"]: m for m in api.client.get("/api/reconciliation/mismatches", headers=meera).json()["items"]}
    assert set(kinds) == {"MISSING", "AMOUNT"} and kinds["AMOUNT"]["intent_id"] == wrong
    assert kinds["MISSING"]["order_id"] == "ORD-240"
    assert _intent_states(api, asha) == before  # a matching run never changes money or state

    again = api.client.post("/api/reconciliation/runs?wait=true", headers=meera).json()
    assert again["mismatches_found"] == 0  # open mismatches are not duplicated
    runs = api.client.get("/api/reconciliation/runs", headers=meera, params={"kind": "MATCHING"}).json()["items"]
    assert len(runs) == 2

    mm = kinds["MISSING"]["mismatch_id"]
    assert api.client.post(f"/api/reconciliation/mismatches/{mm}/resolve", headers=asha,
                           json={"note": "x"}).status_code == 403
    r = api.client.post(f"/api/reconciliation/mismatches/{mm}/resolve", headers=meera, json={"note": "out of band"})
    assert r.json()["status"] == "RESOLVED"


def test_matching_run_detects_a_duplicate_left_by_an_ablated_gateway(api_inprocess):
    api = api_inprocess
    asha, meera = api.login(), api.login("rev-meera")
    api.guard.cfg = api.guard.cfg.without(effect_dedup=False, stable_idempotency_key=False)
    iid = api.authorize(asha, amount="1000.00", ticket=None)
    api.propose(asha, iid, amount="1000.00")
    api.propose(asha, iid, amount="1000.00")  # the ablated gate lets a second refund through
    run = api.client.post("/api/reconciliation/runs?wait=true", headers=meera).json()
    kinds = [m["kind"] for m in api.client.get("/api/reconciliation/mismatches", headers=meera).json()["items"]]
    assert run["mismatches_found"] >= 1 and "DUPLICATE" in kinds


# ------------------------------------------------------------------ policies


def test_kill_switch_and_policy_limit_through_the_api(api):
    asha, admin = api.login(), api.login("admin")
    iid = api.authorize(asha)
    p = api.client.put("/api/admin/policies", headers=admin, json={"kill_switch": True}).json()
    assert p["kill_switch"] is True
    r = api.propose(asha, iid).json()
    assert r["decision"] == "HOLD_FOR_REVIEW" and "KILL_SWITCH" in r["reasons"]
    assert api.provider.get("/v1/ledger").json() == []
    api.client.put("/api/admin/policies", headers=admin, json={"kill_switch": False, "max_amount": "1000.00"})
    r = api.client.post("/api/authorizations", headers=asha, json={
        "customer_id": "C-17", "order_id": "ORD-204", "authorized_amount": "1200.00"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "POLICY_LIMIT_EXCEEDED"
    p = api.client.put("/api/admin/policies", headers=admin, json={"clear_max_amount": True,
                                                                  "attempt_budget": 5}).json()
    assert p["max_amount"] is None and p["attempt_budget"] == 5
    audit = api.client.get("/api/audit", headers=admin, params={"kind": "policy.updated"}).json()["items"]
    assert {e["payload"]["key"] for e in audit} >= {"kill_switch", "max_amount_minor", "attempt_budget"}


# ------------------------------------------------------------- agent output


def test_malformed_llm_output_is_rejected_not_repaired(api, monkeypatch):
    h = api.login()
    iid = api.authorize(h)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_mod.LLMClient, "complete_json",
                        lambda self, system, user: ('{"operation": "REFUND", "order_id": "ORD-204"}', {}))
    r = api.client.post(f"/api/intents/{iid}/agent", headers=h, json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_AGENT_OUTPUT"
    assert api.client.get(f"/api/intents/{iid}", headers=h).json()["proposals"] == []


# ------------------------------------------------------------ simulator mode


def test_simulator_endpoints_disappear_when_simulator_mode_is_off(api_inprocess, monkeypatch):
    api = api_inprocess
    h = api.login()
    assert api.client.post("/api/dev/faults", headers=h, json={"kind": "OUTAGE"}).status_code == 201
    monkeypatch.setattr(api.app.state.settings, "SIMULATOR_MODE", False)
    r = api.client.post("/api/dev/faults", headers=h, json={"kind": "OUTAGE"})
    assert r.status_code == 404 and "SIMULATOR_MODE" in r.json()["error"]["message"]


def test_provider_fault_endpoint_needs_simulator_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("PAYSIM_STATE_PATH", str(tmp_path / "p.json"))
    monkeypatch.setenv("SIMULATOR_MODE", "false")
    import provider_api.main as provider_main

    provider_main = importlib.reload(provider_main)
    client = TestClient(provider_main.app)
    assert client.post("/v1/faults", json={"kind": "OUTAGE"}).status_code == 404
    assert client.get("/health").json()["simulator_mode"] is False


# --------------------------------------------------------- metrics, admin


def test_metrics_summary(api):
    asha = api.login()
    ok = api.authorize(asha)
    api.propose(asha, ok)
    api.propose(asha, ok)  # duplicate
    blocked = api.authorize(asha, amount="100.00", ticket=None)
    api.propose(asha, blocked, amount="999.00")
    m = api.client.get("/api/metrics/summary", headers=asha, params={"window": "24h"}).json()
    assert m["intents"]["total"] == 2 and m["intents"]["completed"] == 1 and m["intents"]["blocked"] == 1
    assert m["duplicates_suppressed"] == 1 and m["human_intervention_rate"] == 0.0
    assert m["median_time_to_verified_s"] is not None and "definitions" in m
    assert api.client.get("/api/metrics/summary", headers=asha, params={"window": "1y"}).status_code == 422


def test_provider_config_secret_is_write_only_and_orders(api):
    admin = api.login("admin")
    r = api.client.put("/api/admin/providers/paysim", headers=admin, json={"webhook_secret": "s" * 32})
    assert r.status_code == 200
    body = r.json()["items"][0]
    assert body["webhook_secret_set"] is True and "s" * 32 not in r.text
    orders = api.client.get("/api/orders", headers=api.login()).json()["items"]
    assert {o["order_id"] for o in orders} == {"ORD-204", "ORD-240", "ORD-2041", "ORD-311"}
    assert api.client.get("/api/ready").json()["status"] == "ready"
