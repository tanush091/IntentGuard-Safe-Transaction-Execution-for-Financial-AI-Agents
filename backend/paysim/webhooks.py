"""
Simulated provider webhooks.

Whenever a transaction's status changes (created PENDING, settled COMPLETED, CANCELLED, ...) an event
is emitted. Event ids are deterministic (one per transaction and status), so a provider restart that
re-emits events produces duplicates the receiver must deduplicate. Faults:

  WEBHOOK_DUPLICATE  deliver the next event for the order twice
  WEBHOOK_DELAY      deliver the next event for the order `delay_s` seconds late (so later events
                     can arrive first: out-of-order delivery)

Signature: `Paysim-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>." + raw body>`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from paysim.simulator import FaultKind, PaymentSimulator

log = logging.getLogger("paysim.webhooks")


def sign(secret: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={mac}"


@dataclass(order=True)
class Delivery:
    due_at: float
    body: bytes = field(compare=False)
    tries: int = field(default=0, compare=False)


class WebhookEmitter:
    """Watches the simulator and delivers signed events. Call step() periodically (or run())."""

    def __init__(self, sim: PaymentSimulator, url: str, secret: str,
                 post: Callable[[str, bytes, dict[str, str]], int] | None = None, max_tries: int = 6):
        self.sim, self.url, self.secret = sim, url, secret
        self._post = post or self._http_post
        self._client: Any = None
        self.max_tries = max_tries
        self._seen: dict[str, str] = {}
        self._seq: dict[str, int] = {}
        self._queue: list[Delivery] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def _http_post(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        # One pooled client: a fresh httpx.post per delivery rebuilds the TLS context each time (~1 s on Windows).
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=2.0)
        return self._client.post(url, content=body, headers=headers).status_code

    def collect(self) -> list[dict[str, Any]]:
        """Events for every status change since the last call (also queued for delivery)."""
        events = []
        now = time.time()
        for tx in self.sim.all_transactions():
            status = tx.status.value
            if self._seen.get(tx.id) == status:
                continue
            self._seen[tx.id] = status
            self._seq[tx.id] = self._seq.get(tx.id, 0) + 1
            event = {"id": f"evt_{tx.id}_{status.lower()}", "type": f"{tx.kind.value.lower()}.{status.lower()}",
                     "created": now, "sequence": self._seq[tx.id], "data": {"object": tx.public()}}
            events.append(event)
            body = json.dumps(event, sort_keys=True, default=str).encode()
            delay = 0.0
            if (f := self.sim.take_fault(FaultKind.WEBHOOK_DELAY, tx.order_id)) is not None:
                delay = float(f.params.get("delay_s", 10.0))
            copies = 2 if self.sim.take_fault(FaultKind.WEBHOOK_DUPLICATE, tx.order_id) is not None else 1
            with self._lock:
                for _ in range(copies):
                    self._queue.append(Delivery(now + delay, body))
        return events

    def deliver_due(self) -> int:
        """Send every queued event that is due. Failed deliveries are retried with back-off."""
        now = time.time()
        with self._lock:
            due = sorted(d for d in self._queue if d.due_at <= now)
            self._queue = [d for d in self._queue if d.due_at > now]
        sent = 0
        for d in due:
            ts = int(time.time())
            headers = {"Content-Type": "application/json", "Paysim-Signature": sign(self.secret, ts, d.body)}
            try:
                status = self._post(self.url, d.body, headers)
            except Exception as exc:  # noqa: BLE001 - delivery failures are retried
                status = 0
                log.warning("webhook delivery failed: %s", exc)
            if 200 <= status < 300:
                sent += 1
            elif d.tries + 1 < self.max_tries:
                with self._lock:
                    self._queue.append(Delivery(now + 2 ** d.tries, d.body, d.tries + 1))
        return sent

    def step(self) -> None:
        self.collect()
        self.deliver_due()

    def run(self, interval_s: float = 0.5) -> None:
        while not self._stop.is_set():
            try:
                self.step()
            except Exception:  # noqa: BLE001
                log.exception("webhook emitter step failed")
            self._stop.wait(interval_s)

    def stop(self) -> None:
        self._stop.set()
