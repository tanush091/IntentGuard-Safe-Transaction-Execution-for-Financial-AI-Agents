"""Health, readiness and simulator-only endpoints (docs/API.md section 12)."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from gateway_api.errors import ApiError
from gateway_api.routers.deps import guard_of, simulator_only
from gateway_api.schemas import FaultIn
from gateway_api.security import Principal, require

router = APIRouter(tags=["system"])
dev = APIRouter(prefix="/dev", tags=["dev (simulator only)"], dependencies=[Depends(simulator_only)])


@router.get("/health", summary="Liveness (no auth)")
def health(request: Request) -> dict[str, Any]:
    return {"status": "ok", "service": "intentguard-gateway"}


@router.get("/ready", summary="Database and provider reachability (no auth)")
def ready(request: Request) -> JSONResponse:
    guard = guard_of(request)
    settings = request.app.state.settings
    checks: dict[str, str] = {}
    try:
        with guard.session() as s:
            s.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"
    if settings.PAYMENT_PROVIDER == "inprocess":
        checks["provider"] = "ok (in-process simulator)"
    else:
        try:
            _provider_client(request).get("/health", timeout=2).raise_for_status()
            checks["provider"] = "ok"
        except httpx.HTTPError as exc:
            checks["provider"] = f"error: {type(exc).__name__}"
    ok = all(v.startswith("ok") for v in checks.values())
    return JSONResponse(status_code=200 if ok else 503, content={"status": "ready" if ok else "not_ready", **checks})


def _provider_client(request: Request) -> httpx.Client:
    """The HTTP provider adapter's own client (same base URL, timeout and transport as the engine uses)."""
    client = getattr(guard_of(request).provider, "_client", None)
    if client is None:
        client = httpx.Client(base_url=request.app.state.settings.PAYMENT_SERVICE_URL, timeout=5)
    return client


# ------------------------------------------------------------ simulator only


def _provider_call(request: Request, method: str, path: str, **kw: Any) -> Any:
    sim = request.app.state.sim
    if sim is not None:
        return None
    try:
        resp = _provider_client(request).request(method, path, **kw)
    except httpx.HTTPError as exc:
        raise ApiError(503, "PROVIDER_UNAVAILABLE", f"provider unreachable: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        raise ApiError(resp.status_code if resp.status_code < 500 else 502, "PROVIDER_ERROR", resp.text[:300])
    return resp.json()


@dev.get("/faults", summary="Queued provider faults")
def list_faults(request: Request, p: Principal = Depends(require("dev"))) -> Any:
    sim = request.app.state.sim
    if sim is not None:
        return [{"kind": f.kind.value, "order_id": f.order_id, "times": f.times, "params": f.params}
                for f in sim.faults()]
    return _provider_call(request, "GET", "/v1/faults")


@dev.post("/faults", status_code=201, summary="Inject a provider fault")
def inject_fault(body: FaultIn, request: Request, p: Principal = Depends(require("dev"))) -> Any:
    sim = request.app.state.sim
    if sim is not None:
        from paysim import Fault, FaultKind

        try:
            kind = FaultKind(body.kind)
        except ValueError as exc:
            raise ApiError(422, "VALIDATION_ERROR", f"unknown fault kind {body.kind}") from exc
        sim.inject(Fault(kind, body.order_id, body.times, body.params))
        out: Any = {"kind": kind.value}
    else:
        out = _provider_call(request, "POST", "/v1/faults", json=body.model_dump())
    guard_of(request).record_audit("dev.fault_injected", p.sub, fault_kind=body.kind, order_id=body.order_id,
                                   times=body.times, params=body.params)
    return out


@dev.delete("/faults", summary="Clear provider faults")
def clear_faults(request: Request, p: Principal = Depends(require("dev"))) -> Any:
    sim = request.app.state.sim
    if sim is not None:
        sim.clear_faults()
        return {"status": "cleared"}
    return _provider_call(request, "DELETE", "/v1/faults")


@dev.get("/ledger", summary="Provider ground truth (every transaction, ignoring search visibility)")
def ledger(request: Request, order_id: str | None = None, p: Principal = Depends(require("dev"))) -> Any:
    sim = request.app.state.sim
    if sim is not None:
        return [t.public() for t in sim.all_transactions() if order_id is None or t.order_id == order_id]
    return _provider_call(request, "GET", "/v1/ledger", params={"order_id": order_id} if order_id else None)


@dev.post("/worker/tick", summary="Run one worker pass now")
def tick(request: Request, p: Principal = Depends(require("dev"))) -> dict[str, int]:
    return {"processed": len(guard_of(request).tick_detailed())}
