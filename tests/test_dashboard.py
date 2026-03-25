"""Tests for dashboard.app (Flask test client)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dashboard.app import create_app

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

CFG = {
    "dashboard": {
        "secret_key": "test-secret",
        "page_size": 10,
    },
    "triage": {"auto_actions": False},
    "tier": {
        "features": {
            "api_access": True,
        }
    },
}


def _mock_audit(items=None, stats=None):
    audit = MagicMock()
    audit.recent_triage_results.return_value = items or []
    audit.stats.return_value = stats or {"total": 0, "by_severity": {}, "by_category": {}, "by_action": {}}
    return audit


@pytest.fixture()
def client():
    audit = _mock_audit(
        items=[
            {
                "item_id": "abc1",
                "item_type": "submission",
                "subreddit": "sentrx_q_dev",
                "author": "spammer",
                "title": "Free Bitcoin",
                "severity": "low",
                "category": "spam",
                "removal_reason": "Spam.",
                "action": "remove",
                "confidence": 0.9,
                "explanation": "Spam keywords.",
                "source": "ai",
                "created_at": "2024-01-01T00:00:00",
            }
        ],
        stats={"total": 1, "by_severity": {"low": 1}, "by_category": {"spam": 1}, "by_action": {"remove": 1}},
    )
    app = create_app(CFG, audit=audit)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"sentrx_q_dev" in resp.data


def test_index_shows_queue_item(client):
    resp = client.get("/")
    assert b"Free Bitcoin" in resp.data
    assert b"spammer" in resp.data


def test_stats_page_returns_200(client):
    resp = client.get("/stats")
    assert resp.status_code == 200


def test_api_queue_returns_json(client):
    resp = client.get("/api/queue")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["item_id"] == "abc1"


def test_api_stats_returns_json(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert data["by_category"]["spam"] == 1


def test_action_post_redirects(client):
    resp = client.post("/action", data={"item_id": "abc1", "action": "remove"})
    assert resp.status_code == 302  # redirect back to index


def test_playtest_banner_visible(client):
    resp = client.get("/")
    assert b"sentrx_q_dev" in resp.data
    assert b"Playtest" in resp.data or b"playtest" in resp.data.lower()


def test_auto_actions_disabled_shown(client):
    resp = client.get("/")
    assert b"DISABLED" in resp.data


def test_index_empty_queue():
    audit = _mock_audit(items=[])
    app = create_app(CFG, audit=audit)
    app.config["TESTING"] = True
    with app.test_client() as c:
        resp = c.get("/")
        assert resp.status_code == 200
        assert b"No items" in resp.data


def test_api_queue_forbidden_without_feature():
    """API endpoints return 403 when api_access tier feature is disabled."""
    cfg_no_api = {
        "dashboard": {"secret_key": "test-secret", "page_size": 10},
        "triage": {"auto_actions": False},
    }
    audit = _mock_audit()
    app = create_app(cfg_no_api, audit=audit)
    app.config["TESTING"] = True
    with app.test_client() as c:
        resp = c.get("/api/queue")
        assert resp.status_code == 403
        assert b"free tier" in resp.data.lower()


def test_api_stats_forbidden_without_feature():
    """API stats endpoint returns 403 when api_access tier feature is disabled."""
    cfg_no_api = {
        "dashboard": {"secret_key": "test-secret", "page_size": 10},
        "triage": {"auto_actions": False},
    }
    audit = _mock_audit()
    app = create_app(cfg_no_api, audit=audit)
    app.config["TESTING"] = True
    with app.test_client() as c:
        resp = c.get("/api/stats")
        assert resp.status_code == 403
