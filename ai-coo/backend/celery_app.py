"""
celery_app.py — Celery app, beat schedule, and all background tasks.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RUNNING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Start worker + beat scheduler together (development):
    celery -A celery_app worker --beat --loglevel=info

Separate processes (production):
    celery -A celery_app worker --loglevel=info --concurrency=4
    celery -A celery_app beat   --loglevel=info

Optional Flower monitoring dashboard:
    celery -A celery_app flower --port=5555
    open http://localhost:5555

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BEAT SCHEDULE OVERVIEW
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  event_processor          every 2 min   — polls event bus; dispatches to subscribing agents
  marketing_trend_scan     every 30 min  — scans Reddit/X/LinkedIn for relevant conversations
  outreach_followup_check  every 6 hr    — identifies contacts needing follow-up
  pm_daily_digest          Mon–Fri 9am   — daily task digest with top priorities
  finance_weekly_summary   Mon 9am       — weekly financial health summary notification
  legal_deadline_check     daily 8am     — checks approaching compliance deadlines

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DESIGN NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• worker_prefetch_multiplier=1: agents make LLM calls that can take 5–30s.
  Fetching one task at a time prevents a single worker from hoarding tasks.

• task_acks_late=True + task_reject_on_worker_lost=True: if the worker dies
  mid-task (e.g. OOM), the task is returned to the queue for retry rather
  than silently dropped.

• The event_processor is the "fan-out" loop. It runs every 2 min and checks
  every agent for unconsumed events. In production this should be replaced
  with Supabase Realtime webhooks → task dispatch, but polling works fine
  for a hackathon / MVP.
"""

from __future__ import annotations
import logging
from typing import Any

from celery import Celery
from celery.schedules import crontab

from app.config import settings

logger = logging.getLogger(__name__)

# ── Agent registry ────────────────────────────────────────────────────────────
# Imported lazily inside tasks to avoid circular imports at module load time.
# This dict is the source of truth for which agents exist and what class they map to.

def _get_agent_registry() -> dict[str, Any]:
    """
    Return a mapping of agent name → agent class.
    Imported lazily so module-level imports don't trigger DB/config access.
    """
    from app.agents.dev_activity.agent import DevActivityAgent
    from app.agents.outreach.agent import OutreachAgent
    from app.agents.marketing.agent import MarketingAgent
    from app.agents.finance.agent import FinanceAgent
    from app.agents.pm.agent import PMAgent
    from app.agents.research.agent import ResearchAgent
    from app.agents.legal.agent import LegalAgent

    return {
        "dev_activity": DevActivityAgent,
        "outreach":     OutreachAgent,
        "marketing":    MarketingAgent,
        "finance":      FinanceAgent,
        "pm":           PMAgent,
        "research":     ResearchAgent,
        "legal":        LegalAgent,
    }


# Convenience alias used by API routes that want to dispatch tasks by name
AGENT_NAMES = [
    "dev_activity", "outreach", "marketing",
    "finance", "pm", "research", "legal",
]


# ── Celery app ────────────────────────────────────────────────────────────────

celery_app = Celery(
    "ai_coo",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Time
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_acks_late=True,                # ack only after task completes (not on receipt)
    task_reject_on_worker_lost=True,    # re-queue if worker dies mid-task
    worker_prefetch_multiplier=1,       # one task per worker at a time (LLM calls are slow)

    # Results expire after 24 hours — we don't need long-term task result storage
    result_expires=86400,
)


# ── Beat schedule ─────────────────────────────────────────────────────────────

celery_app.conf.beat_schedule = {

    # ── Event consumption loop ─────────────────────────────────────────────
    # Polls the event bus every 2 minutes for all agents.
    # For each agent, fetches unconsumed events it subscribes to.
    # If events exist, dispatches an agent run with an EventTrigger.
    # NOTE: replace with Supabase Realtime → webhook → task dispatch in production.
    "event-processor": {
        "task": "celery_app.process_pending_events",
        "schedule": crontab(minute="*/2"),
    },

    # ── Marketing: trend scan ──────────────────────────────────────────────
    # Every 30 minutes. Scans Reddit, X, LinkedIn for conversations relevant
    # to the product/ICP. Creates research_findings rows and notifies on spikes.
    "marketing-trend-scan": {
        "task": "celery_app.run_agent_task",
        "schedule": crontab(minute="*/30"),
        "args": ["marketing", {"type": "scheduled", "task_name": "trend_scan"}],
    },

    # ── Outreach: follow-up check ──────────────────────────────────────────
    # Every 6 hours. Looks at outreach_leads where last_contact_at is stale
    # and drafts follow-up emails (requires approval before sending).
    "outreach-followup-check": {
        "task": "celery_app.run_agent_task",
        "schedule": crontab(minute=0, hour="*/6"),
        "args": ["outreach", {"type": "scheduled", "task_name": "followup_check"}],
    },

    # ── PM: daily digest ──────────────────────────────────────────────────
    # Mon–Fri at 9am UTC. Generates a prioritized task digest from GitHub
    # issues + sprint state and sends it as a notification.
    "pm-daily-digest": {
        "task": "celery_app.run_agent_task",
        "schedule": crontab(minute=0, hour=9, day_of_week="1-5"),
        "args": ["pm", {"type": "scheduled", "task_name": "daily_digest"}],
    },

    # ── Finance: weekly summary ────────────────────────────────────────────
    # Every Monday at 9am UTC. Computes MRR delta, burn rate, runway, and
    # sends a financial health notification. Urgently notifies if runway < 3mo.
    "finance-weekly-summary": {
        "task": "celery_app.run_agent_task",
        "schedule": crontab(minute=0, hour=9, day_of_week=1),
        "args": ["finance", {"type": "scheduled", "task_name": "weekly_summary"}],
    },

    # ── Legal: deadline check ──────────────────────────────────────────────
    # Every day at 8am UTC. Scans legal_documents for deadlines within 30 days
    # and sends high-priority notifications for items within 7 days.
    "legal-deadline-check": {
        "task": "celery_app.run_agent_task",
        "schedule": crontab(minute=0, hour=8),
        "args": ["legal", {"type": "scheduled", "task_name": "deadline_check"}],
    },
}


# ── Tasks ─────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="celery_app.run_agent_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,     # 1 min initial retry delay (Celery doubles it)
)
def run_agent_task(self, agent_name: str, trigger_dict: dict) -> dict:
    """
    Generic task that instantiates any registered agent and runs it.

    This is the single dispatch point for:
      - Beat schedule entries (agent name + trigger dict)
      - Manual API triggers (POST /api/{agent}/run)
      - Approval callbacks (approval_routes._dispatch_approval_callback)
      - One-off delayed tasks scheduled by agents themselves via .apply_async()

    Args:
        agent_name:   Key in AGENT_REGISTRY (e.g. "outreach", "marketing")
        trigger_dict: Dict that deserializes into an AgentTrigger. Must include
                      at minimum {"type": "<trigger_type>"}.

    Returns:
        The dict returned by agent.run().

    Retries up to 3 times with exponential backoff on any exception.
    Skips retry for NotImplementedError (agent stub not yet built).
    """
    from app.schemas.triggers import AgentTrigger

    registry = _get_agent_registry()

    if agent_name not in registry:
        raise ValueError(
            f"Unknown agent '{agent_name}'. "
            f"Registered agents: {list(registry.keys())}"
        )

    agent_cls = registry[agent_name]
    trigger = AgentTrigger(**trigger_dict)

    logger.info("[%s] Task starting (trigger=%s)", agent_name, trigger.type)

    try:
        agent = agent_cls()
        result = agent.run(trigger)
        logger.info("[%s] Task completed. Result: %s", agent_name, result)
        return result

    except NotImplementedError as exc:
        # Agent not yet implemented — don't retry, just log and skip
        logger.info(
            "[%s] Skipped — agent not yet implemented (Prompt 4+): %s",
            agent_name, exc,
        )
        return {"status": "skipped", "reason": "not_implemented", "agent": agent_name}

    except Exception as exc:
        logger.error("[%s] Task failed: %s", agent_name, exc, exc_info=True)
        # Retry with exponential backoff (60s, 120s, 240s)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    name="celery_app.process_pending_events",
    bind=True,
    max_retries=1,
)
def process_pending_events(self) -> dict:
    """
    Event consumption loop — runs every 2 minutes via Beat.

    For each registered agent, checks whether there are unconsumed events
    it subscribes to. If yes, dispatches run_agent_task with an EventTrigger
    carrying the pending event batch.

    This fan-out pattern keeps agents decoupled: the event processor is the
    only component that knows which agents subscribe to which event types.

    In production, replace this with:
      Supabase Realtime INSERT trigger on `events` table
        → HTTP webhook → run_agent_task.delay(agent_name, event_trigger_dict)
    That gives sub-second reaction time vs. the 2-minute polling window here.
    """
    from app.core.events import get_pending_events
    from app.schemas.triggers import TriggerType

    registry = _get_agent_registry()
    dispatched: list[str] = []
    skipped: list[str] = []

    for agent_name, agent_cls in registry.items():
        subscribed = getattr(agent_cls, "subscribed_events", [])
        if not subscribed:
            # Agent doesn't subscribe to any events — nothing to check
            continue

        try:
            pending = get_pending_events(
                agent_name=agent_name,
                event_types=subscribed,
                limit=50,
            )
        except Exception as exc:
            logger.warning("[event_processor] Failed to fetch events for '%s': %s", agent_name, exc)
            skipped.append(agent_name)
            continue

        if not pending:
            continue

        logger.info(
            "[event_processor] Dispatching %d event(s) to '%s': %s",
            len(pending),
            agent_name,
            [e.event_type for e in pending],
        )

        # Serialize events to dicts for JSON transport through Redis
        events_as_dicts = [e.model_dump(mode="json") for e in pending]

        trigger_dict = {
            "type": TriggerType.EVENT,
            "events": events_as_dicts,
        }

        # Dispatch as a separate task so each agent runs independently
        run_agent_task.delay(agent_name, trigger_dict)
        dispatched.append(agent_name)

    return {
        "status": "ok",
        "dispatched_to": dispatched,
        "skipped": skipped,
    }


@celery_app.task(
    name="celery_app.schedule_delayed_agent_run",
)
def schedule_delayed_agent_run(
    agent_name: str,
    trigger_dict: dict,
    countdown_seconds: int = 0,
) -> str:
    """
    Schedule a one-off delayed agent run.

    Agents can call this to schedule future work — e.g. "check back in
    2 hours to see if the approval was granted", or "retry this outreach
    sequence in 3 days".

    Usage from inside an agent's execute():
        from celery_app import schedule_delayed_agent_run
        schedule_delayed_agent_run.apply_async(
            args=["outreach", trigger.model_dump(mode="json")],
            countdown=7200,   # 2 hours
        )

    Args:
        agent_name:        Registered agent name
        trigger_dict:      Serialized AgentTrigger dict
        countdown_seconds: Seconds to wait before dispatching (default: 0 = immediate)

    Returns:
        The Celery task ID of the dispatched run_agent_task.
    """
    task = run_agent_task.apply_async(
        args=[agent_name, trigger_dict],
        countdown=countdown_seconds,
    )
    logger.info(
        "Scheduled delayed run for '%s' in %ds — task_id=%s",
        agent_name, countdown_seconds, task.id,
    )
    return task.id
