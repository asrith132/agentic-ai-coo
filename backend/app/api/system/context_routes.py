"""
api/system/context_routes.py — GET/PATCH /api/context/global

Exposes the single global context row to the frontend.
The frontend dashboard reads this to display business state.
Agents update specific fields via the core/context.py helpers internally.
"""

from fastapi import APIRouter, HTTPException
from app.core.context import get_global_context, patch_global_context
from app.schemas.context import GlobalContext, GlobalContextPatch

router = APIRouter(prefix="/api/context", tags=["context"])


@router.get("/global", response_model=GlobalContext)
async def read_global_context():
    """Return the current global context row."""
    ctx = await get_global_context()
    if ctx is None:
        raise HTTPException(status_code=404, detail="Global context not seeded yet")
    return ctx


@router.patch("/global", response_model=GlobalContext)
async def update_global_context(patch: GlobalContextPatch):
    """
    Merge patch fields into the global context.
    Only non-None fields in the request body are applied.
    """
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    return await patch_global_context(updates)
