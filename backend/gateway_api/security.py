"""
Authentication and authorization (docs/SECURITY.md sections 3 and 4).

* Humans log in with email + password (argon2id) and get a 15-minute access JWT plus an opaque
  refresh token (stored hashed, rotated on every use; reusing a rotated token revokes its family).
* Agents are service principals. An admin issues them short-lived (<= 5 min) JWTs scoped to
  specific intents or customers; they can submit proposals and read those intents only.
* JWTs: HS256 with an explicit algorithm allow-list, iss/aud/exp/iat/sub/jti required, 30 s leeway.
  Every request re-checks that the user is still active and still has the token's role, and that
  an agent token has not been revoked.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from gateway_api.errors import ApiError
from gateway_api.settings import settings
from intentguard.models import Intent, RefreshToken, ServiceToken, User

ALGORITHMS = ["HS256"]
LEEWAY_S = 30
MIN_PASSWORD_LENGTH = 12
ROLES = ("operator", "reviewer", "admin", "agent")

_OPERATOR_CAPS = {
    "intents:read", "authorizations:create", "proposals:create", "agent:run", "reconcile", "cancel",
    "exceptions:read", "exceptions:investigate", "investigations:apply", "reviews:read", "audit:read",
    "metrics:read", "orders:read", "reconciliation:read", "dev",
}
_REVIEWER_CAPS = _OPERATOR_CAPS | {"reviews:resolve", "audit:verify", "reconciliation:run", "mismatches:resolve"}
CAPABILITIES: dict[str, set[str]] = {
    "operator": _OPERATOR_CAPS,
    "reviewer": _REVIEWER_CAPS,
    "admin": _REVIEWER_CAPS | {"admin"},
    "agent": set(),  # agents act only through scopes on specific intents or customers
}

_hasher = PasswordHasher()  # argon2id with the library's current recommended parameters


def now() -> float:
    return time.time()


# ------------------------------------------------------------------ passwords


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ApiError(422, "WEAK_PASSWORD", f"password must be at least {MIN_PASSWORD_LENGTH} characters")


def hash_password(password: str) -> str:
    check_password_policy(password)
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        _hasher.hash("timing-equalizer")  # keep timing similar for users without a password
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ----------------------------------------------------------------------- JWT


@dataclass
class Principal:
    sub: str
    role: str
    kind: str  # "user" | "agent"
    scopes: list[str] = field(default_factory=list)
    jti: str = ""
    name: str = ""

    def can(self, cap: str) -> bool:
        return cap in CAPABILITIES.get(self.role, set())

    def scoped_to(self, action: str, intent: Intent) -> bool:
        """Agent scope check: '<action>:<intent_id>' or '<action>:customer:<customer_id>'."""
        return (f"{action}:{intent.id}" in self.scopes
                or f"{action}:customer:{intent.customer_id}" in self.scopes)


def issue_access_token(user: User, *, ttl_s: int | None = None, scopes: list[str] | None = None,
                       kind: str = "user") -> tuple[str, str, float]:
    issued = now()
    exp = issued + (ttl_s or settings.ACCESS_TOKEN_TTL_S)
    jti = uuid.uuid4().hex
    claims = {
        "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE, "sub": user.id, "role": user.role,
        "scope": scopes if scopes is not None else sorted(CAPABILITIES.get(user.role, set())),
        "iat": int(issued), "exp": int(exp), "jti": jti, "typ": kind,
    }
    return jwt.encode(claims, settings.jwt_secret(), algorithm="HS256"), jti, exp


def decode_token(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in ALGORITHMS:
            raise ApiError(401, "INVALID_TOKEN", "token algorithm is not allowed")
        return jwt.decode(token, settings.jwt_secret(), algorithms=ALGORITHMS, audience=settings.JWT_AUDIENCE,
                          issuer=settings.JWT_ISSUER, leeway=LEEWAY_S,
                          options={"require": ["exp", "iat", "iss", "aud", "sub", "jti"]})
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "TOKEN_EXPIRED", "access token has expired") from exc
    except jwt.PyJWTError as exc:
        raise ApiError(401, "INVALID_TOKEN", f"invalid token: {type(exc).__name__}") from exc


# ------------------------------------------------------------ refresh tokens


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh_token(s: Session, user_id: str, *, family_id: str | None = None,
                        absolute_expires_at: float | None = None, user_agent: str | None = None) -> str:
    t = now()
    token = secrets.token_urlsafe(32)  # 256 bits
    absolute = absolute_expires_at or t + settings.REFRESH_TOKEN_ABSOLUTE_S
    s.add(RefreshToken(user_id=user_id, family_id=family_id or uuid.uuid4().hex, token_hash=_token_hash(token),
                       issued_at=t, expires_at=min(t + settings.REFRESH_TOKEN_TTL_S, absolute),
                       absolute_expires_at=absolute, user_agent=(user_agent or "")[:256]))
    return token


def revoke_family(s: Session, family_id: str) -> None:
    s.execute(update(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
              .values(revoked_at=now()))


def revoke_user_tokens(s: Session, user_id: str) -> None:
    s.execute(update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
              .values(revoked_at=now()))


def rotate_refresh_token(s: Session, token: str, user_agent: str | None = None) -> tuple[User, str]:
    """Consume a refresh token and return (user, new token in the same family)."""
    rt = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == _token_hash(token)))
    t = now()
    if rt is None or rt.revoked_at is not None:
        raise ApiError(401, "INVALID_REFRESH_TOKEN", "refresh token is not valid")
    if rt.used_at is not None:
        revoke_family(s, rt.family_id)  # a rotated token came back: assume theft
        raise ApiError(401, "REFRESH_TOKEN_REUSED", "refresh token was already used; all sessions in this family "
                       "were revoked")
    if t > rt.expires_at:
        raise ApiError(401, "INVALID_REFRESH_TOKEN", "refresh token has expired")
    user = s.get(User, rt.user_id)
    if user is None or not user.active:
        raise ApiError(401, "INVALID_REFRESH_TOKEN", "user is not active")
    rt.used_at = t
    return user, issue_refresh_token(s, user.id, family_id=rt.family_id,
                                     absolute_expires_at=rt.absolute_expires_at, user_agent=user_agent)


# ----------------------------------------------------------------- rate limits


class RateLimiter:
    """Sliding one-minute window per key, in process memory."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: float = 60.0) -> None:
        t = now()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= t - window_s:
                q.popleft()
            if len(q) >= limit:
                retry = int(q[0] + window_s - t) + 1
                raise ApiError(429, "RATE_LIMITED", "too many requests", {"retry_after_s": retry},
                               headers={"Retry-After": str(retry)})
            q.append(t)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ------------------------------------------------------------- dependencies


def current_principal(request: Request) -> Principal:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHENTICATED", "missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_token(auth[7:].strip())
    guard = request.app.state.guard
    with guard.session() as s:
        user = s.get(User, claims["sub"])
        if user is None or not user.active or user.role != claims.get("role"):
            raise ApiError(401, "INVALID_TOKEN", "user is inactive or its role changed")
        if claims.get("typ") == "agent":
            st = s.get(ServiceToken, claims["jti"])
            if st is None or st.revoked_at is not None:
                raise ApiError(401, "INVALID_TOKEN", "agent token was revoked")
        p = Principal(sub=user.id, role=user.role, kind=claims.get("typ", "user"),
                      scopes=list(claims.get("scope") or []), jti=claims["jti"], name=user.name)
    limiter.hit(f"principal:{p.sub}", settings.RATE_LIMIT_PER_MINUTE)
    request.state.principal = p
    return p


def require(cap: str):  # noqa: ANN201 - FastAPI dependency factory
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.can(cap):
            raise ApiError(403, "FORBIDDEN", f"role {p.role} may not do this ({cap})")
        return p

    return dep


def require_intent_access(p: Principal, intent: Intent, cap: str, agent_action: str) -> None:
    """Humans need the capability; agents need a scope for this intent (or its customer)."""
    if p.kind == "agent" or p.role == "agent":
        if not p.scoped_to(agent_action, intent):
            raise ApiError(403, "FORBIDDEN", "agent token is not scoped to this intent")
        return
    if not p.can(cap):
        raise ApiError(403, "FORBIDDEN", f"role {p.role} may not do this ({cap})")
