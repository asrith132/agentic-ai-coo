# AI COO — Multi-Agent Autonomous Operations System

A multi-agent system that runs your startup's operational functions autonomously using Claude AI.

## Agents

| Agent | Domain | Triggers |
|-------|--------|---------|
| **Dev Activity** | GitHub PRs, CI, issues | Every 30m + webhooks |
| **Outreach** | Cold email campaigns, reply tracking | Every 2h |
| **Marketing** | Reddit, X, LinkedIn content | Daily |
| **Finance** | MRR, runway, expenses | Daily |
| **PM** | Sprint health, blockers, velocity | Every 6h |
| **Research** | Competitors, trends, leads | Every 12h |
| **Legal** | Contracts, compliance signals | Daily |

## Architecture

```
Next.js Frontend
      │  REST + Supabase Realtime
      ▼
FastAPI Backend (this repo)
      │
      ├─ core/context.py     Global context read/write
      ├─ core/events.py      Event bus (emit + consume)
      ├─ core/approvals.py   Human-in-the-loop approval queue
      └─ core/notifications.py  Push notifications
      │
      ▼
Celery Workers (one task per agent)
      │
      ▼
Supabase (PostgreSQL + Realtime + Storage)
Redis (Celery broker + result backend)
```

## Quick Start

### 1. Install dependencies

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your real credentials
```

### 3. Apply database migrations

Run in the Supabase SQL editor:
1. `supabase/migrations/001_core_tables.sql`
2. `supabase/migrations/002_agent_domain_tables.sql`

### 4. Seed global context

```bash
python ../scripts/seed_global_context.py
```

### 5. Start the API server

```bash
uvicorn app.main:app --reload
```

### 6. Start Celery worker + beat

```bash
# Worker (in a separate terminal)
celery -A celery_app worker --loglevel=info

# Beat scheduler (in a separate terminal)
celery -A celery_app beat --loglevel=info
```

### 7. Test the event cascade

```bash
python ../scripts/test_cascade.py
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/context/global` | GET | Read global business context |
| `/api/context/global` | PATCH | Update global context fields |
| `/api/events` | GET | List recent events |
| `/api/events/emit` | POST | Emit a test event |
| `/api/approvals` | GET | List pending approvals |
| `/api/approvals/{id}/respond` | POST | Approve or reject |
| `/api/notifications` | GET | List notifications |
| `/api/{agent}/run` | POST | Manually trigger an agent |
| `/api/{agent}/status` | GET | Agent run status |
| `/health` | GET | Health check |

## Project Structure

See `docs/AGENT_GUIDE.md` for how to build or extend agents.
