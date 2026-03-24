"""Tests for bot.actions (ActionRunner)."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from bot.actions import ActionRunner
from bot.ai_triage import TriageResult
from bot.reddit_client import ModQueueItem

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

CFG_AUTO_OFF = {
    "triage": {
        "auto_actions": False,
        "confidence_threshold": 0.85,
    }
}

CFG_AUTO_ON = {
    "triage": {
        "auto_actions": True,
        "confidence_threshold": 0.85,
    }
}


def _item() -> ModQueueItem:
    return ModQueueItem(
        item_id="act1",
        item_type="submission",
        subreddit="sentrx_q_dev",
        author="baduser",
        title="Test",
        body="body",
        permalink="https://reddit.com/r/sentrx_q_dev/comments/act1/",
    )


def _result(action="remove", confidence=0.9, severity="medium", category="spam") -> TriageResult:
    return TriageResult(
        item_id="act1",
        severity=severity,
        category=category,
        removal_reason="Spam.",
        action=action,
        confidence=confidence,
        explanation="Test.",
        source="ai",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_auto_actions_disabled_returns_queued():
    reddit = MagicMock()
    audit = MagicMock()
    runner = ActionRunner(reddit, audit, CFG_AUTO_OFF)
    outcome = runner.process(_item(), _result())
    assert outcome == "queued"
    reddit.remove.assert_not_called()
    audit.log_triage.assert_called_once()


def test_remove_action_executed():
    reddit = MagicMock()
    audit = MagicMock()
    runner = ActionRunner(reddit, audit, CFG_AUTO_ON)
    outcome = runner.process(_item(), _result(action="remove", confidence=0.92))
    assert outcome == "removed"
    reddit.remove.assert_called_once()
    audit.log_action.assert_called_with("act1", "removed")


def test_approve_action_executed():
    reddit = MagicMock()
    audit = MagicMock()
    runner = ActionRunner(reddit, audit, CFG_AUTO_ON)
    outcome = runner.process(_item(), _result(action="approve", confidence=0.90))
    assert outcome == "approved"
    reddit.approve.assert_called_once()


def test_escalate_action_executed():
    reddit = MagicMock()
    audit = MagicMock()
    runner = ActionRunner(reddit, audit, CFG_AUTO_ON)
    outcome = runner.process(_item(), _result(action="escalate", confidence=0.95, severity="critical"))
    assert outcome == "escalated"
    reddit.lock.assert_called_once()
    audit.log_action.assert_called_with("act1", "escalated")


def test_low_confidence_skipped():
    reddit = MagicMock()
    audit = MagicMock()
    runner = ActionRunner(reddit, audit, CFG_AUTO_ON)
    outcome = runner.process(_item(), _result(action="remove", confidence=0.50))
    assert outcome == "skipped_low_confidence"
    reddit.remove.assert_not_called()
    audit.log_action.assert_called_with("act1", "skipped_low_confidence")


def test_unknown_action_returns_no_action():
    reddit = MagicMock()
    audit = MagicMock()
    runner = ActionRunner(reddit, audit, CFG_AUTO_ON)
    outcome = runner.process(_item(), _result(action="none", confidence=0.90))
    assert outcome == "no_action"


def test_reddit_error_is_caught():
    reddit = MagicMock()
    reddit.remove.side_effect = Exception("PRAW error")
    audit = MagicMock()
    runner = ActionRunner(reddit, audit, CFG_AUTO_ON)
    outcome = runner.process(_item(), _result(action="remove", confidence=0.92))
    assert "error" in outcome
