-- 003_marketing_trends.sql — Add marketing_trends table for trend scanning
--
-- Stores social media posts/threads found by the marketing agent's trend scanner.
-- High-relevance trends trigger content drafting workflows.

CREATE TABLE IF NOT EXISTS marketing_trends (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    platform        TEXT        NOT NULL,       -- 'reddit' | 'x' | 'linkedin'
    url             TEXT,
    author          TEXT,
    post_content    TEXT        NOT NULL,
    topic           TEXT,
    relevance_score INT         NOT NULL CHECK (relevance_score BETWEEN 0 AND 100),
    relevance_reason TEXT,
    suggested_action TEXT,                       -- 'reply' | 'quote' | 'new_post'
    actioned        BOOLEAN     DEFAULT false,
    created_at      TIMESTAMP   DEFAULT now()
);

-- Add topic and trend_id columns to marketing_posts for linking content to trends
ALTER TABLE marketing_posts
    ADD COLUMN IF NOT EXISTS topic       TEXT,
    ADD COLUMN IF NOT EXISTS content_type TEXT,  -- 'announcement' | 'reply' | 'thought_leadership' | 'engagement'
    ADD COLUMN IF NOT EXISTS trend_id    UUID REFERENCES marketing_trends(id),
    ADD COLUMN IF NOT EXISTS approval_id UUID,
    ADD COLUMN IF NOT EXISTS published_url TEXT;
