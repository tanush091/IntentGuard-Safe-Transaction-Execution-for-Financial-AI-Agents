"""
Cursor pagination (docs/API.md section 1.5): `?limit=50&cursor=<opaque>`, response
`{"items": [...], "next_cursor": "..." | null}`. Keyset pagination on (sort value, id), newest first.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Callable

from sqlalchemy import Select, and_, or_
from sqlalchemy.orm import Session

from gateway_api.errors import ApiError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def clamp(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1 or limit > MAX_LIMIT:
        raise ApiError(422, "VALIDATION_ERROR", f"limit must be between 1 and {MAX_LIMIT}")
    return limit


def encode(sort_value: Any, row_id: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps([sort_value, row_id]).encode()).decode().rstrip("=")


def decode(cursor: str) -> tuple[Any, Any]:
    try:
        pad = "=" * (-len(cursor) % 4)
        sort_value, row_id = json.loads(base64.urlsafe_b64decode(cursor + pad))
        return sort_value, row_id
    except (ValueError, TypeError) as exc:
        raise ApiError(400, "INVALID_CURSOR", "cursor is not valid") from exc


def paginate(s: Session, stmt: Select, sort_col: Any, id_col: Any, limit: int | None, cursor: str | None,
             key: Callable[[Any], tuple[Any, Any]]) -> tuple[list[Any], str | None]:
    """Run stmt newest first; key(row) -> (sort value, id) of a row, for the next cursor."""
    n = clamp(limit)
    if cursor:
        sv, rid = decode(cursor)
        stmt = stmt.where(or_(sort_col < sv, and_(sort_col == sv, id_col < rid)))
    rows = list(s.scalars(stmt.order_by(sort_col.desc(), id_col.desc()).limit(n + 1)))
    more = len(rows) > n
    rows = rows[:n]
    return rows, (encode(*key(rows[-1])) if more and rows else None)
