-- 004_pm_task_dependencies.sql
--
-- Use when PostgREST returns PGRST205: table public.pm_task_dependencies not found.
-- Safe to run multiple times (IF NOT EXISTS).
--
-- Supabase: SQL Editor → paste → Run. Then wait a few seconds or reload schema if needed.

CREATE TABLE IF NOT EXISTS pm_task_dependencies (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id             UUID NOT NULL REFERENCES pm_tasks(id) ON DELETE CASCADE,
    depends_on_task_id  UUID NOT NULL REFERENCES pm_tasks(id) ON DELETE CASCADE,
    created_at          TIMESTAMP DEFAULT now(),
    CONSTRAINT pm_task_dependencies_no_self_dependency
        CHECK (task_id <> depends_on_task_id),
    CONSTRAINT pm_task_dependencies_unique
        UNIQUE (task_id, depends_on_task_id)
);

CREATE INDEX IF NOT EXISTS idx_pm_task_dependencies_task
    ON pm_task_dependencies (task_id);

CREATE INDEX IF NOT EXISTS idx_pm_task_dependencies_depends_on
    ON pm_task_dependencies (depends_on_task_id);
