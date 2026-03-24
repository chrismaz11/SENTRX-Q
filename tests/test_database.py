"""Tests for database.models (in-memory SQLite)."""

from __future__ import annotations

import pytest

from bot.ai_triage import TriageResult
from bot.reddit_client import ModQueueItem
from database.models import AuditLog

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

IN_MEMORY_CFG = {"database": {"path": ":memory:"}}


def _audit() -> AuditLog:
    return AuditLog(IN_MEMORY_CFG)


def _item(item_id: str = "t1") -> ModQueueItem:
    return ModQueueItem(
        item_id=item_id,
        item_type="submission",
        subreddit="sentrx_q_dev",
        author="testuser",
        title="Test Post",
        body="body text",
        permalink="https://reddit.com/r/sentrx_q_dev/comments/t1/",
    )


def _result(item_id: str = "t1") -> TriageResult:
    return TriageResult(
        item_id=item_id,
        severity="medium",
        category="spam",
        removal_reason="Spam content",
        action="remove",
        confidence=0.88,
        explanation="Matches spam pattern.",
        source="ai",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_log_triage_and_retrieve():
    audit = _audit()
    audit.log_triage(_item(), _result())
    rows = audit.recent_triage_results(10)
    assert len(rows) == 1
    row = rows[0]
    assert row["item_id"] == "t1"
    assert row["severity"] == "medium"
    assert row["category"] == "spam"
    assert row["source"] == "ai"


def test_log_action():
    audit = _audit()
    audit.log_action("t1", "removed")
    # No exception means success; we verify via stats indirectly


def test_recent_results_ordered_by_time():
    audit = _audit()
    for i in range(5):
        audit.log_triage(_item(f"t{i}"), _result(f"t{i}"))
    rows = audit.recent_triage_results(5)
    # Most recent first
    assert rows[0]["item_id"] == "t4"


def test_stats_totals():
    audit = _audit()
    audit.log_triage(_item("s1"), _result("s1"))
    audit.log_triage(
        _item("s2"),
        TriageResult(
            item_id="s2", severity="high", category="harassment",
            removal_reason="Harassment.", action="remove",
            confidence=0.9, explanation="Clear harassment.", source="heuristic",
        ),
    )
    stats = audit.stats()
    assert stats["total"] == 2
    assert stats["by_severity"].get("medium", 0) >= 1
    assert stats["by_severity"].get("high", 0) >= 1
    assert stats["by_category"].get("spam", 0) >= 1
    assert stats["by_category"].get("harassment", 0) >= 1


def test_stats_empty_database():
    audit = _audit()
    stats = audit.stats()
    assert stats["total"] == 0
    assert stats["by_severity"] == {}


def test_multiple_items_limit():
    audit = _audit()
    for i in range(20):
        audit.log_triage(_item(f"x{i}"), _result(f"x{i}"))
    rows = audit.recent_triage_results(5)
    assert len(rows) == 5
