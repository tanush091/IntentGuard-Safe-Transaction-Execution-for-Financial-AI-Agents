"""POST /webhooks/{provider} (docs/API.md section 8). Signature-authenticated, not JWT."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request

from gateway_api import webhooks
from gateway_api.errors import ApiError
from gateway_api.routers.deps import guard_of

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

PROVIDERS = {"paysim"}


@router.post("/{provider}", summary="Provider event (verified, deduplicated, then re-fetched)")
async def receive(provider: str, request: Request, background: BackgroundTasks) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ApiError(404, "NOT_FOUND", f"unknown provider {provider}")
    body = await request.body()  # the raw bytes: the signature covers them exactly
    guard = guard_of(request)
    result, new_id = webhooks.receive(guard, provider, request.headers.get(webhooks.SIGNATURE_HEADER), body)
    if new_id is not None:
        background.add_task(webhooks.process, guard, new_id)
    return result
