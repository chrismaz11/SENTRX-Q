"""Tests for bot.heuristics (no external dependencies)."""

from __future__ import annotations

import pytest

from bot.heuristics import triage_heuristic
from bot.reddit_client import ModQueueItem


def _item(title: str = "", body: str = "", reports: list[str] | None = None) -> ModQueueItem:
    return ModQueueItem(
        item_id="h_test",
        item_type="submission",
        subreddit="sentrx_q_dev",
        author="testuser",
        title=title,
        body=body,
        permalink="https://reddit.com/r/sentrx_q_dev/comments/h_test/",
        report_reasons=reports or [],
    )


def test_spam_detected():
    item = _item(title="Buy now — cheap discount promo code inside!")
    result = triage_heuristic(item)
    assert result.category == "spam"
    assert result.action == "remove"
    assert result.source == "heuristic"


def test_threat_kys():
    item = _item(body="You should kys loser")
    result = triage_heuristic(item)
    assert result.category == "threat"
    assert result.severity == "critical"
    assert result.action == "escalate"


def test_self_harm_detected():
    item = _item(body="I want to die and end it all tonight")
    result = triage_heuristic(item)
    assert result.category == "self_harm"
    assert result.severity == "critical"


def test_hate_speech_slur():
    item = _item(body="you are a faggot")
    result = triage_heuristic(item)
    assert result.category == "hate_speech"
    assert result.severity == "high"


def test_doxxing_detected():
    item = _item(body="Here is their real address and personal info")
    result = triage_heuristic(item)
    assert result.category == "doxxing"
    assert result.action == "remove"


def test_ban_evasion():
    item = _item(body="This is clearly ban evasion with an alt account")
    result = triage_heuristic(item)
    assert result.category == "ban_evasion"


def test_no_match_returns_none_category():
    item = _item(title="Cute puppies!", body="Here are some adorable dogs.")
    result = triage_heuristic(item)
    assert result.category == "none"
    assert result.action == "none"
    assert result.severity == "low"


def test_multiple_rules_increase_confidence():
    """When several rules fire the confidence should be higher."""
    item = _item(
        title="Buy now cheap discount",
        body="kys loser — free bitcoin promo code",
    )
    single_result = triage_heuristic(_item(title="Buy now cheap discount"))
    multi_result = triage_heuristic(item)
    assert multi_result.confidence >= single_result.confidence


def test_result_as_dict():
    item = _item(body="click here free bitcoin")
    result = triage_heuristic(item)
    d = result.as_dict()
    assert d["source"] == "heuristic"
    assert "category" in d
    assert "confidence" in d


def test_report_reasons_analysed():
    """Report reasons should also be scanned for keywords."""
    item = _item(reports=["User posted personal info / doxxing"])
    result = triage_heuristic(item)
    assert result.category == "doxxing"


def test_confidence_within_bounds():
    """Confidence should always be in (0, 1)."""
    for body in ["kys", "buy now", "I want to die", "fake news", "free bitcoin promo code"]:
        result = triage_heuristic(_item(body=body))
        assert 0.0 <= result.confidence <= 1.0
