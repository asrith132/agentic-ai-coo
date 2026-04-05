# Agent Development Guide

This guide explains how to build a new agent or extend an existing one.

## Architecture Overview

```
FastAPI (HTTP layer)
    │
    ▼
Celery Tasks (agent workers)
    │
    ├── reads  ──▶ Global Context (Supabase: global_context)
    ├── reads  ──▶ Event Bus     (Supabase: events)
    ├── writes ──▶ Domain Tables (Supabase: per-agent tables)
    ├── emits  ──▶ Event Bus     (triggers other agents)
    ├── queues ──▶ Approval Queue (Supabase: approvals)
    └── pushes ──▶ Notifications  (Supabase: notifications)
```

Agents **never call each other directly**. All cross-agent communication happens
through events on the event bus.

---

## Creating a New Agent

### 1. Create the agent directory

```
app/agents/my_agent/
├── __init__.py
├── agent.py      # MyAgent(BaseAgent)
└── tools.py      # domain-specific helpers
```

### 2. Subclass BaseAgent (Prompt 2)

```python
# app/agents/my_agent/agent.py

from app.core.base_agent import BaseAgent

class MyAgent(BaseAgent):
    name = "my_agent"
    description = "What this agent does"

    async def run(self, trigger: dict) -> None:
        # 1. Read global context
        ctx = await self.get_context()

        # 2. Do work using tools
        result = await some_tool()

        # 3. Update domain table
        await self.save_domain_state(result)

        # 4. Emit events for other agents
        await self.emit(
            event_type="my_agent.thing_happened",
            payload={"key": "value"},
            summary="Thing happened because of X",
        )

        # 5. Notify user if relevant
        await self.notify("Thing happened", body="Details here", priority="medium")
```

### 3. Add a Celery task

```python
# app/agents/my_agent/tasks.py

from celery_app import celery_app
from app.agents.my_agent.agent import MyAgent

@celery_app.task(bind=True, max_retries=3)
def run_my_agent_task(self, trigger: dict):
    import asyncio
    agent = MyAgent()
    asyncio.run(agent.run(trigger))
```

### 4. Register in celery_app.py

Add to the `include` list:
```python
"app.agents.my_agent.tasks",
```

Add a beat schedule entry if the agent should run on a schedule.

### 5. Add an API route

```python
# app/api/agents/my_agent.py
from fastapi import APIRouter
from app.agents.my_agent.tasks import run_my_agent_task

router = APIRouter(prefix="/api/my-agent", tags=["my-agent"])

@router.post("/run")
async def run():
    task = run_my_agent_task.delay({"type": "user", "agent": "my_agent", "params": {}})
    return {"status": "queued", "task_id": task.id}
```

Include the router in `main.py`.

---

## Event Naming Convention

Format: `<agent_name>.<past_tense_action>`

| Agent | Event types |
|-------|-------------|
| dev_activity | `dev.pr_merged`, `dev.build_failed`, `dev.issue_opened` |
| outreach | `outreach.email_sent`, `outreach.reply_received`, `outreach.meeting_booked` |
| marketing | `marketing.post_published`, `marketing.engagement_spike` |
| finance | `finance.mrr_changed`, `finance.runway_updated`, `finance.expense_spike` |
| pm | `pm.sprint_started`, `pm.blocker_detected`, `pm.sprint_completed` |
| research | `research.competitor_found`, `research.trend_found`, `research.lead_found` |
| legal | `legal.contract_flagged`, `legal.compliance_alert` |

---

## Approval Gate Pattern

For sensitive actions (send email, publish post, make payment):

```python
# 1. Request approval — returns immediately
approval = await self.request_approval(
    action_type="send_email",
    content={"to": "lead@example.com", "subject": "...", "body": "..."},
)

# 2. Wait for decision (poll in a retry loop or use Celery chord)
for _ in range(30):  # wait up to 30 minutes
    status = await self.get_approval_status(approval.id)
    if status.status == "approved":
        content = status.user_edits or status.content
        await send_email(**content)
        break
    elif status.status == "rejected":
        break
    await asyncio.sleep(60)
```

---

## Global Context Fields

| Field | Owner | Updated by |
|-------|-------|------------|
| `company_profile` | User / all agents | Manual or startup |
| `target_customer` | User | Manual |
| `business_state` | Finance + Dev agents | FinanceAgent, DevActivityAgent |
| `brand_voice` | User | Manual |
| `competitive_landscape` | Research agent | ResearchAgent |
| `recent_events` | Event bus | Auto-populated rolling list |

Only update fields your agent "owns". Use `patch_global_context()` with only
the keys you're changing — never overwrite the whole row.
