"""Tests for bot.ai_triage (OpenAI mocked)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from bot.ai_triage import AITriageEngine, TriageResult
from bot.reddit_client import ModQueueItem

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

CFG = {
    "openai": {
        "api_key": "sk-test",
        "model": "gpt-4",
        "max_tokens": 256,
        "temperature": 0.2,
    },
    "triage": {
        "escalation_categories": ["threat", "self_harm", "csam"],
    },
}

ITEM = ModQueueItem(
    item_id="abc1",
    item_type="submission",
    subreddit="sentrx_q_dev",
    author="bad_actor",
    title="Free Bitcoin click here",
    body="Visit spamsite.example.com for free coins",
    permalink="https://reddit.com/r/sentrx_q_dev/comments/abc1/",
    report_reasons=["spam"],
)


def _mock_openai_response(payload: dict) -> MagicMock:
    """Return a mock that looks like an openai.ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = json.dumps(payload)
    response = MagicMock()
    response.choices = [choice]
    return response


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


@patch("bot.ai_triage.openai.OpenAI")
def test_triage_spam_item(mock_openai_cls):
    """Engine should correctly parse a spam response from GPT-4."""
    ai_response = {
        "severity": "low",
        "category": "spam",
        "removal_reason": "Unsolicited advertising.",
        "action": "remove",
        "confidence": 0.92,
        "explanation": "Title and body match spam patterns.",
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(ai_response)
    mock_openai_cls.return_value = mock_client

    engine = AITriageEngine(CFG)
    result = engine.triage(ITEM)

    assert isinstance(result, TriageResult)
    assert result.severity == "low"
    assert result.category == "spam"
    assert result.action == "remove"
    assert 0 < result.confidence < 1.0
    assert result.source == "ai"


@patch("bot.ai_triage.openai.OpenAI")
def test_triage_critical_escalation(mock_openai_cls):
    """Engine should produce action='escalate' for critical items."""
    critical_item = ModQueueItem(
        item_id="crit1",
        item_type="comment",
        subreddit="sentrx_q_dev",
        author="threatener",
        title="",
        body="I will kill you",
        permalink="https://reddit.com/r/sentrx_q_dev/comments/crit1/",
        report_reasons=["threat"],
    )
    ai_response = {
        "severity": "critical",
        "category": "threat",
        "removal_reason": "Explicit threat of violence.",
        "action": "escalate",
        "confidence": 0.97,
        "explanation": "Clear violent threat.",
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(ai_response)
    mock_openai_cls.return_value = mock_client

    engine = AITriageEngine(CFG)
    result = engine.triage(critical_item)

    assert result.severity == "critical"
    assert result.action == "escalate"
    assert result.confidence <= 0.99


@patch("bot.ai_triage.openai.OpenAI")
def test_triage_malformed_json_returns_error_result(mock_openai_cls):
    """Engine should return an error TriageResult when GPT returns garbled JSON."""
    choice = MagicMock()
    choice.message.content = "Sorry, I cannot help with that."
    response = MagicMock()
    response.choices = [choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = response
    mock_openai_cls.return_value = mock_client

    engine = AITriageEngine(CFG)
    result = engine.triage(ITEM)

    assert result.source == "error"
    assert result.confidence == 0.0


@patch("bot.ai_triage.openai.OpenAI")
def test_triage_confidence_clamped(mock_openai_cls):
    """Confidence values outside [0, 0.99] should be clamped."""
    ai_response = {
        "severity": "high",
        "category": "harassment",
        "removal_reason": "Harassment.",
        "action": "remove",
        "confidence": 1.5,  # above max
        "explanation": "Very obvious.",
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(ai_response)
    mock_openai_cls.return_value = mock_client

    engine = AITriageEngine(CFG)
    result = engine.triage(ITEM)

    assert result.confidence <= 0.99


@patch("bot.ai_triage.openai.OpenAI")
def test_triage_unknown_severity_defaults_to_medium(mock_openai_cls):
    """Unknown severity values should fall back to 'medium'."""
    ai_response = {
        "severity": "ultra_critical",  # unknown
        "category": "other",
        "removal_reason": "",
        "action": "none",
        "confidence": 0.5,
        "explanation": "Unclear.",
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(ai_response)
    mock_openai_cls.return_value = mock_client

    engine = AITriageEngine(CFG)
    result = engine.triage(ITEM)

    assert result.severity == "medium"


@patch("bot.ai_triage.openai.OpenAI")
def test_triage_strips_markdown_fence(mock_openai_cls):
    """Engine should handle responses wrapped in markdown code fences."""
    payload = {
        "severity": "low",
        "category": "spam",
        "removal_reason": "Spam.",
        "action": "remove",
        "confidence": 0.8,
        "explanation": "Spam keywords.",
    }
    choice = MagicMock()
    choice.message.content = "```json\n" + json.dumps(payload) + "\n```"
    response = MagicMock()
    response.choices = [choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = response
    mock_openai_cls.return_value = mock_client

    engine = AITriageEngine(CFG)
    result = engine.triage(ITEM)
    assert result.category == "spam"
