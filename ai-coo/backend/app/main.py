"""
main.py — FastAPI application entrypoint.

Mounts all routers under their respective prefixes and configures:
  - CORS (allow all origins in dev; tighten in production)
  - Global exception handler
  - Startup event to verify Supabase connectivity

The Next.js frontend communicates with this API exclusively — agents never
expose their own HTTP endpoints.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# System routes
from app.api.system.context_routes import router as context_router
from app.api.system.event_routes import router as event_router
from app.api.system.approval_routes import router as approval_router
from app.api.system.notification_routes import router as notification_router

# Agent routes
from app.api.agents.dev_activity import router as dev_router
from app.api.agents.outreach import router as outreach_router
from app.api.agents.marketing import router as marketing_router
from app.api.agents.finance import router as finance_router
from app.api.agents.pm import router as pm_router
from app.api.agents.research import router as research_router
from app.api.agents.legal import router as legal_router

from app.config import settings

app = FastAPI(
    title="AI COO Backend",
    description="Multi-agent AI COO system API",
    version="0.1.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# In production, replace "*" with your actual frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
# System infrastructure
app.include_router(context_router)
app.include_router(event_router)
app.include_router(approval_router)
app.include_router(notification_router)

# Agent-specific APIs
app.include_router(dev_router)
app.include_router(outreach_router)
app.include_router(marketing_router)
app.include_router(finance_router)
app.include_router(pm_router)
app.include_router(research_router)
app.include_router(legal_router)


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """Verify Supabase connectivity on startup."""
    from app.db.supabase_client import get_client
    try:
        client = get_client()
        # Lightweight ping — just checks auth, doesn't pull data
        client.table("global_context").select("id").limit(1).execute()
        print("✓ Supabase connected")
    except Exception as e:
        print(f"✗ Supabase connection failed: {e}")
        # Don't crash — allow the app to start even if DB is temporarily unavailable


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "environment": settings.environment}
