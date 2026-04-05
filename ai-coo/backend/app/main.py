"""
main.py — FastAPI application entrypoint.

All routers are mounted here. The app is intentionally thin:
no business logic lives here. Agents run as Celery workers —
this process handles HTTP only.

CORS is open in development (allow_origins=["*"]). In production,
replace "*" with your actual frontend origin(s).
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ── System routes ─────────────────────────────────────────────────────────────
from app.api.system.context_routes import router as context_router
from app.api.system.event_routes import router as event_router
from app.api.system.approval_routes import router as approval_router
from app.api.system.notification_routes import router as notification_router
from app.api.system.settings_routes import router as settings_router
from app.api.system.sms_webhook import router as sms_router
from app.api.system.telegram_webhook import router as telegram_router

# ── Agent routes ──────────────────────────────────────────────────────────────
from app.api.agents.dev_activity import router as dev_activity_router
from app.api.agents.outreach import router as outreach_router
from app.api.agents.marketing import router as marketing_router
from app.api.agents.finance import router as finance_router
from app.api.agents.pm import router as pm_router
from app.api.agents.research import router as research_router
from app.api.agents.legal import router as legal_router

from app.config import settings

app = FastAPI(
    title="AI COO Backend",
    description=(
        "Multi-agent AI COO system — event-driven autonomous operations.\n\n"
        "Seven specialized agents (Dev, Outreach, Marketing, Finance, PM, Research, Legal) "
        "communicate exclusively through an event bus. Human-in-the-loop approval gates "
        "protect sensitive actions."
    ),
    version="0.3.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],         # Replace with specific origin(s) in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount system routers ──────────────────────────────────────────────────────
app.include_router(context_router)
app.include_router(event_router)
app.include_router(approval_router)
app.include_router(notification_router)
app.include_router(settings_router)
app.include_router(sms_router)
app.include_router(telegram_router)

# ── Mount agent routers ───────────────────────────────────────────────────────
app.include_router(dev_activity_router)
app.include_router(outreach_router)
app.include_router(marketing_router)
app.include_router(finance_router)
app.include_router(pm_router)
app.include_router(research_router)
app.include_router(legal_router)


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """Ping Supabase on startup to surface misconfigured credentials early."""
    from app.db.supabase_client import get_client
    try:
        get_client().table("global_context").select("id").limit(1).execute()
        print("✓ Supabase connected")
    except Exception as exc:
        print(f"✗ Supabase connection failed: {exc}")

    from app.api.system.telegram_webhook import register_webhook
    register_webhook()


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["System"])
def health():
    """
    Liveness check. Returns 200 when the API process is running.
    Does NOT check DB connectivity — use startup logs for that.
    """
    return {"status": "ok", "environment": settings.environment, "version": "0.3.0"}


# Alias for legacy /health path
@app.get("/health", include_in_schema=False)
def health_legacy():
    return health()
