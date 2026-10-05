"""Adapter for the mock-payment-service HTTP API (or any provider exposing the same contract)."""

from __future__ import annotations

from typing import Any

import httpx

from intentguard.domain import Operation, ProviderStatus
from intentguard.providers.base import (
    ProviderConflict,
    ProviderNotFound,
    ProviderRecord,
    ProviderRejected,
    ProviderTimeout,
    ProviderUnavailable,
)

_PATH = {Operation.REFUND: "/v1/refunds", Operation.PAYMENT_AUTHORIZATION: "/v1/authorizations"}
_CANCEL = {Operation.REFUND: "cancel", Operation.PAYMENT_AUTHORIZATION: "void"}


def _record(operation: Operation, d: dict[str, Any]) -> ProviderRecord:
    return ProviderRecord(
        provider_ref=d["id"],
        operation=operation,
        order_id=d["order_id"],
        customer_id=d["customer_id"],
        amount_minor=int(d["amount_minor"]),
        currency=d["currency"],
        status=ProviderStatus(d["status"]),
        idempotency_key=d.get("idempotency_key"),
        metadata=d.get("metadata") or {},
    )


class HttpProvider:
    def __init__(self, base_url: str, timeout_s: float = 5.0, client: httpx.Client | None = None):
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s)

    def close(self) -> None:
        self._client.close()

    def _send(self, method: str, url: str, **kw: Any) -> httpx.Response:
        try:
            resp = self._client.request(method, url, **kw)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise ProviderTimeout(f"{method} {url}: {exc.__class__.__name__}") from exc
        if resp.status_code == 504:
            raise ProviderTimeout(f"{method} {url}: gateway timeout")
        if resp.status_code >= 500:
            raise ProviderUnavailable(f"{method} {url}: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", {})
            except ValueError:
                detail = {}
            code = detail.get("code", "rejected") if isinstance(detail, dict) else "rejected"
            msg = detail.get("message", resp.text) if isinstance(detail, dict) else str(detail)
            if resp.status_code == 404:
                raise ProviderNotFound(msg, code)
            if resp.status_code == 409:
                raise ProviderConflict(msg, code)
            raise ProviderRejected(msg, code)
        return resp

    def create(
        self,
        operation: Operation,
        *,
        order_id: str,
        customer_id: str,
        amount_minor: int,
        currency: str,
        idempotency_key: str | None,
        metadata: dict[str, Any],
    ) -> ProviderRecord:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        body = {
            "order_id": order_id,
            "customer_id": customer_id,
            "amount_minor": amount_minor,
            "currency": currency,
            "metadata": metadata,
        }
        return _record(operation, self._send("POST", _PATH[operation], json=body, headers=headers).json())

    def get(self, operation: Operation, provider_ref: str) -> ProviderRecord:
        return _record(operation, self._send("GET", f"{_PATH[operation]}/{provider_ref}").json())

    def list_by_order(self, operation: Operation, order_id: str) -> list[ProviderRecord]:
        resp = self._send("GET", _PATH[operation], params={"order_id": order_id})
        return [_record(operation, d) for d in resp.json()]

    def cancel(self, operation: Operation, provider_ref: str) -> ProviderRecord:
        url = f"{_PATH[operation]}/{provider_ref}/{_CANCEL[operation]}"
        return _record(operation, self._send("POST", url).json())
