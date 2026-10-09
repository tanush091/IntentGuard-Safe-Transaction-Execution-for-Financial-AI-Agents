"""
Client `Idempotency-Key` for state-creating POSTs (docs/API.md section 1.3). This protects the API
call itself: a replay with the same key and body returns the stored response; the same key with a
different body is refused. It is separate from the provider idempotency key, which the gateway
derives from the intent and never exposes. Money safety does not depend on this layer.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from gateway_api.errors import ApiError
from gateway_api.security import Principal, now
from intentguard.models import ApiIdempotency

MAX_KEY = 128


def run(request: Request, principal: Principal, body: Any, status_code: int,
        handler: Callable[[], Any]) -> JSONResponse:
    key = request.headers.get("idempotency-key")
    if key is None:
        return JSONResponse(status_code=status_code, content=handler())
    if not key or len(key) > MAX_KEY:
        raise ApiError(400, "INVALID_IDEMPOTENCY_KEY", f"Idempotency-Key must be 1-{MAX_KEY} characters")
    payload = body.model_dump(mode="json") if hasattr(body, "model_dump") else body
    digest = hashlib.sha256(json.dumps([request.url.path, payload], sort_keys=True, default=str).encode()).hexdigest()
    guard = request.app.state.guard
    with guard.session() as s:
        stored = s.get(ApiIdempotency, (principal.sub, key))
        if stored is not None:
            if stored.body_hash != digest:
                raise ApiError(422, "IDEMPOTENCY_KEY_REUSE",
                               "this Idempotency-Key was used with a different request")
            return JSONResponse(status_code=stored.status_code, content=stored.response,
                                headers={"Idempotent-Replay": "true"})
    result = handler()
    try:
        with guard.session() as s, s.begin():
            s.add(ApiIdempotency(principal=principal.sub, key=key, method=request.method, path=request.url.path,
                                 body_hash=digest, status_code=status_code, response=result, created_at=now()))
    except IntegrityError:
        pass  # a concurrent request with the same key stored first; this one already ran safely
    return JSONResponse(status_code=status_code, content=result)
