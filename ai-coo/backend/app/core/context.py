"""
core/context.py — Global Context read/write helpers.

The Global Context is a single row in `global_context` that every agent can
read and (carefully) write to. It holds shared business state: company profile,
target customer, current strategy, brand voice, etc.

Agents should:
  - READ context at the start of every run via `get_global_context()`
  - WRITE context updates via `patch_global_context(updates)` — only patch
    the keys they own; do not overwrite the entire row

The version field is incremented on every write so agents can detect staleness.
"""

from __future__ import annotations
from typing import Any
from app.db.supabase_client import get_client
from app.schemas.context import GlobalContext


async def get_global_context() -> GlobalContext | None:
    """
    Fetch the single global context row.
    Returns None if the table is empty (call seed_global_context.py first).
    """
    client = get_client()
    response = (
        client.table("global_context")
        .select("*")
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    return GlobalContext(**response.data[0])


async def patch_global_context(updates: dict[str, Any]) -> GlobalContext:
    """
    Merge `updates` into the current global context row and increment version.

    `updates` should be a dict of top-level JSONB column names to their new
    values (e.g. {"business_state": {"mrr": 12000, "runway_months": 14}}).

    This is a full-column replace per key — use merge patterns in callers if
    you need deep merges within a JSONB column.
    """
    client = get_client()

    # Fetch current row id
    current = await get_global_context()
    if current is None:
        raise RuntimeError("Global context not seeded. Run scripts/seed_global_context.py")

    payload = {**updates, "version": current.version + 1}

    response = (
        client.table("global_context")
        .update(payload)
        .eq("id", str(current.id))
        .execute()
    )
    return GlobalContext(**response.data[0])


async def get_context_field(field: str) -> Any:
    """Convenience: read a single top-level JSONB field from global context."""
    ctx = await get_global_context()
    if ctx is None:
        return None
    return getattr(ctx, field, None)
