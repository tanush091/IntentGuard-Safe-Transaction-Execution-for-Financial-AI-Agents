"""
Mock payment provider HTTP service backed by paysim.

A lost response is reported as HTTP 504, which the gateway treats exactly like a
client-side timeout: it cannot tell whether the operation executed. State is
persisted to PAYSIM_STATE_PATH so the provider survives restarts.

Fault injection (/v1/faults) exists only when SIMULATOR_MODE=true. When
PAYSIM_WEBHOOK_URL and a secret (PAYSIM_WEBHOOK_SECRET or WEBHOOK_SECRET) are set,
signed status-change events are delivered to the gateway.
"""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from intentguard.envfile import load_env

from paysim import (
    Fault,
    FaultKind,
    Order,
    PaymentSimulator,
    SimConflict,
    SimError,
    SimNotFound,
    SimRejected,
    SimTimeout,
    SimUnavailable,
    TxKind,
)

from paysim.webhooks import WebhookEmitter

load_env()

sim = PaymentSimulator(
    default_settle_delay_s=float(os.getenv("PAYSIM_SETTLE_DELAY_S", "3")),
    state_path=os.getenv("PAYSIM_STATE_PATH", "paysim_state.json"),
)
SIMULATOR_MODE = os.getenv("SIMULATOR_MODE", "false").strip().lower() in ("1", "true", "yes")
WEBHOOK_URL = os.getenv("PAYSIM_WEBHOOK_URL", "").strip()
WEBHOOK_SECRET = (os.getenv("PAYSIM_WEBHOOK_SECRET") or os.getenv("WEBHOOK_SECRET") or "").strip()


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    emitter = None
    if WEBHOOK_URL and WEBHOOK_SECRET:
        emitter = WebhookEmitter(sim, WEBHOOK_URL, WEBHOOK_SECRET)
        threading.Thread(target=emitter.run, name="paysim-webhooks", daemon=True).start()
    yield
    if emitter is not None:
        emitter.stop()


app = FastAPI(
    title="Mock Payment Provider (paysim)",
    version="3.0.0",
    description="Simulated provider. Never connects to real accounts or real money.",
    lifespan=lifespan,
)


def simulator_only() -> None:
    if not SIMULATOR_MODE:
        raise HTTPException(404, {"code": "not_found", "message": "fault injection is disabled (SIMULATOR_MODE=false)"})


class OrderIn(BaseModel):
    order_id: str
    customer_id: str
    currency: str = "INR"
    amount_minor: int = Field(gt=0)


class CreateIn(BaseModel):
    order_id: str
    customer_id: str
    amount_minor: int
    currency: str = "INR"
    metadata: dict[str, Any] = Field(default_factory=dict)


class FaultIn(BaseModel):
    kind: FaultKind
    order_id: str | None = None
    times: int = 1
    params: dict[str, Any] = Field(default_factory=dict)


def _raise(exc: SimError) -> None:
    body = {"code": exc.code, "message": str(exc)}
    if isinstance(exc, SimTimeout):
        raise HTTPException(504, body)
    if isinstance(exc, SimUnavailable):
        raise HTTPException(503, body)
    if isinstance(exc, SimNotFound):
        raise HTTPException(404, body)
    if isinstance(exc, SimConflict):
        raise HTTPException(409, body)
    if isinstance(exc, SimRejected):
        raise HTTPException(422, body)
    raise HTTPException(500, body)


def _create(kind: TxKind, body: CreateIn, key: str | None) -> dict[str, Any]:
    try:
        tx = sim.create(kind, order_id=body.order_id, customer_id=body.customer_id, amount_minor=body.amount_minor,
                        currency=body.currency, idempotency_key=key, metadata=body.metadata)
    except SimError as exc:
        _raise(exc)
    return tx.public()


def _get(tx_id: str, kind: TxKind) -> dict[str, Any]:
    try:
        tx = sim.get(tx_id)
    except SimError as exc:
        _raise(exc)
    if tx.kind != kind:
        raise HTTPException(404, {"code": "not_found", "message": f"{tx_id} is not a {kind}"})
    return tx.public()


def _list(order_id: str, kind: TxKind) -> list[dict[str, Any]]:
    try:
        return [t.public() for t in sim.list_by_order(order_id, kind)]
    except SimError as exc:
        _raise(exc)
        return []


def _cancel(tx_id: str, kind: TxKind) -> dict[str, Any]:
    _get(tx_id, kind)
    try:
        return sim.cancel(tx_id).public()
    except SimError as exc:
        _raise(exc)
        return {}


@app.get("/health", tags=["system"])
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "mock-payment-provider", "simulation": True,
            "simulator_mode": SIMULATOR_MODE, "webhooks": bool(WEBHOOK_URL and WEBHOOK_SECRET), **sim.stats}


@app.post("/v1/orders", tags=["setup"], status_code=201)
def add_order(body: OrderIn) -> dict[str, str]:
    sim.add_order(Order(body.order_id, body.customer_id, body.currency.upper(), body.amount_minor))
    return {"order_id": body.order_id}


@app.post("/v1/refunds", tags=["refunds"], status_code=201)
def create_refund(body: CreateIn, idempotency_key: str | None = Header(default=None)) -> dict[str, Any]:
    return _create(TxKind.REFUND, body, idempotency_key)


@app.get("/v1/refunds", tags=["refunds"])
def list_refunds(order_id: str = Query(...)) -> list[dict[str, Any]]:
    return _list(order_id, TxKind.REFUND)


@app.get("/v1/refunds/{tx_id}", tags=["refunds"])
def get_refund(tx_id: str) -> dict[str, Any]:
    return _get(tx_id, TxKind.REFUND)


@app.post("/v1/refunds/{tx_id}/cancel", tags=["refunds"])
def cancel_refund(tx_id: str) -> dict[str, Any]:
    return _cancel(tx_id, TxKind.REFUND)


@app.post("/v1/authorizations", tags=["authorizations"], status_code=201)
def create_authorization(body: CreateIn, idempotency_key: str | None = Header(default=None)) -> dict[str, Any]:
    return _create(TxKind.AUTHORIZATION, body, idempotency_key)


@app.get("/v1/authorizations", tags=["authorizations"])
def list_authorizations(order_id: str = Query(...)) -> list[dict[str, Any]]:
    return _list(order_id, TxKind.AUTHORIZATION)


@app.get("/v1/authorizations/{tx_id}", tags=["authorizations"])
def get_authorization(tx_id: str) -> dict[str, Any]:
    return _get(tx_id, TxKind.AUTHORIZATION)


@app.post("/v1/authorizations/{tx_id}/void", tags=["authorizations"])
def void_authorization(tx_id: str) -> dict[str, Any]:
    return _cancel(tx_id, TxKind.AUTHORIZATION)


@app.get("/v1/faults", tags=["faults"], dependencies=[Depends(simulator_only)])
def list_faults() -> list[dict[str, Any]]:
    return [{"kind": f.kind.value, "order_id": f.order_id, "times": f.times, "params": f.params} for f in sim.faults()]


@app.post("/v1/faults", tags=["faults"], status_code=201, dependencies=[Depends(simulator_only)])
def inject_fault(body: FaultIn) -> dict[str, str]:
    sim.inject(Fault(body.kind, body.order_id, body.times, body.params))
    return {"kind": body.kind.value}


@app.delete("/v1/faults", tags=["faults"], dependencies=[Depends(simulator_only)])
def clear_faults() -> dict[str, str]:
    sim.clear_faults()
    return {"status": "cleared"}


@app.get("/v1/ledger", tags=["evaluation"])
def ledger(order_id: str | None = None) -> list[dict[str, Any]]:
    """Ground truth: every transaction, ignoring search visibility. For evaluation and demos."""
    return [t.public() for t in sim.all_transactions() if order_id is None or t.order_id == order_id]
