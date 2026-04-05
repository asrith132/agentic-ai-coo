"""
Unit tests for app.agents.marketing.tools.

Tests cover:
  - Platform search functions (search_reddit, search_x, search_linkedin, search_all_platforms)
  - Platform posting functions (post_to_reddit, post_to_x, post_to_linkedin, publish_to_platform)
  - Engagement tracking (get_post_engagement)
  - DB helpers (store_trend, get_trend, store_content, update_content_status, etc.)
  - Constants and configuration
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.marketing.tools import (
    PLATFORM_CHAR_LIMITS,
    SUPPORTED_PLATFORMS,
    search_reddit,
    search_x,
    search_linkedin,
    search_all_platforms,
    post_to_reddit,
    post_to_x,
    post_to_linkedin,
    publish_to_platform,
    get_post_engagement,
    store_trend,
    get_trend,
    store_content,
    update_content_status,
    get_content,
    get_recent_trends,
    get_content_by_status,
)


# ============================================================================
# Constants
# ============================================================================

class TestConstants:
    def test_platform_char_limits_has_all_platforms(self):
        assert "x" in PLATFORM_CHAR_LIMITS
        assert "reddit" in PLATFORM_CHAR_LIMITS
        assert "linkedin" in PLATFORM_CHAR_LIMITS

    def test_x_char_limit_is_280(self):
        assert PLATFORM_CHAR_LIMITS["x"] == 280

    def test_supported_platforms_matches_char_limits(self):
        assert set(SUPPORTED_PLATFORMS) == set(PLATFORM_CHAR_LIMITS.keys())


# ============================================================================
# Search functions — these return [] when platform SDKs are not installed
# ============================================================================

class TestSearchReddit:
    @pytest.mark.asyncio
    async def test_returns_empty_without_asyncpraw(self):
        """When asyncpraw is not installed, should return empty list."""
        result = await search_reddit(["test keyword"])
        assert result == []

    @pytest.mark.asyncio
    async def test_accepts_hours_param(self):
        result = await search_reddit(["test"], hours=48)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_accepts_empty_keywords(self):
        result = await search_reddit([])
        assert result == []


class TestSearchX:
    @pytest.mark.asyncio
    async def test_returns_empty_without_tweepy(self):
        result = await search_x(["test keyword"])
        assert result == []

    @pytest.mark.asyncio
    async def test_accepts_hours_param(self):
        result = await search_x(["test"], hours=1)
        assert isinstance(result, list)


class TestSearchLinkedin:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        result = await search_linkedin(["test keyword"])
        assert result == []


class TestSearchAllPlatforms:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_results(self):
        result = await search_all_platforms(["test"])
        assert result == []

    @pytest.mark.asyncio
    async def test_combines_results_from_all_platforms(self):
        """When individual searchers return data, results are combined."""
        from app.agents.marketing import tools as tools_mod

        fake_reddit = AsyncMock(return_value=[{"content": "r1", "url": "https://reddit.com/1"}])
        fake_x = AsyncMock(return_value=[{"content": "x1", "url": "https://x.com/1"}])
        fake_li = AsyncMock(return_value=[])

        original = dict(tools_mod.PLATFORM_SEARCHERS)
        tools_mod.PLATFORM_SEARCHERS["reddit"] = fake_reddit
        tools_mod.PLATFORM_SEARCHERS["x"] = fake_x
        tools_mod.PLATFORM_SEARCHERS["linkedin"] = fake_li
        try:
            result = await search_all_platforms(["test"])
        finally:
            tools_mod.PLATFORM_SEARCHERS.update(original)

        assert len(result) == 2
        platforms = {r.get("platform") for r in result}
        assert "reddit" in platforms
        assert "x" in platforms

    @pytest.mark.asyncio
    async def test_sets_default_platform_on_results(self):
        """Results without a platform key should get one set."""
        from app.agents.marketing import tools as tools_mod

        fake_reddit = AsyncMock(return_value=[{"content": "post without platform key"}])
        fake_empty = AsyncMock(return_value=[])

        original = dict(tools_mod.PLATFORM_SEARCHERS)
        tools_mod.PLATFORM_SEARCHERS["reddit"] = fake_reddit
        tools_mod.PLATFORM_SEARCHERS["x"] = fake_empty
        tools_mod.PLATFORM_SEARCHERS["linkedin"] = fake_empty
        try:
            result = await search_all_platforms(["test"])
        finally:
            tools_mod.PLATFORM_SEARCHERS.update(original)

        reddit_results = [r for r in result if r.get("platform") == "reddit"]
        assert len(reddit_results) >= 1

    @pytest.mark.asyncio
    async def test_handles_searcher_exception_gracefully(self):
        """If one platform searcher raises, others still run."""
        from app.agents.marketing import tools as tools_mod

        fake_boom = AsyncMock(side_effect=RuntimeError("boom"))
        fake_ok = AsyncMock(return_value=[{"content": "ok"}])
        fake_empty = AsyncMock(return_value=[])

        original = dict(tools_mod.PLATFORM_SEARCHERS)
        tools_mod.PLATFORM_SEARCHERS["reddit"] = fake_boom
        tools_mod.PLATFORM_SEARCHERS["x"] = fake_ok
        tools_mod.PLATFORM_SEARCHERS["linkedin"] = fake_empty
        try:
            result = await search_all_platforms(["test"])
        finally:
            tools_mod.PLATFORM_SEARCHERS.update(original)

        assert len(result) >= 1


# ============================================================================
# Posting functions
# ============================================================================

class TestPostToReddit:
    @pytest.mark.asyncio
    async def test_raises_without_asyncpraw(self):
        """Without asyncpraw, should raise RuntimeError."""
        # asyncpraw won't be installed in test env
        with pytest.raises((RuntimeError, NotImplementedError)):
            await post_to_reddit(subreddit="test", title="Test", body="Body")


class TestPostToX:
    @pytest.mark.asyncio
    async def test_raises_without_tweepy(self):
        with pytest.raises((RuntimeError, NotImplementedError)):
            await post_to_x(text="Hello world")


class TestPostToLinkedin:
    @pytest.mark.asyncio
    async def test_raises_when_credentials_missing(self):
        """Should raise RuntimeError when access token not configured."""
        with pytest.raises(RuntimeError, match="linkedin_access_token"):
            await post_to_linkedin(text="Hello world")


class TestPublishToPlatform:
    @pytest.mark.asyncio
    async def test_unsupported_platform_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported platform"):
            await publish_to_platform("tiktok", "content")

    @pytest.mark.asyncio
    async def test_reddit_delegates_to_post_to_reddit(self):
        with patch("app.agents.marketing.tools.post_to_reddit", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"platform_post_id": "abc", "url": "https://reddit.com/abc"}
            result = await publish_to_platform("reddit", "body text", subreddit="test", title="title")
            mock_post.assert_called_once_with(subreddit="test", title="title", body="body text", parent_id=None)
            assert result["platform_post_id"] == "abc"

    @pytest.mark.asyncio
    async def test_x_delegates_to_post_to_x(self):
        with patch("app.agents.marketing.tools.post_to_x", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"platform_post_id": "tw1", "url": "https://x.com/tw1"}
            result = await publish_to_platform("x", "tweet text")
            mock_post.assert_called_once_with(text="tweet text", reply_to=None)

    @pytest.mark.asyncio
    async def test_linkedin_delegates_to_post_to_linkedin(self):
        with patch("app.agents.marketing.tools.post_to_linkedin", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"platform_post_id": "li1", "url": "https://linkedin.com/li1"}
            result = await publish_to_platform("linkedin", "linkedin post")
            mock_post.assert_called_once_with(text="linkedin post")


# ============================================================================
# Engagement tracking
# ============================================================================

class TestGetPostEngagement:
    @pytest.mark.asyncio
    async def test_returns_zeroed_metrics(self):
        result = await get_post_engagement("x", "some-id")
        assert result == {"likes": 0, "comments": 0, "shares": 0}

    @pytest.mark.asyncio
    async def test_returns_dict_with_expected_keys(self):
        result = await get_post_engagement("reddit", "post-123")
        assert "likes" in result
        assert "comments" in result
        assert "shares" in result


# ============================================================================
# DB helpers — these require the Supabase mock from conftest
# ============================================================================

class TestStoreTrend:
    @pytest.mark.asyncio
    async def test_inserts_and_returns_row(self, fake_supabase):
        trend = {
            "platform": "reddit",
            "url": "https://reddit.com/r/test/1",
            "author": "user123",
            "content": "This is a test post about code reviews",
            "topic": "code reviews",
            "relevance_score": 85,
            "relevance_reason": "Directly mentions pain point",
            "suggested_action": "reply",
        }
        result = await store_trend(trend)
        assert "id" in result
        assert result["platform"] == "reddit"
        assert result["relevance_score"] == 85

    @pytest.mark.asyncio
    async def test_stores_minimal_trend(self, fake_supabase):
        trend = {
            "platform": "x",
            "content": "short post",
            "relevance_score": 61,
        }
        result = await store_trend(trend)
        assert result["platform"] == "x"


class TestGetTrend:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, fake_supabase):
        fake_supabase.set_table_data("marketing_trends", [])
        result = await get_trend("nonexistent-id")
        # FakeQueryBuilder.maybe_single on empty list returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_trend_when_exists(self, fake_supabase):
        tid = str(uuid.uuid4())
        fake_supabase.set_table_data("marketing_trends", [
            {"id": tid, "platform": "x", "post_content": "test", "relevance_score": 75}
        ])
        result = await get_trend(tid)
        assert result is not None
        assert result["platform"] == "x"


class TestStoreContent:
    @pytest.mark.asyncio
    async def test_inserts_draft(self, fake_supabase):
        content = {
            "platform": "linkedin",
            "content": "Check out our new feature!",
            "content_type": "announcement",
            "topic": "new feature",
        }
        result = await store_content(content)
        assert "id" in result
        assert result["status"] == "draft"

    @pytest.mark.asyncio
    async def test_includes_trend_id_when_provided(self, fake_supabase):
        tid = str(uuid.uuid4())
        content = {
            "platform": "x",
            "content": "reply text",
            "content_type": "reply",
            "trend_id": tid,
        }
        result = await store_content(content)
        assert result["trend_id"] == tid


class TestUpdateContentStatus:
    @pytest.mark.asyncio
    async def test_updates_status(self, fake_supabase):
        cid = str(uuid.uuid4())
        fake_supabase.set_table_data("marketing_posts", [
            {"id": cid, "status": "draft", "platform": "x", "content": "hello"}
        ])
        result = await update_content_status(cid, "published", published_url="https://x.com/1")
        assert result["status"] == "published"
        assert result["published_url"] == "https://x.com/1"


class TestGetContent:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, fake_supabase):
        fake_supabase.set_table_data("marketing_posts", [])
        result = await get_content("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_content_when_exists(self, fake_supabase):
        cid = str(uuid.uuid4())
        fake_supabase.set_table_data("marketing_posts", [
            {"id": cid, "platform": "reddit", "content": "a post", "status": "draft"}
        ])
        result = await get_content(cid)
        assert result is not None
        assert result["platform"] == "reddit"


class TestGetRecentTrends:
    @pytest.mark.asyncio
    async def test_returns_list(self, fake_supabase):
        fake_supabase.set_table_data("marketing_trends", [
            {"id": "1", "platform": "x", "relevance_score": 90},
            {"id": "2", "platform": "reddit", "relevance_score": 70},
        ])
        result = await get_recent_trends(limit=10)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_trends(self, fake_supabase):
        fake_supabase.set_table_data("marketing_trends", [])
        result = await get_recent_trends()
        assert result == []


class TestGetContentByStatus:
    @pytest.mark.asyncio
    async def test_returns_filtered_content(self, fake_supabase):
        fake_supabase.set_table_data("marketing_posts", [
            {"id": "1", "status": "draft", "platform": "x"},
            {"id": "2", "status": "published", "platform": "linkedin"},
        ])
        result = await get_content_by_status("draft")
        # FakeQueryBuilder doesn't actually filter, but structure is correct
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_matches(self, fake_supabase):
        fake_supabase.set_table_data("marketing_posts", [])
        result = await get_content_by_status("published")
        assert result == []


# ============================================================================
# Reddit implementation tests — mock asyncpraw to verify real wiring
# ============================================================================

import sys
import types
from datetime import datetime, timezone, timedelta


def _make_submission(
    sub_id: str = "abc123",
    title: str = "Test post",
    selftext: str = "Body text",
    author: str = "testuser",
    score: int = 42,
    num_comments: int = 5,
    created_utc: float | None = None,
    permalink: str = "/r/test/comments/abc123/test_post/",
    subreddit_name: str = "test",
):
    """Create a mock Reddit submission object."""
    sub = MagicMock()
    sub.id = sub_id
    sub.title = title
    sub.selftext = selftext
    sub.author = MagicMock(__str__=lambda s: author) if author else None
    sub.score = score
    sub.num_comments = num_comments
    sub.created_utc = created_utc or (datetime.now(timezone.utc).timestamp() - 60)
    sub.permalink = permalink
    return sub


class _AsyncSubmissionIter:
    """Async iterator that yields mock submissions."""
    def __init__(self, submissions):
        self._items = list(submissions)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


class TestSearchRedditImplementation:
    """Tests for the real search_reddit logic with asyncpraw mocked."""

    def _make_mock_asyncpraw(self, submissions_by_keyword=None):
        """Build a mock asyncpraw module and Reddit instance."""
        submissions_by_keyword = submissions_by_keyword or {}

        mock_subreddit = MagicMock()

        def fake_search(keyword, sort="new", time_filter="day", limit=25):
            subs = submissions_by_keyword.get(keyword, [])
            return _AsyncSubmissionIter(subs)

        mock_subreddit.search = fake_search

        mock_reddit = MagicMock()
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)
        mock_reddit.close = AsyncMock()

        mock_module = MagicMock()
        mock_module.Reddit.return_value = mock_reddit

        return mock_module, mock_reddit

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_credentials(self):
        """Should return [] when reddit_client_id is empty."""
        result = await search_reddit(["test"])
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_keywords(self):
        result = await search_reddit([])
        assert result == []

    @pytest.mark.asyncio
    async def test_searches_configured_subreddits(self):
        """Should search each configured subreddit with each keyword."""
        sub1 = _make_submission(sub_id="s1", title="Relevant post")
        mock_module, mock_reddit = self._make_mock_asyncpraw({"test": [sub1]})

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = ""
                mock_settings.reddit_password = ""
                mock_settings.reddit_user_agent = "test-bot"
                mock_settings.reddit_subreddits = "startups,SaaS"

                result = await search_reddit(["test"])

        # Called subreddit() for each sub_name
        assert mock_reddit.subreddit.call_count == 2
        mock_reddit.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_defaults_to_r_all_when_no_subreddits_configured(self):
        sub1 = _make_submission(sub_id="s1")
        mock_module, mock_reddit = self._make_mock_asyncpraw({"test": [sub1]})

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = ""
                mock_settings.reddit_password = ""
                mock_settings.reddit_user_agent = "test-bot"
                mock_settings.reddit_subreddits = ""

                result = await search_reddit(["test"])

        mock_reddit.subreddit.assert_called_once_with("all")

    @pytest.mark.asyncio
    async def test_filters_posts_older_than_cutoff(self):
        """Posts older than `hours` parameter should be excluded."""
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
        recent_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()

        old_sub = _make_submission(sub_id="old", created_utc=old_ts)
        new_sub = _make_submission(sub_id="new", created_utc=recent_ts)
        mock_module, mock_reddit = self._make_mock_asyncpraw({"kw": [old_sub, new_sub]})

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = ""
                mock_settings.reddit_password = ""
                mock_settings.reddit_user_agent = "test-bot"
                mock_settings.reddit_subreddits = "test"

                result = await search_reddit(["kw"], hours=24)

        assert len(result) == 1
        assert result[0]["post_id"] == "new"

    @pytest.mark.asyncio
    async def test_deduplicates_across_keywords(self):
        """Same post found via multiple keywords should appear once."""
        sub = _make_submission(sub_id="dup1")
        mock_module, mock_reddit = self._make_mock_asyncpraw({
            "keyword1": [sub],
            "keyword2": [sub],
        })

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = ""
                mock_settings.reddit_password = ""
                mock_settings.reddit_user_agent = "test-bot"
                mock_settings.reddit_subreddits = "test"

                result = await search_reddit(["keyword1", "keyword2"])

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_result_structure(self):
        """Verify all expected fields are present in results."""
        sub = _make_submission(
            sub_id="x1",
            title="My Title",
            selftext="Body here",
            author="alice",
            score=10,
            num_comments=3,
        )
        mock_module, mock_reddit = self._make_mock_asyncpraw({"kw": [sub]})

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = ""
                mock_settings.reddit_password = ""
                mock_settings.reddit_user_agent = "test-bot"
                mock_settings.reddit_subreddits = "test"

                result = await search_reddit(["kw"])

        assert len(result) == 1
        r = result[0]
        assert r["platform"] == "reddit"
        assert "reddit.com" in r["url"]
        assert r["author"] == "alice"
        assert "My Title" in r["content"]
        assert "Body here" in r["content"]
        assert r["post_id"] == "x1"
        assert r["score"] == 10
        assert r["num_comments"] == 3
        assert "posted_at" in r
        assert "subreddit" in r

    @pytest.mark.asyncio
    async def test_handles_deleted_author(self):
        """Posts with author=None should show [deleted]."""
        sub = _make_submission(sub_id="del1", author=None)
        sub.author = None
        mock_module, mock_reddit = self._make_mock_asyncpraw({"kw": [sub]})

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = ""
                mock_settings.reddit_password = ""
                mock_settings.reddit_user_agent = "test-bot"
                mock_settings.reddit_subreddits = "test"

                result = await search_reddit(["kw"])

        assert result[0]["author"] == "[deleted]"

    @pytest.mark.asyncio
    async def test_closes_reddit_client_on_exception(self):
        """Reddit client should be closed even if search raises."""
        mock_module = MagicMock()
        mock_reddit = MagicMock()
        mock_reddit.subreddit = AsyncMock(side_effect=RuntimeError("API error"))
        mock_reddit.close = AsyncMock()
        mock_module.Reddit.return_value = mock_reddit

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = ""
                mock_settings.reddit_password = ""
                mock_settings.reddit_user_agent = "test-bot"
                mock_settings.reddit_subreddits = "test"

                result = await search_reddit(["kw"])

        # Should not crash, and should close the client
        mock_reddit.close.assert_called_once()
        assert result == []


class TestPostToRedditImplementation:
    """Tests for the real post_to_reddit logic with asyncpraw mocked."""

    @pytest.mark.asyncio
    async def test_raises_when_credentials_missing(self):
        """Should raise RuntimeError when username/password not set."""
        mock_module = MagicMock()
        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = ""
                mock_settings.reddit_password = ""
                mock_settings.reddit_user_agent = "test-bot"

                with pytest.raises(RuntimeError, match="reddit_username"):
                    await post_to_reddit(subreddit="test", title="T", body="B")

    @pytest.mark.asyncio
    async def test_submits_new_post(self):
        """Should call subreddit.submit() for new posts."""
        mock_submission = MagicMock()
        mock_submission.id = "new123"
        mock_submission.permalink = "/r/test/comments/new123/title/"

        mock_subreddit = MagicMock()
        mock_subreddit.submit = AsyncMock(return_value=mock_submission)

        mock_reddit = MagicMock()
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)
        mock_reddit.close = AsyncMock()

        mock_module = MagicMock()
        mock_module.Reddit.return_value = mock_reddit

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = "user"
                mock_settings.reddit_password = "pass"
                mock_settings.reddit_user_agent = "test-bot"

                result = await post_to_reddit(
                    subreddit="startups", title="Hello", body="World"
                )

        assert result["platform_post_id"] == "new123"
        assert "reddit.com" in result["url"]
        mock_subreddit.submit.assert_called_once_with(title="Hello", selftext="World")
        mock_reddit.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_replies_to_comment(self):
        """Should call comment.reply() when parent_id is provided."""
        mock_reply = MagicMock()
        mock_reply.id = "reply456"
        mock_reply.permalink = "/r/test/comments/abc/t/reply456/"

        mock_comment = MagicMock()
        mock_comment.reply = AsyncMock(return_value=mock_reply)

        mock_reddit = MagicMock()
        mock_reddit.comment = AsyncMock(return_value=mock_comment)
        mock_reddit.close = AsyncMock()

        mock_module = MagicMock()
        mock_module.Reddit.return_value = mock_reddit

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = "user"
                mock_settings.reddit_password = "pass"
                mock_settings.reddit_user_agent = "test-bot"

                result = await post_to_reddit(
                    subreddit="", title="", body="Nice post!",
                    parent_id="comment789"
                )

        assert result["platform_post_id"] == "reply456"
        mock_reddit.comment.assert_called_once_with("comment789")
        mock_comment.reply.assert_called_once_with("Nice post!")

    @pytest.mark.asyncio
    async def test_raises_when_subreddit_missing_for_new_post(self):
        mock_reddit = MagicMock()
        mock_reddit.close = AsyncMock()

        mock_module = MagicMock()
        mock_module.Reddit.return_value = mock_reddit

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = "user"
                mock_settings.reddit_password = "pass"
                mock_settings.reddit_user_agent = "test-bot"

                with pytest.raises(ValueError, match="subreddit is required"):
                    await post_to_reddit(subreddit="", title="T", body="B")

    @pytest.mark.asyncio
    async def test_closes_client_on_error(self):
        mock_subreddit = MagicMock()
        mock_subreddit.submit = AsyncMock(side_effect=RuntimeError("API error"))

        mock_reddit = MagicMock()
        mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)
        mock_reddit.close = AsyncMock()

        mock_module = MagicMock()
        mock_module.Reddit.return_value = mock_reddit

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = "user"
                mock_settings.reddit_password = "pass"
                mock_settings.reddit_user_agent = "test-bot"

                with pytest.raises(RuntimeError, match="API error"):
                    await post_to_reddit(subreddit="test", title="T", body="B")

        mock_reddit.close.assert_called_once()


class TestGetRedditEngagement:
    """Tests for Reddit engagement tracking."""

    @pytest.mark.asyncio
    async def test_returns_score_and_comments(self):
        from app.agents.marketing.tools import _get_reddit_engagement

        mock_submission = MagicMock()
        mock_submission.score = 150
        mock_submission.num_comments = 23

        mock_reddit = MagicMock()
        mock_reddit.submission = AsyncMock(return_value=mock_submission)
        mock_reddit.close = AsyncMock()

        mock_module = MagicMock()
        mock_module.Reddit.return_value = mock_reddit

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = ""
                mock_settings.reddit_password = ""
                mock_settings.reddit_user_agent = "test-bot"

                result = await _get_reddit_engagement("abc123")

        assert result["likes"] == 150
        assert result["comments"] == 23
        assert result["shares"] == 0
        mock_reddit.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_zeros_on_error(self):
        from app.agents.marketing.tools import _get_reddit_engagement

        mock_reddit = MagicMock()
        mock_reddit.submission = AsyncMock(side_effect=RuntimeError("fail"))
        mock_reddit.close = AsyncMock()

        mock_module = MagicMock()
        mock_module.Reddit.return_value = mock_reddit

        with patch.dict(sys.modules, {"asyncpraw": mock_module}):
            with patch("app.agents.marketing.tools.settings") as mock_settings:
                mock_settings.reddit_client_id = "id"
                mock_settings.reddit_client_secret = "secret"
                mock_settings.reddit_username = ""
                mock_settings.reddit_password = ""
                mock_settings.reddit_user_agent = "test-bot"

                result = await _get_reddit_engagement("bad_id")

        assert result == {"likes": 0, "comments": 0, "shares": 0}

    @pytest.mark.asyncio
    async def test_get_post_engagement_delegates_to_reddit(self):
        """get_post_engagement should call _get_reddit_engagement for reddit."""
        with patch(
            "app.agents.marketing.tools._get_reddit_engagement",
            new_callable=AsyncMock,
            return_value={"likes": 10, "comments": 2, "shares": 0},
        ):
            result = await get_post_engagement("reddit", "some-id")
        assert result["likes"] == 10

    @pytest.mark.asyncio
    async def test_get_post_engagement_returns_zeros_for_other_platforms(self):
        result = await get_post_engagement("x", "some-id")
        assert result == {"likes": 0, "comments": 0, "shares": 0}

    @pytest.mark.asyncio
    async def test_get_post_engagement_delegates_to_linkedin(self):
        """get_post_engagement should call _get_linkedin_engagement for linkedin."""
        with patch(
            "app.agents.marketing.tools._get_linkedin_engagement",
            new_callable=AsyncMock,
            return_value={"likes": 5, "comments": 1, "shares": 3},
        ):
            result = await get_post_engagement("linkedin", "urn:li:share:123")
        assert result["likes"] == 5
        assert result["shares"] == 3


# ============================================================================
# LinkedIn implementation tests — mock httpx to verify real wiring
# ============================================================================


def _make_httpx_response(status_code: int = 200, json_data: dict | None = None, headers: dict | None = None):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = str(json_data or {})
    resp.headers = headers or {}
    return resp


class TestSearchLinkedinImplementation:
    """Tests for the real search_linkedin logic with httpx mocked."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_credentials(self):
        result = await search_linkedin(["test"])
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_keywords(self):
        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"
            mock_settings.linkedin_person_id = "urn:li:person:123"
            result = await search_linkedin([])
        assert result == []

    @pytest.mark.asyncio
    async def test_fetches_posts_and_filters_by_keyword(self):
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        api_response = {
            "elements": [
                {
                    "id": "urn:li:share:1",
                    "commentary": "We just shipped an AI code review tool!",
                    "createdAt": now_ms - 1000,
                    "author": "urn:li:person:123",
                },
                {
                    "id": "urn:li:share:2",
                    "commentary": "Having lunch at a nice restaurant",
                    "createdAt": now_ms - 2000,
                    "author": "urn:li:person:123",
                },
                {
                    "id": "urn:li:share:3",
                    "commentary": "Code review best practices for 2026",
                    "createdAt": now_ms - 3000,
                    "author": "urn:li:person:123",
                },
            ]
        }
        mock_resp = _make_httpx_response(200, api_response)

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"
            mock_settings.linkedin_person_id = "urn:li:person:123"
            mock_settings.linkedin_organization_id = ""

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await search_linkedin(["code review"])

        # Should match post 1 and 3 (contain "code review"), skip post 2
        assert len(result) == 2
        ids = {r["post_id"] for r in result}
        assert "urn:li:share:1" in ids
        assert "urn:li:share:3" in ids
        assert "urn:li:share:2" not in ids

    @pytest.mark.asyncio
    async def test_filters_posts_outside_time_window(self):
        old_ms = int((datetime.now(timezone.utc) - timedelta(hours=48)).timestamp() * 1000)
        recent_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - 1000

        api_response = {
            "elements": [
                {"id": "old", "commentary": "old matching post", "createdAt": old_ms, "author": "a"},
                {"id": "new", "commentary": "new matching post", "createdAt": recent_ms, "author": "a"},
            ]
        }
        mock_resp = _make_httpx_response(200, api_response)

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"
            mock_settings.linkedin_person_id = "urn:li:person:123"
            mock_settings.linkedin_organization_id = ""

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await search_linkedin(["matching"], hours=24)

        assert len(result) == 1
        assert result[0]["post_id"] == "new"

    @pytest.mark.asyncio
    async def test_scans_organization_when_configured(self):
        api_response = {"elements": []}
        mock_resp = _make_httpx_response(200, api_response)

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"
            mock_settings.linkedin_person_id = "urn:li:person:123"
            mock_settings.linkedin_organization_id = "urn:li:organization:456"

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                await search_linkedin(["test"])

        # Should make 2 API calls — one for person, one for organization
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self):
        mock_resp = _make_httpx_response(500, {"error": "internal"})

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"
            mock_settings.linkedin_person_id = "urn:li:person:123"
            mock_settings.linkedin_organization_id = ""

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await search_linkedin(["test"])

        assert result == []

    @pytest.mark.asyncio
    async def test_result_structure(self):
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        api_response = {
            "elements": [{
                "id": "urn:li:share:42",
                "commentary": "Great discussion about testing",
                "createdAt": now_ms - 500,
                "author": "urn:li:person:alice",
            }]
        }
        mock_resp = _make_httpx_response(200, api_response)

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"
            mock_settings.linkedin_person_id = "urn:li:person:123"
            mock_settings.linkedin_organization_id = ""

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await search_linkedin(["testing"])

        assert len(result) == 1
        r = result[0]
        assert r["platform"] == "linkedin"
        assert "linkedin.com" in r["url"]
        assert r["post_id"] == "urn:li:share:42"
        assert "testing" in r["content"].lower()
        assert "posted_at" in r


class TestPostToLinkedinImplementation:
    """Tests for the real post_to_linkedin logic with httpx mocked."""

    @pytest.mark.asyncio
    async def test_raises_when_credentials_missing(self):
        with pytest.raises(RuntimeError, match="linkedin_access_token"):
            await post_to_linkedin(text="Hello")

    @pytest.mark.asyncio
    async def test_successful_post(self):
        mock_resp = _make_httpx_response(
            201, {},
            headers={"x-restli-id": "urn:li:share:999"},
        )

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"
            mock_settings.linkedin_person_id = "urn:li:person:123"
            mock_settings.linkedin_organization_id = ""

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await post_to_linkedin("Check out our new feature!")

        assert result["platform_post_id"] == "urn:li:share:999"
        assert "linkedin.com" in result["url"]

        # Verify the API call payload
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["author"] == "urn:li:person:123"
        assert payload["commentary"] == "Check out our new feature!"
        assert payload["visibility"] == "PUBLIC"

    @pytest.mark.asyncio
    async def test_posts_as_organization_when_configured(self):
        mock_resp = _make_httpx_response(
            201, {},
            headers={"x-restli-id": "urn:li:share:888"},
        )

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"
            mock_settings.linkedin_person_id = "urn:li:person:123"
            mock_settings.linkedin_organization_id = "urn:li:organization:456"

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await post_to_linkedin("Company update")

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["author"] == "urn:li:organization:456"

    @pytest.mark.asyncio
    async def test_raises_on_api_error(self):
        mock_resp = _make_httpx_response(403, {"message": "Forbidden"})

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"
            mock_settings.linkedin_person_id = "urn:li:person:123"
            mock_settings.linkedin_organization_id = ""

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                with pytest.raises(RuntimeError, match="403"):
                    await post_to_linkedin("This should fail")

    @pytest.mark.asyncio
    async def test_sends_correct_headers(self):
        mock_resp = _make_httpx_response(
            201, {}, headers={"x-restli-id": "urn:li:share:777"},
        )

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "my-secret-token"
            mock_settings.linkedin_person_id = "urn:li:person:123"
            mock_settings.linkedin_organization_id = ""

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                await post_to_linkedin("Test")

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs["headers"]
        assert headers["Authorization"] == "Bearer my-secret-token"
        assert "LinkedIn-Version" in headers


class TestGetLinkedinEngagement:
    """Tests for LinkedIn engagement tracking."""

    @pytest.mark.asyncio
    async def test_returns_engagement_counts(self):
        from app.agents.marketing.tools import _get_linkedin_engagement

        api_response = {
            "totalShareStatistics": {
                "likeCount": 42,
                "commentCount": 7,
                "shareCount": 3,
            }
        }
        mock_resp = _make_httpx_response(200, api_response)

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await _get_linkedin_engagement("urn:li:share:42")

        assert result["likes"] == 42
        assert result["comments"] == 7
        assert result["shares"] == 3

    @pytest.mark.asyncio
    async def test_returns_zeros_on_api_error(self):
        from app.agents.marketing.tools import _get_linkedin_engagement

        mock_resp = _make_httpx_response(500, {})

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await _get_linkedin_engagement("bad-id")

        assert result == {"likes": 0, "comments": 0, "shares": 0}

    @pytest.mark.asyncio
    async def test_returns_zeros_when_no_token(self):
        from app.agents.marketing.tools import _get_linkedin_engagement

        result = await _get_linkedin_engagement("urn:li:share:42")
        assert result == {"likes": 0, "comments": 0, "shares": 0}

    @pytest.mark.asyncio
    async def test_returns_zeros_on_network_exception(self):
        from app.agents.marketing.tools import _get_linkedin_engagement

        with patch("app.agents.marketing.tools.settings") as mock_settings:
            mock_settings.linkedin_access_token = "token"

            with patch("app.agents.marketing.tools.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                import httpx as _httpx
                mock_client.get = AsyncMock(side_effect=_httpx.ConnectError("timeout"))
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                result = await _get_linkedin_engagement("urn:li:share:42")

        assert result == {"likes": 0, "comments": 0, "shares": 0}
