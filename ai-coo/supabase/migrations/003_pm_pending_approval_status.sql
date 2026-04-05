-- Migration 003: Add 'pending_approval' to pm_tasks status enum
--
-- PM tasks created proactively by the agent start in 'pending_approval'
-- and wait for user acceptance before transitioning to 'in_progress'.

ALTER TABLE pm_tasks
    DROP CONSTRAINT IF EXISTS pm_tasks_status_check;

ALTER TABLE pm_tasks
    ADD CONSTRAINT pm_tasks_status_check
    CHECK (status IN ('pending_approval', 'todo', 'in_progress', 'done', 'blocked'));
