"""
Fixtures for HTTP tests of the gateway API (docs/API.md).

`api` runs the real gateway app against the real provider app; the provider is reached through the
real HttpProvider adapter over an in-process transport, so no ports are needed. `api_inprocess`
embeds the simulator in the gateway (needed for /api/dev/* endpoints). Demo users are seeded with
DEMO_PASSWORD; the LLM is forced offline so tests never call a real model.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

PASSWORD = "intentguard-test-password"
EMAILS = {"op-asha": "asha@intentguard.test", "op-ravi": "ravi@intentguard.test",
          "rev-meera": "meera@intentguard.test", "admin": "admin@intentguard.test"}
WEBHOOK_SECRET = "whsec_test_secret_0123456789"


@dataclass
class Api:
    client: TestClient
    provider: Any  # TestClient for provider_api (http mode) or None
    sim: Any  # PaymentSimulator (inprocess mode) or the provider module's simulator
    app: Any

    @property
    def guard(self) -> Any:
        return self.app.state.guard

    def login(self, user: str = "op-asha") -> dict[str, str]:
        r = self.client.post("/api/auth/login", json={"email": EMAILS[user], "password": PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def authorize(self, h: dict[str, str], order: str = "ORD-204", customer: str = "C-17", amount: str = "1500.00",
                  ticket: str | None = "Refund ₹1,500 for ORD-204 to C-17", operation: str = "REFUND") -> str:
        r = self.client.post("/api/authorizations", headers=h, json={
            "customer_id": customer, "order_id": order, "operation": operation, "authorized_amount": amount,
            "currency": "INR", "ticket_text": ticket})
        assert r.status_code == 201, r.text
        return r.json()["intent_id"]

    def propose(self, h: dict[str, str], iid: str, **kw: Any) -> Any:
        body = {"operation": "REFUND", "customer_id": "C-17", "order_id": "ORD-204", "amount": "1500.00",
                "currency": "INR", **kw}
        return self.client.post(f"/api/intents/{iid}/proposals", headers=h, json=body)

    def fault(self, kind: str, order_id: str = "ORD-204", **params: Any) -> None:
        times = params.pop("times", 1)
        if self.provider is not None:
            r = self.provider.post("/v1/faults", json={"kind": kind, "order_id": order_id, "times": times,
                                                       "params": params})
            assert r.status_code == 201, r.text
        else:
            from paysim import Fault, FaultKind

            self.sim.inject(Fault(FaultKind(kind), order_id, times, params))


def _configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Any, provider_mode: str) -> Any:
    from gateway_api import settings as settings_mod

    s = settings_mod.settings
    for key, value in {
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'gw.db').as_posix()}", "PAYMENT_PROVIDER": provider_mode,
        "DEMO_SEED": True, "DEMO_PASSWORD": PASSWORD, "SIMULATOR_MODE": True, "JWT_SECRET": "j" * 48,
        "WEBHOOK_SECRET": WEBHOOK_SECRET, "COOKIE_SECURE": False, "WORKER_INTERVAL_S": 3600.0,
        "RATE_LIMIT_PER_MINUTE": 100000, "LOGIN_RATE_LIMIT_PER_MINUTE": 100000,
    }.items():
        monkeypatch.setattr(s, key, value)
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    from gateway_api.security import limiter

    limiter.reset()
    return s


@pytest.fixture
def api(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("PAYSIM_STATE_PATH", str(tmp_path / "paysim.json"))
    monkeypatch.setenv("PAYSIM_SETTLE_DELAY_S", "0")
    monkeypatch.setenv("SIMULATOR_MODE", "true")
    monkeypatch.delenv("PAYSIM_WEBHOOK_URL", raising=False)
    import provider_api.main as provider_main

    provider_main = importlib.reload(provider_main)
    provider_client = TestClient(provider_main.app)
    _configure(monkeypatch, tmp_path, "http")
    import gateway_api.main as gw_main
    import gateway_api.routers.admin as admin_mod
    import gateway_api.seed as seed_mod
    from intentguard.providers.http import HttpProvider

    def register(_sim: Any, oid: str, cust: str, cur: str, amt: int) -> None:
        provider_client.post("/v1/orders", json={"order_id": oid, "customer_id": cust, "currency": cur,
                                                 "amount_minor": amt})

    monkeypatch.setattr(gw_main, "build_provider", lambda: (HttpProvider("http://provider", client=provider_client),
                                                            None))
    monkeypatch.setattr(seed_mod, "register_provider_order", register)
    monkeypatch.setattr(admin_mod, "register_provider_order", register)
    with TestClient(gw_main.app) as client:
        yield Api(client, provider_client, provider_main.sim, gw_main.app)


@pytest.fixture
def api_inprocess(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    _configure(monkeypatch, tmp_path, "inprocess")
    import gateway_api.main as gw_main
    from intentguard.providers.inprocess import InProcessProvider
    from paysim import PaymentSimulator

    sim = PaymentSimulator(state_path=None, default_settle_delay_s=0.0)
    monkeypatch.setattr(gw_main, "build_provider", lambda: (InProcessProvider(sim), sim))
    with TestClient(gw_main.app) as client:
        yield Api(client, None, sim, gw_main.app)
