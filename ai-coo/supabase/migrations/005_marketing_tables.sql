-- Marketing agent tables

CREATE TABLE IF NOT EXISTS marketing_trends (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    platform      text NOT NULL DEFAULT 'linkedin',
    url           text,
    author        text,
    post_content  text NOT NULL DEFAULT '',
    topic         text NOT NULL DEFAULT '',
    relevance_score integer NOT NULL DEFAULT 0,
    relevance_reason text NOT NULL DEFAULT '',
    suggested_action text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS marketing_posts (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    platform         text NOT NULL DEFAULT 'linkedin',
    content          text NOT NULL DEFAULT '',
    content_type     text,
    topic            text NOT NULL DEFAULT '',
    trend_id         uuid REFERENCES marketing_trends(id) ON DELETE SET NULL,
    status           text NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft','pending_approval','published','rejected')),
    approval_id      uuid,
    platform_post_id text,
    published_url    text,
    published_at     timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
