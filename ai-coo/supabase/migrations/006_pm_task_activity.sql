-- 006_pm_task_activity.sql
--
-- Lightweight audit trail for PM task lifecycle (created, started, completed, blocked, etc.).
-- Supabase: SQL Editor → paste → Run. Safe to run multiple times (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS pm_task_activity (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID NOT NULL REFERENCES pm_tasks(id) ON DELETE CASCADE,
    milestone_id  UUID,
    agent_name    TEXT,
    action_type   TEXT NOT NULL,
    old_status    TEXT,
    new_status    TEXT,
    note          TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pm_task_activity_task_created
    ON pm_task_activity (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pm_task_activity_action_created
    ON pm_task_activity (action_type, created_at DESC);
