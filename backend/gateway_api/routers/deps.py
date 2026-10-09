from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from gateway_api.errors import ApiError
from intentguard.engine import IntentGuard
from intentguard.models import Intent


def guard_of(request: Request) -> IntentGuard:
    return request.app.state.guard


def load_intent(s: Session, intent_id: str) -> Intent:
    intent = s.get(Intent, intent_id)
    if intent is None:
        raise ApiError(404, "NOT_FOUND", f"intent {intent_id} not found")
    return intent


def simulator_only(request: Request) -> None:
    if not request.app.state.settings.SIMULATOR_MODE:
        raise ApiError(404, "NOT_FOUND", "simulator endpoints are disabled (SIMULATOR_MODE=false)")


def sim_of(request: Request) -> Any:
    return request.app.state.sim
