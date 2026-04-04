"""
api/system/context_routes.py

Routes:
  GET  /api/context/global   — Return the full GlobalContext object
  PATCH /api/context/global  — User write path (no agent permission check)

This is the user's direct write path. Agent writes go through
core/context.update_global_context() which enforces the permission map.
"""

from __future__ import annotations
from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from app.core.context import get_global_context, _get_raw_row
from app.db.supabase_client import get_client
from app.schemas.context import GlobalContext

router = APIRouter(prefix="/api/context", tags=["Context"])


@router.get(
    "/global",
    response_model=GlobalContext,
    summary="Get global context",
)
def read_global_context():
    """
    Return the full GlobalContext object.

    This is the shared business state read by every agent at the start of
    each run. Includes company profile, ICP, business state, brand voice,
    competitive landscape, and a rolling list of the 50 most recent events.
    """
    try:
        return get_global_context()
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class ContextFieldPatch(BaseModel):
    """
    Request body for PATCH /api/context/global.

    `field` must be a top-level column name in the global_context table
    (e.g. "company_profile", "business_state", "brand_voice").
    `value` is the new JSONB value to set for that column.
    """
    field: str
    value: Any


@router.patch(
    "/global",
    response_model=GlobalContext,
    summary="Update a global context field (user write path)",
)
def patch_global_context(body: ContextFieldPatch):
    """
    User write path — update a single top-level field in the global context.

    This bypasses the agent permission map (users can write any field).
    The version counter is incremented on every write.

    Example body:
        {"field": "company_profile", "value": {"name": "Acme", ...}}
    """
    ALLOWED_COLUMNS = {
        "company_profile", "target_customer", "business_state",
        "brand_voice", "competitive_landscape", "recent_events",
    }
    if body.field not in ALLOWED_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown field '{body.field}'. Allowed: {sorted(ALLOWED_COLUMNS)}",
        )

    raw = _get_raw_row()
    if raw is None:
        raise HTTPException(status_code=404, detail="Global context not seeded yet")

    client = get_client()
    client.table("global_context").update({
        body.field: body.value,
        "version": raw["version"] + 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", raw["id"]).execute()

    return get_global_context()
