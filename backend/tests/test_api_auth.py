"""Authentication (docs/SECURITY.md section 3, docs/TEST_PLAN.md section 10)."""

from __future__ import annotations

import base64
import json
import time

import jwt
import pytest

from tests.api_support import EMAILS, PASSWORD

SECRET = "j" * 48


def _claims(**over):
    t = int(time.time())
    base = {"iss": "intentguard", "aud": "intentguard-api", "sub": "op-asha", "role": "operator",
            "scope": ["intents:read"], "iat": t, "exp": t + 600, "jti": "x" * 32, "typ": "user"}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def _get(api, token):
    return api.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})


def test_login_returns_tokens_and_wrong_password_is_generic(api):
    r = api.client.post("/api/auth/login", json={"email": EMAILS["op-asha"], "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 900 and body["user"]["role"] == "operator"
    assert "ig_refresh" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
    assert "samesite=strict" in r.headers["set-cookie"].lower()
    for email in (EMAILS["op-asha"], "nobody@intentguard.test"):
        bad = api.client.post("/api/auth/login", json={"email": email, "password": "wrong-password-123"})
        assert bad.status_code == 401 and bad.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_browser_cookie_mode_keeps_the_refresh_token_out_of_the_body(api):
    """SECURITY 3.4: a browser (CSRF header) only gets the HttpOnly cookie; API clients get the token."""
    creds = {"email": EMAILS["op-asha"], "password": PASSWORD}
    browser = api.client.post("/api/auth/login", json=creds, headers={"X-IntentGuard-CSRF": "1"})
    assert browser.status_code == 200 and "refresh_token" not in browser.json()
    assert "ig_refresh" in browser.headers["set-cookie"]
    rotated = api.client.post("/api/auth/refresh", headers={"X-IntentGuard-CSRF": "1"})  # cookie from the jar
    assert rotated.status_code == 200 and "refresh_token" not in rotated.json() and rotated.json()["access_token"]
    client = api.client.post("/api/auth/login", json=creds)
    assert client.json()["refresh_token"]


def test_repeated_failures_lock_the_account(api):
    for _ in range(5):
        api.client.post("/api/auth/login", json={"email": EMAILS["op-ravi"], "password": "wrong-password-123"})
    r = api.client.post("/api/auth/login", json={"email": EMAILS["op-ravi"], "password": PASSWORD})
    assert r.status_code == 429 and r.json()["error"]["code"] == "ACCOUNT_LOCKED" and "retry-after" in r.headers


def test_refresh_rotates_and_reuse_revokes_the_family(api):
    first = api.client.post("/api/auth/login", json={"email": EMAILS["op-asha"], "password": PASSWORD}).json()
    r1 = api.client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r1.status_code == 200 and r1.json()["refresh_token"] != first["refresh_token"]
    reuse = api.client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401 and reuse.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"
    # The whole family is revoked, including the token issued by the legitimate rotation.
    after = api.client.post("/api/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]})
    assert after.status_code == 401


def test_cookie_refresh_needs_the_csrf_header_and_logout_revokes(api):
    api.client.post("/api/auth/login", json={"email": EMAILS["op-asha"], "password": PASSWORD})
    assert api.client.post("/api/auth/refresh").json()["error"]["code"] == "CSRF_REQUIRED"
    ok = api.client.post("/api/auth/refresh", headers={"X-IntentGuard-CSRF": "1"})
    assert ok.status_code == 200 and "refresh_token" not in ok.json()
    rotated = api.client.cookies.get("ig_refresh")
    assert api.client.post("/api/auth/logout", headers={"X-IntentGuard-CSRF": "1"}).status_code == 204
    assert api.client.post("/api/auth/refresh", json={"refresh_token": rotated}).status_code == 401


@pytest.mark.parametrize("token_kind", ["expired", "wrong_aud", "wrong_iss", "alg_none", "hs512", "tampered",
                                        "missing_jti", "garbage"])
def test_invalid_access_tokens_are_rejected(api, token_kind):
    if token_kind == "expired":
        token = jwt.encode(_claims(iat=int(time.time()) - 4000, exp=int(time.time()) - 3000), SECRET, "HS256")
    elif token_kind == "wrong_aud":
        token = jwt.encode(_claims(aud="someone-else"), SECRET, "HS256")
    elif token_kind == "wrong_iss":
        token = jwt.encode(_claims(iss="evil"), SECRET, "HS256")
    elif token_kind == "alg_none":
        def b64(d):
            return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
        token = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(_claims())}."
    elif token_kind == "hs512":
        token = jwt.encode(_claims(), SECRET, "HS512")
    elif token_kind == "tampered":
        good = jwt.encode(_claims(), SECRET, "HS256")
        head, payload, sig = good.split(".")
        token = f"{head}.{base64.urlsafe_b64encode(json.dumps(_claims(role='admin')).encode()).decode().rstrip('=')}.{sig}"
    elif token_kind == "missing_jti":
        token = jwt.encode(_claims(jti=None), SECRET, "HS256")
    else:
        token = "not-a-jwt"
    r = _get(api, token)
    assert r.status_code == 401, (token_kind, r.text)
    assert r.json()["error"]["code"] in ("INVALID_TOKEN", "TOKEN_EXPIRED")


def test_role_change_and_deactivation_end_existing_sessions(api):
    ravi = api.login("op-ravi")
    admin = api.login("admin")
    assert api.client.get("/api/auth/me", headers=ravi).status_code == 200
    api.client.patch("/api/admin/users/op-ravi", headers=admin, json={"role": "reviewer"})
    assert api.client.get("/api/auth/me", headers=ravi).status_code == 401  # role in token no longer matches
    meera = api.login("rev-meera")
    api.client.patch("/api/admin/users/rev-meera", headers=admin, json={"active": False})
    assert api.client.get("/api/auth/me", headers=meera).status_code == 401


def test_passwords_must_be_long_enough(api):
    admin = api.login("admin")
    r = api.client.post("/api/admin/users", headers=admin, json={
        "email": "new@intentguard.test", "name": "New", "role": "operator", "password": "short"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEAK_PASSWORD"


def test_unauthenticated_requests_are_401(api):
    r = api.client.get("/api/intents")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"
    assert api.client.get("/api/health").status_code == 200  # liveness needs no token
