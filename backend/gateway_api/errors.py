"""
The error envelope from docs/API.md section 1.4:

    {"error": {"code": "...", "message": "...", "details": {...}, "request_id": "req_..."}}

Gateway *decisions* (REJECT, DUPLICATE, ...) are not errors: they are HTTP 200 payloads.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from intentguard.db import SchemaMismatch
from intentguard.domain import IllegalTransition
from intentguard.engine import AuthorizationError, ConflictError, GatewayError, NotFound, PermissionDenied

log = logging.getLogger("intentguard.gateway")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.details = details or {}
        self.headers = headers or {}


def envelope(request: Request, status: int, code: str, message: str, details: dict[str, Any] | None = None,
             headers: dict[str, str] | None = None) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=status, headers=headers,
                        content={"error": {"code": code, "message": message, "details": details or {},
                                           "request_id": rid}})


_STATUS = {AuthorizationError: 422, NotFound: 404, ConflictError: 409, PermissionDenied: 403}
_HTTP_CODES = {400: "BAD_REQUEST", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND",
               405: "METHOD_NOT_ALLOWED", 409: "STATE_CONFLICT", 422: "VALIDATION_ERROR", 429: "RATE_LIMITED",
               500: "INTERNAL_ERROR", 502: "PROVIDER_ERROR", 503: "PROVIDER_UNAVAILABLE"}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return envelope(request, exc.status, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(GatewayError)
    async def _gateway_error(request: Request, exc: GatewayError) -> JSONResponse:
        status = next((v for k, v in _STATUS.items() if isinstance(exc, k)), 400)
        return envelope(request, status, exc.code, str(exc), exc.details)

    @app.exception_handler(IllegalTransition)
    async def _illegal(request: Request, exc: IllegalTransition) -> JSONResponse:
        return envelope(request, 409, "ILLEGAL_TRANSITION", str(exc))

    @app.exception_handler(SchemaMismatch)
    async def _schema(request: Request, exc: SchemaMismatch) -> JSONResponse:
        return envelope(request, 500, "SCHEMA_MISMATCH", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": [str(x) for x in e.get("loc", ())], "msg": e.get("msg"), "type": e.get("type")}
                  for e in exc.errors()]
        if any(e["type"] == "json_invalid" for e in errors):
            return envelope(request, 400, "MALFORMED_REQUEST", "request body is not valid JSON", {"errors": errors})
        return envelope(request, 422, "VALIDATION_ERROR", "request validation failed", {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        code = _HTTP_CODES.get(exc.status_code, "ERROR")
        message = detail if isinstance(detail, str) else code.replace("_", " ").lower()
        return envelope(request, exc.status_code, code, message, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return envelope(request, 500, "INTERNAL_ERROR", "internal error")
