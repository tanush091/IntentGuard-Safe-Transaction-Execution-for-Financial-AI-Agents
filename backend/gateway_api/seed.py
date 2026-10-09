"""
First-start data. DEMO_SEED creates sandbox users (password DEMO_PASSWORD) and orders with
near-miss IDs. Otherwise BOOTSTRAP_ADMIN_EMAIL/PASSWORD create the first admin when no user exists.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import func, select

from gateway_api.security import hash_password, now
from gateway_api.settings import settings
from intentguard.engine import IntentGuard
from intentguard.models import User
from intentguard.money import to_minor

log = logging.getLogger("intentguard.gateway")

DEMO_USERS = [
    # id, email, name, role, permitted operations, limit (INR)
    ("op-asha", "asha@intentguard.test", "Asha (support lead)", "operator", ["REFUND", "PAYMENT_AUTHORIZATION"], "50000"),
    ("op-ravi", "ravi@intentguard.test", "Ravi (support agent)", "operator", ["REFUND"], "5000"),
    ("rev-meera", "meera@intentguard.test", "Meera (finance reviewer)", "reviewer", ["REFUND", "PAYMENT_AUTHORIZATION"],
     "50000"),
    ("admin", "admin@intentguard.test", "Admin", "admin", ["REFUND", "PAYMENT_AUTHORIZATION"], "100000"),
    ("agent-support", None, "Support agent (service principal)", "agent", [], "0"),
]
DEMO_ORDERS = [  # near-miss IDs on purpose: ORD-204 / ORD-240 / ORD-2041
    ("ORD-204", "C-17", "INR", "5000"),
    ("ORD-240", "C-17", "INR", "12000"),
    ("ORD-2041", "C-71", "INR", "20000"),
    ("ORD-311", "C-17", "INR", "8000"),
]


_provider: httpx.Client | None = None


def _provider_client() -> httpx.Client:
    # Reused across calls: building a client per request costs ~1 s on Windows (TLS context setup).
    global _provider
    if _provider is None or str(_provider.base_url).rstrip("/") != settings.PAYMENT_SERVICE_URL.rstrip("/"):
        _provider = httpx.Client(base_url=settings.PAYMENT_SERVICE_URL, timeout=5)
    return _provider


def register_provider_order(sim: Any, order_id: str, customer_id: str, currency: str, amount_minor: int) -> None:
    if sim is not None:
        from paysim import Order as SimOrder

        sim.add_order(SimOrder(order_id, customer_id, currency, amount_minor))
        return
    try:
        _provider_client().post("/v1/orders", json={"order_id": order_id, "customer_id": customer_id,
                                                     "currency": currency, "amount_minor": amount_minor}).raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Could not register order %s with the provider: %s", order_id, exc)


def create_user(guard: IntentGuard, *, user_id: str, email: str | None, name: str, role: str,
                password: str | None, permitted_operations: list[str], limit_minor: int, actor: str) -> None:
    guard.upsert_operator(user_id, name, permitted_operations, limit_minor, role=role)
    with guard.session() as s, s.begin():
        u = s.get(User, user_id)
        assert u is not None
        u.email = email.lower() if email else None
        u.role = role
        u.password_hash = hash_password(password) if password else None
    guard.record_audit("user.created", actor, user_id=user_id, role=role, email=email)


def seed(guard: IntentGuard, sim: Any) -> None:
    with guard.session() as s:
        if s.scalar(select(func.count()).select_from(User)):
            return
    if settings.DEMO_SEED:
        for uid, email, name, role, ops, limit in DEMO_USERS:
            create_user(guard, user_id=uid, email=email, name=name, role=role,
                        password=settings.DEMO_PASSWORD if role != "agent" else None,
                        permitted_operations=ops, limit_minor=to_minor(limit, "INR"), actor="seed")
        for order_id, cust, cur, amount in DEMO_ORDERS:
            minor = to_minor(amount, cur)
            guard.upsert_order(order_id, cust, cur, minor)
            register_provider_order(sim, order_id, cust, cur, minor)
        log.warning("Seeded demo users (password from DEMO_PASSWORD) and orders. Sandbox only.")
    elif settings.BOOTSTRAP_ADMIN_EMAIL and settings.BOOTSTRAP_ADMIN_PASSWORD:
        create_user(guard, user_id="admin", email=settings.BOOTSTRAP_ADMIN_EMAIL, name="Admin", role="admin",
                    password=settings.BOOTSTRAP_ADMIN_PASSWORD,
                    permitted_operations=["REFUND", "PAYMENT_AUTHORIZATION"], limit_minor=0, actor="bootstrap")
        log.info("Created the bootstrap admin %s", settings.BOOTSTRAP_ADMIN_EMAIL)
    else:
        log.warning("No users exist. Set DEMO_SEED=true or BOOTSTRAP_ADMIN_EMAIL/BOOTSTRAP_ADMIN_PASSWORD.")


__all__ = ["DEMO_ORDERS", "DEMO_USERS", "create_user", "now", "register_provider_order", "seed"]
