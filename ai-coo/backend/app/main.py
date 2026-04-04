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
from app.api.public.routes import router as public_router

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
app.include_router(public_router)

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


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["System"])
def health():
    """
    Liveness check. Returns 200 when the API process is running.
    Does NOT check DB connectivity — use startup logs for that.
    """
    return {"status": "ok", "environment": settings.environment, "version": "0.3.0"}


@app.get("/api/health/status", tags=["System"])
def health_status():
    """
    Supabase + core PM table probes. Use after changing .env or running migrations.
    Safe read-only checks (limit 1); does not expose row data.
    """
    from urllib.parse import urlparse

    from postgrest.exceptions import APIError

    from app.db.supabase_client import get_client

    def probe_table(client: object, table: str) -> dict:
        try:
            client.table(table).select("id").limit(1).execute()
            return {"ok": True}
        except APIError as exc:
            return {
                "ok": False,
                "code": str(exc.code) if exc.code is not None else None,
                "message": (exc.message or str(exc))[:300],
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)[:300]}

    host = urlparse(settings.supabase_url).netloc or "unknown"
    client = get_client()

    table_names = (
        "global_context",
        "pm_milestones",
        "pm_tasks",
        "pm_task_dependencies",
        "pm_priority_history",
    )
    tables: dict[str, dict] = {name: probe_table(client, name) for name in table_names}

    routing: dict[str, object] = {"target_agent_column": False}
    if tables.get("pm_tasks", {}).get("ok"):
        try:
            client.table("pm_tasks").select("target_agent").limit(1).execute()
            routing["target_agent_column"] = True
        except APIError as exc:
            routing["target_agent_column"] = False
            routing["detail"] = (exc.message or str(exc))[:200]
        except Exception as exc:
            routing["target_agent_column"] = False
            routing["detail"] = str(exc)[:200]

    core_ok = bool(tables.get("global_context", {}).get("ok"))
    pm_core_ok = bool(
        tables.get("pm_milestones", {}).get("ok")
        and tables.get("pm_tasks", {}).get("ok")
    )
    deps_ok = bool(tables.get("pm_task_dependencies", {}).get("ok"))

    return {
        "api": {
            "ok": True,
            "environment": settings.environment,
            "version": "0.3.0",
        },
        "supabase": {
            "url_host": host,
        },
        "tables": tables,
        "pm_routing": routing,
        "summary": {
            "core_db_ready": core_ok,
            "pm_milestones_and_tasks_ready": pm_core_ok,
            "pm_task_dependencies_ready": deps_ok,
            "pm_target_agent_column_ready": bool(routing.get("target_agent_column")),
        },
    }


# Alias for legacy /health path
@app.get("/health", include_in_schema=False)
def health_legacy():
    return health()
