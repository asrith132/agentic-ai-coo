-- 002_agent_domain_tables.sql — Per-agent private domain tables
--
-- Each agent has its own table(s) for private state that is not shared with
-- other agents via global context. Agents read/write their own domain tables
-- directly; they share knowledge with other agents only by emitting events.


-- ── Dev Activity Agent ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dev_agent_state (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    last_run_at     TIMESTAMP,
    last_pr_sha     TEXT,           -- last PR SHA processed (for deduplication)
    open_prs        JSONB       DEFAULT '[]',
    recent_commits  JSONB       DEFAULT '[]',
    ci_status       TEXT,           -- 'passing' | 'failing' | 'pending'
    summary         TEXT,
    updated_at      TIMESTAMP   DEFAULT now()
);


-- ── Outreach Agent ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS outreach_leads (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT        UNIQUE NOT NULL,
    name            TEXT,
    company         TEXT,
    role            TEXT,
    source          TEXT,           -- 'manual' | 'research_agent' | 'linkedin'
    status          TEXT        DEFAULT 'new'
                                CHECK (status IN ('new', 'contacted', 'replied', 'booked', 'dead')),
    last_contact_at TIMESTAMP,
    notes           TEXT,
    created_at      TIMESTAMP   DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outreach_emails (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID        REFERENCES outreach_leads(id),
    subject         TEXT        NOT NULL,
    body            TEXT        NOT NULL,
    direction       TEXT        CHECK (direction IN ('sent', 'received')),
    gmail_thread_id TEXT,
    sent_at         TIMESTAMP,
    created_at      TIMESTAMP   DEFAULT now()
);


-- ── Marketing Agent ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS marketing_posts (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    platform        TEXT        NOT NULL,   -- 'reddit' | 'x' | 'linkedin'
    content         TEXT        NOT NULL,
    status          TEXT        DEFAULT 'draft'
                                CHECK (status IN ('draft', 'pending_approval', 'published', 'rejected')),
    platform_post_id TEXT,
    likes           INT         DEFAULT 0,
    comments        INT         DEFAULT 0,
    shares          INT         DEFAULT 0,
    published_at    TIMESTAMP,
    created_at      TIMESTAMP   DEFAULT now()
);


-- ── Finance Agent ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS finance_snapshots (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date   DATE        NOT NULL,
    mrr             NUMERIC(12, 2),
    arr             NUMERIC(12, 2),
    cash_balance    NUMERIC(12, 2),
    monthly_burn    NUMERIC(12, 2),
    runway_months   NUMERIC(5, 1),
    notes           TEXT,
    created_at      TIMESTAMP   DEFAULT now()
);


-- ── PM Agent ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pm_sprints (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    sprint_number   INT         NOT NULL,
    goal            TEXT,
    start_date      DATE,
    end_date        DATE,
    status          TEXT        DEFAULT 'active'
                                CHECK (status IN ('planning', 'active', 'completed')),
    velocity        NUMERIC(5, 1),
    blockers        JSONB       DEFAULT '[]',
    summary         TEXT,
    created_at      TIMESTAMP   DEFAULT now()
);


-- ── Research Agent ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS research_findings (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_type    TEXT        NOT NULL,   -- 'competitor' | 'trend' | 'lead' | 'news'
    title           TEXT        NOT NULL,
    content         JSONB       NOT NULL,
    source_url      TEXT,
    relevance_score NUMERIC(3, 2),          -- 0.0 to 1.0
    actioned        BOOLEAN     DEFAULT false,
    created_at      TIMESTAMP   DEFAULT now()
);


-- ── Legal Agent ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS legal_documents (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_name   TEXT        NOT NULL,
    document_type   TEXT,                   -- 'contract' | 'nda' | 'tos' | 'privacy'
    storage_path    TEXT,                   -- Supabase Storage path
    risk_level      TEXT        CHECK (risk_level IN ('low', 'medium', 'high')),
    flagged_clauses JSONB       DEFAULT '[]',
    summary         TEXT,
    reviewed_at     TIMESTAMP,
    created_at      TIMESTAMP   DEFAULT now()
);
