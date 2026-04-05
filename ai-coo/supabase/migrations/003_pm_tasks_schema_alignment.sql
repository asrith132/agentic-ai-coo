-- 003_pm_tasks_schema_alignment.sql
--
-- Run this if pm_tasks was created from an older 002 snapshot and PostgREST
-- errors with: Could not find the 'effort_points' column (PGRST204).
-- Safe to run multiple times (IF NOT EXISTS).
--
-- In Supabase: SQL Editor → paste → Run.
-- Or: supabase db push (if linked).

ALTER TABLE pm_milestones
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now();

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS source_event_type TEXT;

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS impact_area TEXT DEFAULT 'product';

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS urgency TEXT DEFAULT 'medium';

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS effort_points INT DEFAULT 3;

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS is_revenue_generating BOOLEAN DEFAULT false;

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS is_cost_saving BOOLEAN DEFAULT false;

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS is_compliance_related BOOLEAN DEFAULT false;

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS is_customer_requested BOOLEAN DEFAULT false;

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS due_date DATE;

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

ALTER TABLE pm_tasks
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now();

-- Optional: ensure pm_task_dependencies exists (no-op if already applied from 002)
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
