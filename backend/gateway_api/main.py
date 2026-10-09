"""
IntentGuard gateway HTTP service.

The agent-facing surface is POST /api/intents/{id}/proposals (structured) and
POST /api/intents/{id}/agent (ticket -> agent -> proposal). Neither can reach the
payment provider directly; only the engine can.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from gateway_api.schemas import (
    AgentRunIn,
    AgentRunOut,
    IntentIn,
    OperatorIn,
    OperatorPatch,
    OrderIn,
    ProposalIn,
    ResolveIn,
    RevokeIn,
    SubmitOut,
)
from gateway_api.settings import settings
from intentguard import audit
from intentguard.agents import ExtractionError, LLMError, LLMExtractor, LLMSettings, extract
from intentguard.checks import Proposal
from intentguard.clock import SystemClock
from intentguard.db import init_schema, make_engine, make_session_factory
from intentguard.domain import IllegalTransition
from intentguard.engine import AuthorizationError, ConflictError, IntentGuard, NotFound, SubmitResult
from intentguard.models import Attempt, AuditEvent, Effect, Intent, Operator, Order, ProposalRecord, ReviewCase
from intentguard.money import fmt, to_minor

log = logging.getLogger("intentguard.gateway")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

DEMO_OPERATORS = [
    ("op-asha", "Asha (support lead)", ["REFUND", "PAYMENT_AUTHORIZATION"], "50000"),
    ("op-ravi", "Ravi (support agent)", ["REFUND"], "5000"),
]
DEMO_ORDERS = [  # near-miss IDs on purpose: ORD-204 / ORD-240 / ORD-2041
    ("ORD-204", "C-17", "INR", "5000"),
    ("ORD-240", "C-17", "INR", "12000"),
    ("ORD-2041", "C-71", "INR", "20000"),
    ("ORD-311", "C-17", "INR", "8000"),
]


def build_provider() -> tuple[Any, Any]:
    if settings.PAYMENT_PROVIDER == "inprocess":
        from intentguard.providers.inprocess import InProcessProvider
        from paysim import PaymentSimulator

        sim = PaymentSimulator(state_path="paysim_state.json")
        return InProcessProvider(sim), sim
    from intentguard.providers.http import HttpProvider

    return HttpProvider(settings.PAYMENT_SERVICE_URL, timeout_s=settings.PROVIDER_TIMEOUT_S), None


def seed_demo(guard: IntentGuard, sim: Any) -> None:
    with guard.session() as s:
        if s.scalar(select(func.count()).select_from(Operator)):
            return
    for oid, name, ops, limit in DEMO_OPERATORS:
        guard.upsert_operator(oid, name, ops, to_minor(limit, "INR"))
    for order_id, cust, cur, amount in DEMO_ORDERS:
        minor = to_minor(amount, cur)
        guard.upsert_order(order_id, cust, cur, minor)
        seed_provider_order(sim, order_id, cust, cur, minor)
    log.info("Seeded demo operators and orders")


def seed_provider_order(sim: Any, order_id: str, customer_id: str, currency: str, amount_minor: int) -> None:
    if sim is not None:
        from paysim import Order as SimOrder

        sim.add_order(SimOrder(order_id, customer_id, currency, amount_minor))
        return
    try:
        httpx.post(f"{settings.PAYMENT_SERVICE_URL}/v1/orders", timeout=5,
                   json={"order_id": order_id, "customer_id": customer_id, "currency": currency,
                         "amount_minor": amount_minor}).raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Could not register order %s with the provider: %s", order_id, exc)


async def worker_loop(guard: IntentGuard) -> None:
    while True:
        try:
            n = await asyncio.to_thread(guard.tick)
            if n:
                log.info("worker processed %d intent(s)", n)
        except Exception:  # noqa: BLE001 - the worker must survive individual failures
            log.exception("worker tick failed")
        await asyncio.sleep(settings.WORKER_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    engine = make_engine(settings.DATABASE_URL)
    init_schema(engine)
    provider, sim = build_provider()
    guard = IntentGuard(make_session_factory(engine), provider, SystemClock(), settings.protocol())
    app.state.guard, app.state.sim = guard, sim
    if settings.DEMO_SEED:
        seed_demo(guard, sim)
    recovered = await asyncio.to_thread(guard.startup_recovery)
    log.info("startup recovery: %d intent(s) had orphaned attempts", recovered)
    task = asyncio.create_task(worker_loop(guard))
    yield
    task.cancel()


app = FastAPI(
    title="IntentGuard Gateway",
    version="2.0.0",
    description="Intent-consistent transaction protocol between AI agents and a payment provider.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFound)
async def _not_found(_: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(AuthorizationError)
async def _unauthorized(_: Request, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
@app.exception_handler(IllegalTransition)
async def _conflict(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


def guard_of(request: Request) -> IntentGuard:
    return request.app.state.guard


def _row(obj: Any) -> dict[str, Any]:
    d = {c.key: getattr(obj, c.key) for c in obj.__table__.columns}
    if "amount_minor" in d and "currency" in d:
        d["amount_display"] = fmt(d["amount_minor"], d["currency"])
    return d


def _submit_out(r: SubmitResult) -> SubmitOut:
    return SubmitOut(decision=r.decision.value, intent_id=r.intent_id, intent_state=r.intent_state.value,
                     findings=r.findings, proposal_id=r.proposal_id, attempt_id=r.attempt_id,
                     provider_ref=r.provider_ref)


# ------------------------------------------------------------------ system


@app.get("/health", tags=["system"])
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "intentguard-gateway", "provider": settings.PAYMENT_PROVIDER}


@app.get("/info", tags=["system"])
def info(request: Request) -> dict[str, Any]:
    cfg = guard_of(request).cfg
    llm = LLMSettings.from_env()
    return {"protocol": cfg.__dict__, "provider": settings.PAYMENT_PROVIDER,
            "agent_extractor": llm.provider if llm else "offline-rules"}


@app.post("/api/worker/tick", tags=["system"])
def run_tick(request: Request) -> dict[str, int]:
    return {"processed": guard_of(request).tick()}


# ------------------------------------------------------------ operators/orders


@app.get("/api/operators", tags=["admin"])
def list_operators(request: Request) -> list[dict[str, Any]]:
    with guard_of(request).session() as s:
        return [_row(o) for o in s.scalars(select(Operator).order_by(Operator.id))]


@app.post("/api/operators", tags=["admin"], status_code=201)
def upsert_operator(body: OperatorIn, request: Request) -> dict[str, str]:
    guard_of(request).upsert_operator(body.id, body.name, [o.value for o in body.permitted_operations],
                                      to_minor(body.limit, body.currency), body.active)
    return {"id": body.id}


@app.patch("/api/operators/{operator_id}", tags=["admin"])
def patch_operator(operator_id: str, body: OperatorPatch, request: Request) -> dict[str, Any]:
    guard_of(request).set_operator_active(operator_id, body.active)
    return {"id": operator_id, "active": body.active}


@app.get("/api/orders", tags=["admin"])
def list_orders(request: Request) -> list[dict[str, Any]]:
    with guard_of(request).session() as s:
        return [_row(o) for o in s.scalars(select(Order).order_by(Order.id))]


@app.post("/api/orders", tags=["admin"], status_code=201)
def upsert_order(body: OrderIn, request: Request) -> dict[str, str]:
    minor = to_minor(body.amount, body.currency)
    guard_of(request).upsert_order(body.id, body.customer_id, body.currency, minor)
    seed_provider_order(request.app.state.sim, body.id, body.customer_id, body.currency.upper(), minor)
    return {"id": body.id}


# ------------------------------------------------------------------ intents


@app.post("/api/intents", tags=["intents"], status_code=201)
def create_intent(body: IntentIn, request: Request) -> dict[str, Any]:
    g = guard_of(request)
    iid = g.authorize(operator_id=body.operator_id, customer_id=body.customer_id, order_id=body.order_id,
                      operation=body.operation, amount_minor=to_minor(body.amount, body.currency),
                      currency=body.currency, ticket=body.ticket)
    return g.timeline(iid)["intent"]


@app.get("/api/intents", tags=["intents"])
def list_intents(request: Request, state: str | None = None, limit: int = Query(50, le=500)) -> list[dict[str, Any]]:
    with guard_of(request).session() as s:
        stmt = select(Intent).order_by(Intent.created_at.desc()).limit(limit)
        if state:
            stmt = stmt.where(Intent.state == state.upper())
        return [_row(i) for i in s.scalars(stmt)]


@app.get("/api/intents/{intent_id}", tags=["intents"])
def get_intent(intent_id: str, request: Request) -> dict[str, Any]:
    t = guard_of(request).timeline(intent_id)
    for key in ("intent",):
        t[key]["amount_display"] = fmt(t[key]["amount_minor"], t[key]["currency"])
    for key in ("proposals", "attempts", "effects"):
        for r in t[key]:
            r["amount_display"] = fmt(r["amount_minor"], r["currency"])
    return t


@app.post("/api/intents/{intent_id}/proposals", tags=["agent"], response_model=SubmitOut)
def submit_proposal(intent_id: str, body: ProposalIn, request: Request) -> SubmitOut:
    p = Proposal(intent_id=intent_id, request_id=body.request_id or f"req_{uuid.uuid4().hex[:12]}",
                 agent_id=body.agent_id, operation=body.operation, customer_id=body.customer_id,
                 order_id=body.order_id, amount_minor=to_minor(body.amount, body.currency),
                 currency=body.currency.upper(), rationale=body.rationale)
    return _submit_out(guard_of(request).submit(p))


@app.post("/api/intents/{intent_id}/agent", tags=["agent"], response_model=AgentRunOut)
def run_agent(intent_id: str, body: AgentRunIn, request: Request) -> AgentRunOut:
    g = guard_of(request)
    with g.session() as s:
        intent = s.get(Intent, intent_id)
        if intent is None:
            raise HTTPException(404, "intent not found")
        ticket = body.ticket or intent.ticket
    if not ticket:
        raise HTTPException(422, "no ticket text: pass one or store it on the intent")

    llm = LLMSettings.from_env()
    extractor, error, ex = (llm.provider if llm else "offline-rules"), None, None
    try:
        ex = LLMExtractor(llm).extract(ticket) if llm else extract(ticket)
    except (LLMError, ExtractionError) as exc:
        error = str(exc)
    if ex is None:
        return AgentRunOut(extractor=extractor, extracted=None, extraction_error=error, result=None)
    p = Proposal(intent_id=intent_id, request_id=f"req_{uuid.uuid4().hex[:12]}", agent_id=body.agent_id,
                 operation=ex.operation, customer_id=ex.customer_id, order_id=ex.order_id,
                 amount_minor=ex.amount_minor, currency=ex.currency, rationale=f"extracted by {extractor}")
    return AgentRunOut(extractor=extractor, extraction_error=None,
                       extracted={**ex.__dict__, "operation": ex.operation.value,
                                  "amount_display": fmt(ex.amount_minor, ex.currency)},
                       result=_submit_out(g.submit(p)))


@app.post("/api/intents/{intent_id}/reconcile", tags=["intents"])
def reconcile(intent_id: str, request: Request) -> dict[str, str]:
    g = guard_of(request)
    g.reconcile(intent_id)
    return {"intent_state": g._drive(intent_id).value}


@app.post("/api/intents/{intent_id}/revoke", tags=["intents"])
def revoke(intent_id: str, body: RevokeIn, request: Request) -> dict[str, str]:
    guard_of(request).revoke(intent_id, body.actor)
    return {"intent_state": "REVOKED"}


# ------------------------------------------------------------------ reviews


@app.get("/api/reviews", tags=["reviews"])
def list_reviews(request: Request, status: str | None = "OPEN") -> list[dict[str, Any]]:
    with guard_of(request).session() as s:
        stmt = select(ReviewCase).order_by(ReviewCase.created_at.desc())
        if status:
            stmt = stmt.where(ReviewCase.status == status.upper())
        return [_row(r) for r in s.scalars(stmt)]


@app.post("/api/reviews/{case_id}/resolve", tags=["reviews"])
def resolve_review(case_id: int, body: ResolveIn, request: Request) -> dict[str, str]:
    state = guard_of(request).resolve_review(case_id, body.reviewer_id, body.resolution, body.notes)
    return {"intent_state": state.value}


# -------------------------------------------------------------------- audit


@app.get("/api/audit", tags=["audit"])
def list_audit(request: Request, intent_id: str | None = None, limit: int = Query(100, le=1000)) -> list[dict[str, Any]]:
    with guard_of(request).session() as s:
        stmt = select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(limit)
        if intent_id:
            stmt = stmt.where(AuditEvent.chain_id == intent_id)
        return [_row(e) for e in s.scalars(stmt)]


@app.get("/api/audit/verify", tags=["audit"])
def verify_audit(request: Request) -> dict[str, Any]:
    with guard_of(request).session() as s:
        return audit.verify(s)


# ------------------------------------------------------------------ metrics


@app.get("/api/metrics", tags=["metrics"])
def metrics(request: Request) -> dict[str, Any]:
    """Live counts computed from the ledger; nothing here is a constant."""
    with guard_of(request).session() as s:
        def grouped(col: Any) -> dict[str, int]:
            return {k: v for k, v in s.execute(select(col, func.count()).group_by(col))}

        live_bad = s.execute(
            select(func.count(), func.coalesce(func.sum(Effect.amount_minor), 0)).where(
                Effect.provider_status.in_(["PENDING", "COMPLETED"]),
                Effect.classification != "INTENDED", Effect.remediated.is_(False))
        ).one()
        open_reviews = s.execute(
            select(func.count(), func.coalesce(func.sum(ReviewCase.discrepancy_minor), 0)).where(
                ReviewCase.status == "OPEN")
        ).one()
        return {
            "intents_by_state": grouped(Intent.state),
            "proposals_by_decision": grouped(ProposalRecord.decision),
            "attempts_by_status": grouped(Attempt.status),
            "effects_by_class": grouped(Effect.classification),
            "live_unintended_effects": {"count": live_bad[0], "amount_minor": int(live_bad[1])},
            "open_reviews": {"count": open_reviews[0], "discrepancy_minor": int(open_reviews[1])},
        }


# -------------------------------------------------------------- experiments


@app.get("/api/experiments/latest", tags=["experiments"])
def latest_experiment() -> dict[str, Any]:
    """Serves the most recent benchmark output written by `python -m bench run`."""
    path = Path(settings.RESULTS_DIR) / "latest" / "summary.json"
    if not path.exists():
        raise HTTPException(404, "no benchmark results yet; run `python -m bench run`")
    return json.loads(path.read_text(encoding="utf-8"))

