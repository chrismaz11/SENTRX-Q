"""Tests for bot.reddit_client (PRAW mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bot.reddit_client import ModQueueItem, RedditClient

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

CFG = {
    "reddit": {
        "client_id": "fake_id",
        "client_secret": "fake_secret",
        "username": "fake_user",
        "password": "fake_pass",
        "user_agent": "SENTRX-Q/test",
        "subreddits": ["sentrx_q_dev"],
        "fetch_limit": 10,
    }
}


def _make_submission(**kwargs) -> MagicMock:
    sub = MagicMock()
    sub.id = kwargs.get("id", "abc123")
    sub.author = MagicMock()
    sub.author.__str__ = lambda self: kwargs.get("author", "testuser")
    sub.title = kwargs.get("title", "Test post")
    sub.selftext = kwargs.get("body", "Some body text")
    sub.permalink = "/r/sentrx_q_dev/comments/abc123/test_post/"
    sub.score = kwargs.get("score", 5)
    sub.user_reports = kwargs.get("user_reports", [])
    sub.mod_reports = kwargs.get("mod_reports", [])
    # Make isinstance(sub, praw.models.Submission) work
    import praw.models
    sub.__class__ = praw.models.Submission
    return sub


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


@patch("bot.reddit_client.praw.Reddit")
def test_reddit_client_init(mock_praw):
    """RedditClient should authenticate with the provided credentials."""
    client = RedditClient(CFG)
    mock_praw.assert_called_once_with(
        client_id="fake_id",
        client_secret="fake_secret",
        username="fake_user",
        password="fake_pass",
        user_agent="SENTRX-Q/test",
    )
    assert client is not None


@patch("bot.reddit_client.praw.Reddit")
def test_fetch_mod_queue_returns_items(mock_praw):
    """fetch_mod_queue should yield normalised ModQueueItem objects."""
    submission = _make_submission(
        id="xyz999",
        title="Spam post",
        user_reports=[("This is spam", 3)],
    )

    mock_reddit_instance = mock_praw.return_value
    mock_subreddit = MagicMock()
    mock_subreddit.mod.queue.return_value = [submission]
    mock_reddit_instance.subreddit.return_value = mock_subreddit

    client = RedditClient(CFG)
    items = client.fetch_mod_queue()

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, ModQueueItem)
    assert item.item_id == "xyz999"
    assert item.item_type == "submission"
    assert item.subreddit == "sentrx_q_dev"
    assert "This is spam" in item.report_reasons


@patch("bot.reddit_client.praw.Reddit")
def test_fetch_mod_queue_empty(mock_praw):
    """Empty mod queue should return an empty list."""
    mock_reddit_instance = mock_praw.return_value
    mock_subreddit = MagicMock()
    mock_subreddit.mod.queue.return_value = []
    mock_reddit_instance.subreddit.return_value = mock_subreddit

    client = RedditClient(CFG)
    items = client.fetch_mod_queue()
    assert items == []


@patch("bot.reddit_client.praw.Reddit")
def test_fetch_mod_queue_error_is_logged(mock_praw, caplog):
    """Errors from PRAW should be caught and logged, not raised."""
    mock_reddit_instance = mock_praw.return_value
    mock_subreddit = MagicMock()
    mock_subreddit.mod.queue.side_effect = Exception("network error")
    mock_reddit_instance.subreddit.return_value = mock_subreddit

    client = RedditClient(CFG)
    import logging
    with caplog.at_level(logging.ERROR, logger="bot.reddit_client"):
        items = client.fetch_mod_queue()

    assert items == []
    assert "network error" in caplog.text


@patch("bot.reddit_client.praw.Reddit")
def test_remove_calls_praw(mock_praw):
    """remove() should call raw.mod.remove() on the item."""
    mock_raw = MagicMock()
    item = ModQueueItem(
        item_id="t1", item_type="submission", subreddit="sentrx_q_dev",
        author="u1", title="T", body="B", permalink="http://x", raw=mock_raw,
    )
    client = RedditClient(CFG)
    client.remove(item, mod_note="spam")
    mock_raw.mod.remove.assert_called_once_with(mod_note="spam")


@patch("bot.reddit_client.praw.Reddit")
def test_approve_calls_praw(mock_praw):
    """approve() should call raw.mod.approve() on the item."""
    mock_raw = MagicMock()
    item = ModQueueItem(
        item_id="t2", item_type="submission", subreddit="sentrx_q_dev",
        author="u2", title="T", body="B", permalink="http://x", raw=mock_raw,
    )
    client = RedditClient(CFG)
    client.approve(item)
    mock_raw.mod.approve.assert_called_once()


@patch("bot.reddit_client.praw.Reddit")
def test_as_dict(mock_praw):
    """as_dict() should return a plain dict with the expected keys."""
    item = ModQueueItem(
        item_id="t3", item_type="comment", subreddit="sentrx_q_dev",
        author="u3", title="", body="Hello", permalink="http://y",
        report_reasons=["rule violation"], score=1, num_reports=1,
    )
    d = item.as_dict()
    assert d["item_id"] == "t3"
    assert d["item_type"] == "comment"
    assert d["report_reasons"] == ["rule violation"]


@patch("bot.reddit_client.praw.Reddit")
def test_deleted_author(mock_praw):
    """Items from deleted accounts should have author '[deleted]'."""
    submission = _make_submission(author="", id="del1")
    submission.author = None  # PRAW sets author to None for deleted accounts

    mock_reddit_instance = mock_praw.return_value
    mock_subreddit = MagicMock()
    mock_subreddit.mod.queue.return_value = [submission]
    mock_reddit_instance.subreddit.return_value = mock_subreddit

    client = RedditClient(CFG)
    items = client.fetch_mod_queue()
    assert items[0].author == "[deleted]"
