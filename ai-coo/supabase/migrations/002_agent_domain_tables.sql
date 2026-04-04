-- 002_agent_domain_tables.sql — Per-agent private domain tables
--
-- Each agent owns its own tables and reads/writes them exclusively.
-- Cross-agent knowledge sharing happens only through the event bus (events table).
--
-- Run after 001_core_tables.sql.
-- Apply via Supabase dashboard SQL editor or: supabase db push


-- ═══════════════════════════════════════════════════════════════════════════
-- DEV ACTIVITY AGENT
-- Tracks GitHub commits, derived features, and CI/build state.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS dev_commits (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    sha                 TEXT        NOT NULL,
    message             TEXT,
    author              TEXT,
    timestamp           TIMESTAMP,
    branch              TEXT        DEFAULT 'main',
    parsed_summary      TEXT,           -- LLM-generated one-sentence business summary
    features_referenced TEXT[],         -- feature names extracted from commit message/diff
    created_at          TIMESTAMP   DEFAULT now()
);

-- Avoid re-inserting the same commit on repeated polls
CREATE UNIQUE INDEX IF NOT EXISTS idx_dev_commits_sha
    ON dev_commits (sha);

-- Recent commits by branch, newest first
CREATE INDEX IF NOT EXISTS idx_dev_commits_branch_ts
    ON dev_commits (branch, timestamp DESC);


CREATE TABLE IF NOT EXISTS dev_features (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    feature_name    TEXT        NOT NULL,
    description     TEXT,
    status          TEXT        DEFAULT 'shipped'
                                CHECK (status IN ('shipped', 'in_progress', 'deprecated')),
    shipped_at      TIMESTAMP,
    related_commits TEXT[],         -- array of SHAs that contributed to this feature
    created_at      TIMESTAMP   DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_dev_features_name
    ON dev_features (feature_name);

CREATE INDEX IF NOT EXISTS idx_dev_features_status
    ON dev_features (status);


-- ═══════════════════════════════════════════════════════════════════════════
-- OUTREACH AGENT
-- Manages contacts, email threads, and outreach templates.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS outreach_contacts (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT        NOT NULL,
    email               TEXT,
    company             TEXT,
    role                TEXT,
    contact_type        TEXT        DEFAULT 'customer'
                                    CHECK (contact_type IN ('customer', 'investor', 'partner', 'press')),
    status              TEXT        DEFAULT 'cold'
                                    CHECK (status IN ('cold', 'warm', 'responded', 'converted')),
    source              TEXT,           -- 'manual' | 'research_agent' | 'linkedin' | 'referral'
    research_cache      JSONB       DEFAULT '{}',   -- LinkedIn data, recent posts, company info
    notes               TEXT,
    last_contacted_at   TIMESTAMP,
    next_followup_at    TIMESTAMP,
    created_at          TIMESTAMP   DEFAULT now()
);

-- Email uniqueness (nullable — some contacts may not have email yet)
CREATE UNIQUE INDEX IF NOT EXISTS idx_outreach_contacts_email
    ON outreach_contacts (email)
    WHERE email IS NOT NULL;

-- Dashboard queries: contacts by status
CREATE INDEX IF NOT EXISTS idx_outreach_contacts_status
    ON outreach_contacts (status, created_at DESC);

-- Overdue follow-up queue
CREATE INDEX IF NOT EXISTS idx_outreach_contacts_followup
    ON outreach_contacts (next_followup_at)
    WHERE next_followup_at IS NOT NULL AND status NOT IN ('responded', 'converted');


CREATE TABLE IF NOT EXISTS outreach_messages (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id      UUID        REFERENCES outreach_contacts(id) ON DELETE CASCADE,
    direction       TEXT        NOT NULL
                                CHECK (direction IN ('sent', 'received')),
    subject         TEXT,
    body            TEXT        NOT NULL,
    channel         TEXT        DEFAULT 'email'
                                CHECK (channel IN ('email', 'linkedin', 'twitter')),
    status          TEXT        DEFAULT 'draft'
                                CHECK (status IN (
                                    'draft', 'pending_approval', 'sent',
                                    'delivered', 'opened', 'replied'
                                )),
    template_used   TEXT,
    approval_id     UUID,           -- links to approvals table when status='pending_approval'
    sent_at         TIMESTAMP,
    created_at      TIMESTAMP   DEFAULT now()
);

-- Message history per contact, newest first
CREATE INDEX IF NOT EXISTS idx_outreach_messages_contact
    ON outreach_messages (contact_id, created_at DESC);

-- Pending approval queue
CREATE INDEX IF NOT EXISTS idx_outreach_messages_pending
    ON outreach_messages (status)
    WHERE status = 'pending_approval';


CREATE TABLE IF NOT EXISTS outreach_templates (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT        NOT NULL,
    contact_type        TEXT,           -- which contact_type this template targets
    subject_template    TEXT,
    body_template       TEXT,
    -- follow_up_sequence: [{delay_days: int, subject: str, body: str}, ...]
    follow_up_sequence  JSONB       DEFAULT '[]',
    -- performance: {sent: int, opened: int, replied: int}
    performance         JSONB       DEFAULT '{}',
    created_at          TIMESTAMP   DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_outreach_templates_name
    ON outreach_templates (name);


-- ═══════════════════════════════════════════════════════════════════════════
-- MARKETING AGENT
-- Stores found trends and drafted/published content.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS marketing_trends (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    platform            TEXT        NOT NULL
                                    CHECK (platform IN ('reddit', 'twitter', 'linkedin', 'hackernews', 'other')),
    topic               TEXT        NOT NULL,
    url                 TEXT,
    relevance_score     FLOAT,          -- 0.0–1.0, agent-assigned
    original_content    TEXT,           -- the raw post/thread that was found
    suggested_action    TEXT
                                    CHECK (suggested_action IN ('reply', 'post', 'ignore')),
    status              TEXT        DEFAULT 'found'
                                    CHECK (status IN ('found', 'drafted', 'approved', 'published', 'ignored')),
    draft_content       TEXT,           -- the agent-drafted reply or post
    approval_id         UUID,           -- links to approvals table
    found_at            TIMESTAMP   DEFAULT now()
);

-- Active (non-ignored) trends by platform, newest first
CREATE INDEX IF NOT EXISTS idx_marketing_trends_platform_status
    ON marketing_trends (platform, status, found_at DESC);

CREATE INDEX IF NOT EXISTS idx_marketing_trends_status
    ON marketing_trends (status)
    WHERE status IN ('found', 'drafted');


CREATE TABLE IF NOT EXISTS marketing_content (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    platform        TEXT        NOT NULL,
    content_type    TEXT
                                CHECK (content_type IN ('reply', 'post', 'thread', 'article')),
    body            TEXT        NOT NULL,
    status          TEXT        DEFAULT 'draft'
                                CHECK (status IN ('draft', 'scheduled', 'published')),
    published_url   TEXT,
    -- engagement: {likes: int, comments: int, shares: int, impressions: int}
    engagement      JSONB       DEFAULT '{}',
    scheduled_for   TIMESTAMP,
    published_at    TIMESTAMP,
    created_at      TIMESTAMP   DEFAULT now()
);

-- Content calendar view: scheduled items
CREATE INDEX IF NOT EXISTS idx_marketing_content_scheduled
    ON marketing_content (scheduled_for)
    WHERE status = 'scheduled';

-- Published history
CREATE INDEX IF NOT EXISTS idx_marketing_content_published
    ON marketing_content (published_at DESC)
    WHERE status = 'published';


-- ═══════════════════════════════════════════════════════════════════════════
-- FINANCE AGENT
-- Stores parsed transactions and monthly snapshots.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS finance_transactions (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE        NOT NULL,
    description     TEXT        NOT NULL,
    amount          DECIMAL(12,2) NOT NULL,     -- negative = expense, positive = income
    category        TEXT
                                CHECK (category IN (
                                    'hosting', 'tools', 'contractors', 'marketing',
                                    'salary', 'revenue', 'tax', 'legal', 'other'
                                )),
    subcategory     TEXT,
    is_recurring    BOOLEAN     DEFAULT false,
    source          TEXT        DEFAULT 'csv'
                                CHECK (source IN ('csv', 'manual', 'plaid')),
    notes           TEXT,
    created_at      TIMESTAMP   DEFAULT now()
);

-- Date range queries
CREATE INDEX IF NOT EXISTS idx_finance_transactions_date
    ON finance_transactions (date DESC);

-- Category breakdown queries
CREATE INDEX IF NOT EXISTS idx_finance_transactions_category
    ON finance_transactions (category, date DESC);

-- Recurring cost analysis
CREATE INDEX IF NOT EXISTS idx_finance_transactions_recurring
    ON finance_transactions (is_recurring, category)
    WHERE is_recurring = true;


CREATE TABLE IF NOT EXISTS finance_snapshots (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    month           DATE        NOT NULL,           -- always first day of month (e.g. 2025-01-01)
    total_income    DECIMAL(12,2) DEFAULT 0,
    total_expenses  DECIMAL(12,2) DEFAULT 0,
    net             DECIMAL(12,2) DEFAULT 0,         -- total_income - total_expenses
    -- by_category: {hosting: 1100.00, tools: 500.00, salary: 8000.00, ...}
    by_category     JSONB       DEFAULT '{}',
    runway_months   FLOAT,
    current_balance DECIMAL(12,2),
    created_at      TIMESTAMP   DEFAULT now()
);

-- One snapshot per month
CREATE UNIQUE INDEX IF NOT EXISTS idx_finance_snapshots_month
    ON finance_snapshots (month);


-- ═══════════════════════════════════════════════════════════════════════════
-- PM AGENT
-- Task backlog, milestones, and priority reshuffle history.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS pm_milestones (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    description     TEXT,
    target_date     DATE,
    status          TEXT        DEFAULT 'active'
                                CHECK (status IN ('active', 'completed', 'at_risk')),
    completed_at    TIMESTAMP,
    created_at      TIMESTAMP   DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pm_milestones_status
    ON pm_milestones (status, target_date);


CREATE TABLE IF NOT EXISTS pm_tasks (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT        NOT NULL,
    description     TEXT,
    status          TEXT        DEFAULT 'todo'
                                CHECK (status IN ('todo', 'in_progress', 'done', 'blocked')),
    priority_score  FLOAT       DEFAULT 50      -- 0–100; higher = more important
                                CHECK (priority_score BETWEEN 0 AND 100),
    priority_reason TEXT,           -- LLM-generated explanation of the score
    source_agent    TEXT,           -- agent that created the task, or "user"
    source_event_id UUID,           -- event that triggered creation (foreign key not enforced to keep loose coupling)
    milestone_id    UUID        REFERENCES pm_milestones(id) ON DELETE SET NULL,
    assigned_to     TEXT,
    due_date        DATE,
    completed_at    TIMESTAMP,
    created_at      TIMESTAMP   DEFAULT now(),
    updated_at      TIMESTAMP   DEFAULT now()
);

-- Priority-sorted backlog (main dashboard query)
CREATE INDEX IF NOT EXISTS idx_pm_tasks_priority
    ON pm_tasks (priority_score DESC, status)
    WHERE status NOT IN ('done');

-- Status filter + recency
CREATE INDEX IF NOT EXISTS idx_pm_tasks_status
    ON pm_tasks (status, updated_at DESC);

-- Blocked tasks surfaced immediately
CREATE INDEX IF NOT EXISTS idx_pm_tasks_blocked
    ON pm_tasks (status)
    WHERE status = 'blocked';

-- Milestone progress rollup
CREATE INDEX IF NOT EXISTS idx_pm_tasks_milestone
    ON pm_tasks (milestone_id, status)
    WHERE milestone_id IS NOT NULL;

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION pm_tasks_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pm_tasks_updated_at
    BEFORE UPDATE ON pm_tasks
    FOR EACH ROW EXECUTE FUNCTION pm_tasks_set_updated_at();


CREATE TABLE IF NOT EXISTS pm_priority_history (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMP   DEFAULT now(),
    trigger_event   TEXT,           -- what caused the reshuffle (e.g. "dev.build_failed", "user request")
    -- previous_top_3: [{task_id: uuid, title: str, score: float}, ...]
    previous_top_3  JSONB,
    -- new_top_3: same shape
    new_top_3       JSONB,
    reasoning       TEXT            -- LLM-generated explanation of the reprioritization
);

CREATE INDEX IF NOT EXISTS idx_pm_priority_history_ts
    ON pm_priority_history (timestamp DESC);


-- ═══════════════════════════════════════════════════════════════════════════
-- RESEARCH AGENT
-- Stores research reports and a query result cache.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS research_reports (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    query               TEXT        NOT NULL,
    requesting_agent    TEXT,           -- which agent triggered this, or "user"
    report_type         TEXT        DEFAULT 'general'
                                    CHECK (report_type IN (
                                        'general', 'competitor', 'market',
                                        'investor', 'technical'
                                    )),
    -- findings: [{title: str, summary: str, source_url: str, relevance: float}, ...]
    findings            JSONB       DEFAULT '[]',
    executive_summary   TEXT,
    -- sources: [{url: str, title: str, accessed_at: str}, ...]
    sources             JSONB       DEFAULT '[]',
    status              TEXT        DEFAULT 'completed'
                                    CHECK (status IN ('pending', 'in_progress', 'completed', 'failed')),
    created_at          TIMESTAMP   DEFAULT now()
);

-- Report list by type and recency
CREATE INDEX IF NOT EXISTS idx_research_reports_type
    ON research_reports (report_type, created_at DESC);

-- In-progress reports for status polling
CREATE INDEX IF NOT EXISTS idx_research_reports_status
    ON research_reports (status)
    WHERE status IN ('pending', 'in_progress');


CREATE TABLE IF NOT EXISTS research_cache (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    query_hash      TEXT        NOT NULL UNIQUE,    -- SHA-256 of normalized query string
    query           TEXT        NOT NULL,
    result          JSONB       NOT NULL,
    expires_at      TIMESTAMP,
    created_at      TIMESTAMP   DEFAULT now()
);

-- Expiry cleanup query
CREATE INDEX IF NOT EXISTS idx_research_cache_expires
    ON research_cache (expires_at)
    WHERE expires_at IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════════════════
-- LEGAL AGENT
-- Compliance checklist items and drafted legal documents.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS legal_checklist (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    item            TEXT        NOT NULL,
    description     TEXT,
    category        TEXT
                                CHECK (category IN (
                                    'incorporation', 'tax', 'compliance',
                                    'ip', 'contracts', 'employment', 'privacy'
                                )),
    status          TEXT        DEFAULT 'pending'
                                CHECK (status IN ('pending', 'in_progress', 'done', 'overdue')),
    due_date        DATE,
    priority        TEXT        DEFAULT 'medium'
                                CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    document_url    TEXT,           -- link to the drafted/finalized document
    notes           TEXT,
    created_at      TIMESTAMP   DEFAULT now(),
    updated_at      TIMESTAMP   DEFAULT now()
);

-- Deadline monitor: items due within N days
CREATE INDEX IF NOT EXISTS idx_legal_checklist_due_date
    ON legal_checklist (due_date)
    WHERE status NOT IN ('done') AND due_date IS NOT NULL;

-- Status + category dashboard
CREATE INDEX IF NOT EXISTS idx_legal_checklist_status
    ON legal_checklist (status, category);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION legal_checklist_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER legal_checklist_updated_at
    BEFORE UPDATE ON legal_checklist
    FOR EACH ROW EXECUTE FUNCTION legal_checklist_set_updated_at();


CREATE TABLE IF NOT EXISTS legal_documents (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_type       TEXT        NOT NULL
                                    CHECK (document_type IN (
                                        'privacy_policy', 'tos', 'contractor_agreement',
                                        'nda', 'employee_agreement', 'ip_assignment',
                                        'incorporation', 'other'
                                    )),
    title               TEXT        NOT NULL,
    content             TEXT,           -- full drafted document text
    status              TEXT        DEFAULT 'draft'
                                    CHECK (status IN ('draft', 'review', 'final')),
    checklist_item_id   UUID        REFERENCES legal_checklist(id) ON DELETE SET NULL,
    approval_id         UUID,           -- links to approvals table if pending review
    created_at          TIMESTAMP   DEFAULT now(),
    updated_at          TIMESTAMP   DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_legal_documents_type_status
    ON legal_documents (document_type, status);

CREATE INDEX IF NOT EXISTS idx_legal_documents_checklist_item
    ON legal_documents (checklist_item_id)
    WHERE checklist_item_id IS NOT NULL;

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION legal_documents_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER legal_documents_updated_at
    BEFORE UPDATE ON legal_documents
    FOR EACH ROW EXECUTE FUNCTION legal_documents_set_updated_at();
