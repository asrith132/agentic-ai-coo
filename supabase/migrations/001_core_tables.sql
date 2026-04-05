-- 001_core_tables.sql — Shared infrastructure tables
--
-- Run this in the Supabase SQL editor or via `supabase db push`.
-- Creates: global_context, events, approvals, notifications
-- Enables Realtime on: events, approvals, notifications


-- ── Global Context ────────────────────────────────────────────────────────────
-- Single row, versioned. Every agent reads this at the start of each run.
-- Stores shared business knowledge that all agents need: company profile,
-- target customer, current business state, brand voice, competitive landscape.

CREATE TABLE IF NOT EXISTS global_context (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_profile      JSONB       DEFAULT '{}',
    target_customer      JSONB       DEFAULT '{}',
    business_state       JSONB       DEFAULT '{}',
    brand_voice          JSONB       DEFAULT '{}',
    competitive_landscape JSONB      DEFAULT '{}',
    recent_events        JSONB       DEFAULT '[]',
    version              INT         DEFAULT 1,
    updated_at           TIMESTAMP   DEFAULT now()
);

-- Trigger: auto-update updated_at on every write
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER global_context_updated_at
    BEFORE UPDATE ON global_context
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── Event Bus ─────────────────────────────────────────────────────────────────
-- Append-only log. Agents emit events here; other agents poll for unconsumed ones.
-- consumed_by tracks which agents have already processed each event.
-- Supabase Realtime broadcasts INSERTs so agents can react immediately.

CREATE TABLE IF NOT EXISTS events (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp    TIMESTAMP   DEFAULT now(),
    source_agent TEXT        NOT NULL,
    event_type   TEXT        NOT NULL,
    payload      JSONB       DEFAULT '{}',
    summary      TEXT        NOT NULL,
    priority     TEXT        DEFAULT 'medium'
                             CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    consumed_by  TEXT[]      DEFAULT '{}'
);

-- Fast query: "give me all events of type X not yet consumed by agent Y"
CREATE INDEX IF NOT EXISTS idx_events_unconsumed
    ON events (event_type, timestamp DESC);

-- Index for filtering by source agent
CREATE INDEX IF NOT EXISTS idx_events_source_agent
    ON events (source_agent, timestamp DESC);


-- ── Approvals Queue ───────────────────────────────────────────────────────────
-- Agents request human sign-off here before taking sensitive actions.
-- Frontend polls this table and displays pending items for the user to act on.

CREATE TABLE IF NOT EXISTS approvals (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent        TEXT        NOT NULL,
    action_type  TEXT        NOT NULL,
    content      JSONB       NOT NULL,
    status       TEXT        DEFAULT 'pending'
                             CHECK (status IN ('pending', 'approved', 'rejected')),
    user_edits   JSONB,
    created_at   TIMESTAMP   DEFAULT now(),
    resolved_at  TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_approvals_pending
    ON approvals (status, created_at DESC)
    WHERE status = 'pending';


-- ── Notifications ─────────────────────────────────────────────────────────────
-- Agents push updates here for the frontend notification bell.
-- High-priority notifications can also trigger Twilio SMS (handled in Python).

CREATE TABLE IF NOT EXISTS notifications (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent      TEXT        NOT NULL,
    title      TEXT        NOT NULL,
    body       TEXT        NOT NULL,
    priority   TEXT        DEFAULT 'medium'
                           CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    read       BOOLEAN     DEFAULT false,
    created_at TIMESTAMP   DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_unread
    ON notifications (read, created_at DESC)
    WHERE read = false;


-- ── Supabase Realtime ─────────────────────────────────────────────────────────
-- Enable broadcast on INSERT for the three tables the frontend subscribes to.
-- Run in Supabase dashboard: Database → Replication → enable these tables.
-- (The ALTER PUBLICATION syntax is Supabase-specific)

ALTER PUBLICATION supabase_realtime ADD TABLE events;
ALTER PUBLICATION supabase_realtime ADD TABLE approvals;
ALTER PUBLICATION supabase_realtime ADD TABLE notifications;
