"""Role and scope enforcement (docs/SECURITY.md section 4, docs/API.md contract rule 1)."""

from __future__ import annotations

import pytest


def _agent_token(api, admin, **scope):
    r = api.client.post("/api/admin/service-tokens", headers=admin, json={"principal_id": "agent-support", **scope})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("user, method, path, body, allowed", [
    ("op-asha", "post", "/api/review-cases/RC-1/resolve", {"resolution": "OTHER"}, False),
    ("op-asha", "get", "/api/audit/verify", None, False),
    ("op-asha", "get", "/api/admin/users", None, False),
    ("op-asha", "post", "/api/reconciliation/runs?wait=true", None, False),
    ("rev-meera", "get", "/api/audit/verify", None, True),
    ("rev-meera", "post", "/api/reconciliation/runs?wait=true", None, True),
    ("rev-meera", "get", "/api/admin/policies", None, False),
    ("admin", "get", "/api/admin/policies", None, True),
])
def test_role_matrix(api, user, method, path, body, allowed):
    h = api.login(user)
    r = getattr(api.client, method)(path, headers=h, **({"json": body} if body is not None else {}))
    if allowed:
        assert r.status_code in (200, 202), r.text
    else:
        assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"


def test_agent_token_is_scoped_to_its_intent(api):
    asha, admin = api.login("op-asha"), api.login("admin")
    mine = api.authorize(asha)
    other = api.authorize(asha, order="ORD-311", amount="1000.00", ticket=None)
    tok = _agent_token(api, admin, intent_ids=[mine], ttl_s=3600)
    assert tok["expires_in"] == 300  # agent tokens are capped at 5 minutes
    agent = {"Authorization": f"Bearer {tok['token']}"}

    assert api.propose(agent, mine).json()["decision"] == "ALLOW"
    r = api.propose(agent, other, order_id="ORD-311", amount="1000.00")
    assert r.status_code == 403
    assert api.client.get(f"/api/intents/{other}", headers=agent).status_code == 403
    assert [i["intent_id"] for i in api.client.get("/api/intents", headers=agent).json()["items"]] == [mine]
    for path, body in [("/api/authorizations", {"customer_id": "C-17", "order_id": "ORD-204",
                                                "authorized_amount": "10.00"}),
                       (f"/api/intents/{mine}/cancel", {}), (f"/api/exceptions/{mine}/investigate", None)]:
        assert api.client.post(path, headers=agent, json=body).status_code == 403, path
    assert api.client.get("/api/dev/ledger", headers=agent).status_code == 403


def test_revoked_agent_token_stops_working(api):
    asha, admin = api.login("op-asha"), api.login("admin")
    iid = api.authorize(asha)
    tok = _agent_token(api, admin, intent_ids=[iid])
    agent = {"Authorization": f"Bearer {tok['token']}"}
    assert api.client.get(f"/api/intents/{iid}", headers=agent).status_code == 200
    assert api.client.delete(f"/api/admin/service-tokens/{tok['jti']}", headers=admin).status_code == 200
    assert api.client.get(f"/api/intents/{iid}", headers=agent).status_code == 401


def test_customer_scoped_agent_token(api):
    asha, admin = api.login("op-asha"), api.login("admin")
    c17 = api.authorize(asha)
    c71 = api.authorize(asha, order="ORD-2041", customer="C-71", amount="1000.00", ticket=None)
    agent = {"Authorization": f"Bearer {_agent_token(api, admin, customer_ids=['C-17'])['token']}"}
    assert api.client.get(f"/api/intents/{c17}", headers=agent).status_code == 200
    assert api.client.get(f"/api/intents/{c71}", headers=agent).status_code == 403


def test_agents_cannot_log_in_and_must_be_scoped(api):
    admin = api.login("admin")
    r = api.client.post("/api/admin/service-tokens", headers=admin, json={"principal_id": "agent-support"})
    assert r.status_code == 422  # no scope
    r = api.client.post("/api/admin/service-tokens", headers=admin, json={"principal_id": "op-asha",
                                                                         "intent_ids": []})
    assert r.status_code == 422


def test_separation_of_duties_over_http(api):
    asha, meera, admin = api.login("op-asha"), api.login("rev-meera"), api.login("admin")
    iid = api.authorize(meera)  # the reviewer authorizes this one herself
    api.fault("CORRUPT_AMOUNT", factor=2)
    api.propose(asha, iid)
    case = api.client.get("/api/review-cases", headers=meera).json()["items"][0]["case_id"]
    r = api.client.post(f"/api/review-cases/{case}/resolve", headers=meera, json={"resolution": "WRITTEN_OFF"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "SEPARATION_OF_DUTIES"
    ok = api.client.post(f"/api/review-cases/{case}/resolve", headers=admin, json={"resolution": "WRITTEN_OFF"})
    assert ok.status_code == 200 and ok.json()["intent_state"] == "CLOSED"
