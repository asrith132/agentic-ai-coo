-- PM voice: structured project intake + generated tasks (JSONB), keyed in app as pm_voice_intake

ALTER TABLE global_context
ADD COLUMN IF NOT EXISTS pm_voice_intake JSONB NOT NULL DEFAULT '{}'::jsonb;
