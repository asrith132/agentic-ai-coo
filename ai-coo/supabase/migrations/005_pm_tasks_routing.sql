-- 005_pm_tasks_routing.sql
-- Agent-facing routing fields for pm_tasks (decomposition target_agent / task_type).
-- Safe to run multiple times (IF NOT EXISTS).

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS target_agent TEXT;

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS task_type TEXT;

CREATE INDEX IF NOT EXISTS idx_pm_tasks_target_agent
    ON pm_tasks (target_agent)
    WHERE target_agent IS NOT NULL;
