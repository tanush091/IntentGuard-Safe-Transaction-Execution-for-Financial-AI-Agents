"""Admin: users, scoped agent tokens, policies, provider connections, orders (docs/API.md section 11)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from gateway_api import security
from gateway_api import serializers as ser
from gateway_api.errors import ApiError
from gateway_api.pagination import paginate
from gateway_api.routers.deps import guard_of
from gateway_api.schemas import OrderIn, PoliciesIn, ProviderIn, ServiceTokenIn, UserIn, UserPatch
from gateway_api.security import Principal, now, require
from gateway_api.seed import create_user, register_provider_order
from intentguard.models import Intent, Order, ProviderConfig, ServiceToken, User
from intentguard.money import to_minor

router = APIRouter(tags=["admin"])
admin = require("admin")


# --------------------------------------------------------------------- users


@router.get("/admin/users", summary="Users and service principals")
def list_users(request: Request, p: Principal = Depends(admin), limit: int | None = Query(None),
               cursor: str | None = None) -> dict[str, Any]:
    with guard_of(request).session() as s:
        rows, nxt = paginate(s, select(User), User.created_at, User.id, limit, cursor, lambda u: (u.created_at, u.id))
        return {"items": [ser.user(u) for u in rows], "next_cursor": nxt}


@router.post("/admin/users", status_code=201, summary="Create a user or an agent service principal")
def add_user(body: UserIn, request: Request, p: Principal = Depends(admin)) -> dict[str, Any]:
    guard = guard_of(request)
    if body.role != "agent" and (not body.email or not body.password):
        raise ApiError(422, "VALIDATION_ERROR", "email and password are required for operator, reviewer and admin")
    if body.role == "agent" and body.password:
        raise ApiError(422, "VALIDATION_ERROR", "agents authenticate with service tokens, not passwords")
    user_id = body.id or (body.email.split("@")[0] if body.email else f"agent-{int(now())}")
    with guard.session() as s:
        if s.get(User, user_id) is not None:
            raise ApiError(409, "ALREADY_EXISTS", f"user {user_id} already exists")
        if body.email and s.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())):
            raise ApiError(409, "ALREADY_EXISTS", "email is already in use")
    create_user(guard, user_id=user_id, email=body.email, name=body.name, role=body.role, password=body.password,
                permitted_operations=[o.value for o in body.permitted_operations],
                limit_minor=to_minor(body.limit, "INR"), actor=p.sub)
    with guard.session() as s:
        return ser.user(s.get(User, user_id))


@router.patch("/admin/users/{user_id}", summary="Change role, status, password, permissions or limit")
def patch_user(user_id: str, body: UserPatch, request: Request, p: Principal = Depends(admin)) -> dict[str, Any]:
    guard = guard_of(request)
    changes: dict[str, Any] = {}
    with guard.session() as s, s.begin():
        u = s.get(User, user_id)
        if u is None:
            raise ApiError(404, "NOT_FOUND", f"user {user_id} not found")
        if body.name is not None:
            u.name = changes["name"] = body.name
        if body.permitted_operations is not None:
            u.permitted_operations = changes["permitted_operations"] = [o.value for o in body.permitted_operations]
        if body.limit is not None:
            u.limit_minor = changes["limit_minor"] = to_minor(body.limit, "INR")
        revoke = False
        if body.role is not None and body.role != u.role:
            u.role = changes["role"] = body.role
            revoke = True
        if body.active is not None and body.active != u.active:
            u.active = changes["active"] = body.active
            revoke = revoke or not body.active
        if body.password is not None:
            u.password_hash = security.hash_password(body.password)
            u.failed_logins, u.locked_until = 0, None
            changes["password"] = "changed"
            revoke = True
        if revoke:
            security.revoke_user_tokens(s, user_id)  # role, status or password change ends all sessions
    guard.record_audit("user.updated", p.sub, user_id=user_id, changes=changes)
    with guard.session() as s:
        return ser.user(s.get(User, user_id))


# ----------------------------------------------------------- service tokens


@router.post("/admin/service-tokens", status_code=201, summary="Issue a short-lived, scoped agent token")
def issue_service_token(body: ServiceTokenIn, request: Request, p: Principal = Depends(admin)) -> dict[str, Any]:
    guard = guard_of(request)
    settings = request.app.state.settings
    if not body.intent_ids and not body.customer_ids:
        raise ApiError(422, "VALIDATION_ERROR", "an agent token must be scoped to intent_ids or customer_ids")
    ttl = min(body.ttl_s, settings.AGENT_TOKEN_MAX_TTL_S)
    with guard.session() as s:
        agent = s.get(User, body.principal_id)
        if agent is None or agent.role != "agent" or not agent.active:
            raise ApiError(422, "VALIDATION_ERROR", "principal_id must be an active agent service principal")
        missing = [i for i in body.intent_ids if s.get(Intent, i) is None]
        if missing:
            raise ApiError(422, "VALIDATION_ERROR", f"unknown intents: {missing}")
        s.expunge(agent)
    scopes = ([f"proposals:create:{i}" for i in body.intent_ids] + [f"intents:read:{i}" for i in body.intent_ids]
              + [f"proposals:create:customer:{c}" for c in body.customer_ids]
              + [f"intents:read:customer:{c}" for c in body.customer_ids])
    token, jti, exp = security.issue_access_token(agent, ttl_s=ttl, scopes=scopes, kind="agent")
    with guard.session() as s, s.begin():
        s.add(ServiceToken(jti=jti, user_id=agent.id, scopes=scopes, issued_by=p.sub, issued_at=now(), expires_at=exp))
    guard.record_audit("service_token.issued", p.sub, principal_id=agent.id, jti=jti, scopes=scopes, ttl_s=ttl)
    return {"token": token, "token_type": "bearer", "jti": jti, "scopes": scopes, "expires_at": ser.iso(exp),
            "expires_in": ttl}


@router.get("/admin/service-tokens", summary="Issued agent tokens (values are never shown again)")
def list_service_tokens(request: Request, p: Principal = Depends(admin)) -> dict[str, Any]:
    with guard_of(request).session() as s:
        rows = list(s.scalars(select(ServiceToken).order_by(ServiceToken.issued_at.desc()).limit(200)))
        return {"items": [{"jti": t.jti, "principal_id": t.user_id, "scopes": t.scopes, "issued_by": t.issued_by,
                           "issued_at": ser.iso(t.issued_at), "expires_at": ser.iso(t.expires_at),
                           "revoked_at": ser.iso(t.revoked_at), "active": t.revoked_at is None and t.expires_at > now()}
                          for t in rows], "next_cursor": None}


@router.delete("/admin/service-tokens/{jti}", summary="Revoke an agent token")
def revoke_service_token(jti: str, request: Request, p: Principal = Depends(admin)) -> dict[str, Any]:
    guard = guard_of(request)
    with guard.session() as s, s.begin():
        t = s.get(ServiceToken, jti)
        if t is None:
            raise ApiError(404, "NOT_FOUND", f"token {jti} not found")
        t.revoked_at = t.revoked_at or now()
    guard.record_audit("service_token.revoked", p.sub, jti=jti)
    return {"jti": jti, "revoked": True}


# ------------------------------------------------------------------ policies


def _policies(request: Request) -> dict[str, Any]:
    guard = guard_of(request)
    pol = guard.policies()
    return {
        "kill_switch": bool(pol["kill_switch"]),
        "max_amount": ser.amount(pol["max_amount_minor"], "INR") if pol["max_amount_minor"] is not None else None,
        "separation_of_duties": bool(pol["separation_of_duties"]),
        "attempt_budget": guard.cfg.max_attempts,
        "absence_window_s": guard.cfg.absence_window_s,
        "unknown_review_after_s": guard.cfg.unknown_review_after_s,
        "protocol": asdict(guard.cfg),
    }


@router.get("/admin/policies", summary="Kill switch, limits, attempt budget, absence window")
def get_policies(request: Request, p: Principal = Depends(admin)) -> dict[str, Any]:
    return _policies(request)


@router.put("/admin/policies", summary="Change policies (applied immediately and audited)")
def put_policies(body: PoliciesIn, request: Request, p: Principal = Depends(admin)) -> dict[str, Any]:
    guard = guard_of(request)
    if body.kill_switch is not None:
        guard.set_policy("kill_switch", body.kill_switch, p.sub)
    if body.clear_max_amount:
        guard.set_policy("max_amount_minor", None, p.sub)
    elif body.max_amount is not None:
        guard.set_policy("max_amount_minor", to_minor(body.max_amount, "INR"), p.sub)
    if body.separation_of_duties is not None:
        guard.set_policy("separation_of_duties", body.separation_of_duties, p.sub)
    protocol = {"attempt_budget": ("max_attempts", body.attempt_budget),
                "absence_window_s": ("absence_window_s", body.absence_window_s),
                "unknown_review_after_s": ("unknown_review_after_s", body.unknown_review_after_s)}
    for key, (field, value) in protocol.items():
        if value is not None:
            guard.set_policy(key, value, p.sub)
            guard.cfg = guard.cfg.without(**{field: value})
    return _policies(request)


# ----------------------------------------------------------------- providers


@router.get("/admin/providers", summary="Provider connections (secrets are write-only)")
def get_providers(request: Request, p: Principal = Depends(admin)) -> dict[str, Any]:
    settings = request.app.state.settings
    with guard_of(request).session() as s:
        cfg = s.get(ProviderConfig, "paysim")
        return {"items": [{
            "name": "paysim", "simulator": True, "mode": settings.PAYMENT_PROVIDER,
            "base_url": cfg.base_url if cfg else settings.PAYMENT_SERVICE_URL,
            "timeout_s": cfg.timeout_s if cfg else settings.PROVIDER_TIMEOUT_S,
            "webhook_secret_set": bool((cfg and cfg.webhook_secret) or settings.WEBHOOK_SECRET),
            "updated_by": cfg.updated_by if cfg else None, "updated_at": ser.iso(cfg.updated_at) if cfg else None,
        }]}


@router.put("/admin/providers/{name}", summary="Update a provider connection")
def put_provider(name: str, body: ProviderIn, request: Request, p: Principal = Depends(admin)) -> dict[str, Any]:
    if name != "paysim":
        raise ApiError(404, "NOT_FOUND", f"unknown provider {name}")
    guard = guard_of(request)
    settings = request.app.state.settings
    with guard.session() as s, s.begin():
        cfg = s.get(ProviderConfig, name)
        if cfg is None:
            cfg = ProviderConfig(name=name, base_url=settings.PAYMENT_SERVICE_URL,
                                 timeout_s=settings.PROVIDER_TIMEOUT_S, updated_by=p.sub, updated_at=now())
            s.add(cfg)
        if body.base_url is not None:
            cfg.base_url = body.base_url
        if body.timeout_s is not None:
            cfg.timeout_s = body.timeout_s
        if body.webhook_secret is not None:
            cfg.webhook_secret = body.webhook_secret
        cfg.updated_by, cfg.updated_at = p.sub, now()
        base_url, timeout = cfg.base_url, cfg.timeout_s
    if settings.PAYMENT_PROVIDER == "http" and (body.base_url is not None or body.timeout_s is not None):
        from intentguard.providers.http import HttpProvider

        guard.provider = HttpProvider(base_url, timeout_s=timeout)
    guard.record_audit("provider.updated", p.sub, provider=name, base_url=body.base_url, timeout_s=body.timeout_s,
                       webhook_secret="changed" if body.webhook_secret else None)
    return get_providers(request, p)


# -------------------------------------------------------------------- orders


@router.get("/orders", summary="The merchant's orders")
def list_orders(request: Request, p: Principal = Depends(require("orders:read"))) -> dict[str, Any]:
    with guard_of(request).session() as s:
        return {"items": [{"order_id": o.id, "customer_id": o.customer_id, "currency": o.currency,
                           "amount": ser.amount(o.amount_minor, o.currency), "created_at": ser.iso(o.created_at)}
                          for o in s.scalars(select(Order).order_by(Order.id))], "next_cursor": None}


@router.post("/admin/orders", status_code=201, summary="Create or update an order (also registered at the provider)")
def upsert_order(body: OrderIn, request: Request, p: Principal = Depends(admin)) -> dict[str, Any]:
    guard = guard_of(request)
    minor = to_minor(body.amount, body.currency)
    guard.upsert_order(body.id, body.customer_id, body.currency, minor)
    register_provider_order(request.app.state.sim, body.id, body.customer_id, body.currency.upper(), minor)
    guard.record_audit("order.upserted", p.sub, order_id=body.id, customer_id=body.customer_id, amount_minor=minor)
    return {"order_id": body.id}
