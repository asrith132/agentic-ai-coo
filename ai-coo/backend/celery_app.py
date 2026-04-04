"""
celery_app.py — Celery configuration, beat schedule, and task registration.

Workers run as separate processes from the FastAPI app. Each agent gets its own
Celery task so they can run truly independently and in parallel.

Beat schedule defines when each agent polls or runs automatically. Agents can
also be triggered on-demand via the API (which enqueues a Celery task).

Starting workers:
  celery -A celery_app worker --loglevel=info
  celery -A celery_app beat --loglevel=info

Monitoring (optional Flower dashboard):
  celery -A celery_app flower
"""

from celery import Celery
from celery.schedules import crontab
from app.config import settings

# ── App instance ─────────────────────────────────────────────────────────────
celery_app = Celery(
    "ai_coo",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        # Agent task modules — each exports a `run_<agent>_task` function
        # These will be populated in Prompt 4
        # "app.agents.dev_activity.tasks",
        # "app.agents.outreach.tasks",
        # "app.agents.marketing.tasks",
        # "app.agents.finance.tasks",
        # "app.agents.pm.tasks",
        # "app.agents.research.tasks",
        # "app.agents.legal.tasks",
    ],
)

# ── Celery configuration ──────────────────────────────────────────────────────
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Retry failed tasks up to 3 times with exponential backoff
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker (agents are LLM-heavy)
)

# ── Beat schedule (cron-based agent triggers) ─────────────────────────────────
# Uncomment and adjust schedules once agent tasks are implemented in Prompt 4
celery_app.conf.beat_schedule = {
    # Dev Activity — every 30 minutes
    # "dev-activity-poll": {
    #     "task": "app.agents.dev_activity.tasks.run_dev_activity_task",
    #     "schedule": crontab(minute="*/30"),
    #     "args": [{"type": "scheduled", "agent": "dev_activity", "schedule": "every_30m"}],
    # },

    # Outreach — every 2 hours (check replies, send follow-ups)
    # "outreach-poll": {
    #     "task": "app.agents.outreach.tasks.run_outreach_task",
    #     "schedule": crontab(minute=0, hour="*/2"),
    #     "args": [{"type": "scheduled", "agent": "outreach", "schedule": "every_2h"}],
    # },

    # Marketing — daily at 9am UTC
    # "marketing-daily": {
    #     "task": "app.agents.marketing.tasks.run_marketing_task",
    #     "schedule": crontab(minute=0, hour=9),
    #     "args": [{"type": "scheduled", "agent": "marketing", "schedule": "daily_9am"}],
    # },

    # Finance — daily at 8am UTC
    # "finance-daily": {
    #     "task": "app.agents.finance.tasks.run_finance_task",
    #     "schedule": crontab(minute=0, hour=8),
    #     "args": [{"type": "scheduled", "agent": "finance", "schedule": "daily_8am"}],
    # },

    # PM — every 6 hours
    # "pm-poll": {
    #     "task": "app.agents.pm.tasks.run_pm_task",
    #     "schedule": crontab(minute=0, hour="*/6"),
    #     "args": [{"type": "scheduled", "agent": "pm", "schedule": "every_6h"}],
    # },

    # Research — every 12 hours
    # "research-poll": {
    #     "task": "app.agents.research.tasks.run_research_task",
    #     "schedule": crontab(minute=0, hour="*/12"),
    #     "args": [{"type": "scheduled", "agent": "research", "schedule": "every_12h"}],
    # },

    # Legal — daily at 10am UTC
    # "legal-daily": {
    #     "task": "app.agents.legal.tasks.run_legal_task",
    #     "schedule": crontab(minute=0, hour=10),
    #     "args": [{"type": "scheduled", "agent": "legal", "schedule": "daily_10am"}],
    # },
}
