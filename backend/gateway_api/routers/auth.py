"""POST /auth/login, /auth/refresh, /auth/logout; GET /auth/me (docs/API.md section 2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from gateway_api import security
from gateway_api.errors import ApiError
from gateway_api.routers.deps import guard_of
from gateway_api.schemas import LoginIn, RefreshIn
from gateway_api.security import Principal, current_principal
from gateway_api.settings import settings
from intentguard.models import RefreshToken, User

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE = "ig_refresh"
COOKIE_PATH = "/api/auth"
CSRF_HEADER = "x-intentguard-csrf"


def _token_response(user: User, refresh: str) -> JSONResponse:
    access, _jti, exp = security.issue_access_token(user)
    body = {
        "access_token": access, "token_type": "bearer", "expires_in": settings.ACCESS_TOKEN_TTL_S,
        "refresh_token": refresh,
        "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role},
    }
    resp = JSONResponse(body, headers={"Cache-Control": "no-store"})
    resp.set_cookie(COOKIE, refresh, max_age=settings.REFRESH_TOKEN_TTL_S, httponly=True,
                    secure=settings.COOKIE_SECURE, samesite="strict", path=COOKIE_PATH)
    return resp


@router.post("/login", summary="Email + password -> access token and rotating refresh token")
def login(body: LoginIn, request: Request) -> JSONResponse:
    security.limiter.hit(f"login:{security.client_ip(request)}", settings.LOGIN_RATE_LIMIT_PER_MINUTE)
    guard = guard_of(request)
    t = security.now()
    with guard.session() as s, s.begin():
        user = s.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
        if user is not None and user.locked_until and user.locked_until > t:
            retry = int(user.locked_until - t) + 1
            raise ApiError(429, "ACCOUNT_LOCKED", "too many failed logins; try again later",
                           {"retry_after_s": retry}, headers={"Retry-After": str(retry)})
        ok = (user is not None and user.active and user.role != "agent"
              and security.verify_password(user.password_hash, body.password))
        if not ok:
            if user is not None:
                user.failed_logins += 1
                if user.failed_logins >= settings.LOGIN_MAX_FAILURES:
                    user.locked_until, user.failed_logins = t + settings.LOGIN_LOCKOUT_S, 0
            failed_user = user.id if user else None
        else:
            user.failed_logins, user.locked_until = 0, None
            refresh = security.issue_refresh_token(s, user.id, user_agent=request.headers.get("user-agent"))
            s.flush()
            s.expunge(user)
    if not ok:
        guard.record_audit("auth.login_failed", failed_user or "anonymous", email=body.email.strip().lower())
        raise ApiError(401, "INVALID_CREDENTIALS", "email or password is incorrect")
    guard.record_audit("auth.login", user.id)
    return _token_response(user, refresh)


@router.post("/refresh", summary="Rotate the refresh token; a reused token revokes its family")
def refresh(request: Request, body: RefreshIn | None = None) -> JSONResponse:
    token = body.refresh_token if body else None
    if not token:
        token = request.cookies.get(COOKIE)
        if token and request.headers.get(CSRF_HEADER) != "1":
            raise ApiError(403, "CSRF_REQUIRED", f"cookie refresh requires the {CSRF_HEADER} header")
    if not token:
        raise ApiError(401, "INVALID_REFRESH_TOKEN", "no refresh token")
    guard = guard_of(request)
    try:
        with guard.session() as s, s.begin():
            user, new = security.rotate_refresh_token(s, token, request.headers.get("user-agent"))
            s.flush()
            s.expunge(user)
    except ApiError as exc:
        if exc.code == "REFRESH_TOKEN_REUSED":
            # rotate_refresh_token revoked the family inside a transaction that the error rolled back;
            # revoke again in a transaction of its own so the revocation sticks.
            with guard.session() as s, s.begin():
                rt = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == security._token_hash(token)))
                reused = (rt.user_id, rt.family_id) if rt is not None else None
                if rt is not None:
                    security.revoke_family(s, rt.family_id)
            if reused:  # audit outside the transaction: SQLite allows one writer at a time
                guard.record_audit("auth.refresh_reuse_detected", reused[0], family=reused[1])
        raise
    return _token_response(user, new)


@router.post("/logout", status_code=204, summary="Revoke the refresh token family")
def logout(request: Request, body: RefreshIn | None = None) -> Response:
    token = (body.refresh_token if body else None) or request.cookies.get(COOKIE)
    if token:
        guard = guard_of(request)
        with guard.session() as s, s.begin():
            rt = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == security._token_hash(token)))
            if rt is not None:
                security.revoke_family(s, rt.family_id)
    resp = Response(status_code=204)
    resp.delete_cookie(COOKIE, path=COOKIE_PATH)
    return resp


@router.get("/me", summary="The authenticated principal")
def me(p: Principal = Depends(current_principal)) -> dict[str, Any]:
    return {"id": p.sub, "name": p.name, "role": p.role, "kind": p.kind, "scopes": p.scopes}
