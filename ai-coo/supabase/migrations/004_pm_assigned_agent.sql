-- Add assigned_agent column to pm_tasks
-- This records which specialist agent should execute the task when approved.

ALTER TABLE pm_tasks ADD COLUMN IF NOT EXISTS assigned_agent text;
