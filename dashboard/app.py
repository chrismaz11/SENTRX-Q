"""Flask web dashboard for SENTRX-Q.

Routes
------
GET  /             Prioritised queue view with quick-action buttons
GET  /stats        Aggregate statistics
POST /action       Execute a manual mod action (approve / remove / escalate)
GET  /api/queue    JSON feed of recent triage results
GET  /api/stats    JSON feed of aggregate stats
"""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, url_for

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def create_app(cfg: dict[str, Any], audit=None, reddit=None) -> Flask:
    """Application factory.

    Parameters
    ----------
    cfg:
        Loaded SENTRX-Q config dict.
    audit:
        :class:`~database.models.AuditLog` instance (injected for testability).
    reddit:
        :class:`~bot.reddit_client.RedditClient` instance (injected for testability).
    """
    dash_cfg = cfg.get("dashboard", {})
    secret_key = dash_cfg.get("secret_key", os.urandom(24).hex())
    page_size = int(dash_cfg.get("page_size", 25))

    app = Flask(__name__, template_folder="templates")
    app.secret_key = secret_key

    # Stash dependencies in app config for access inside views
    app.config["AUDIT"] = audit
    app.config["REDDIT"] = reddit
    app.config["PAGE_SIZE"] = page_size

    # ------------------------------------------------------------------
    # HTML views
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        audit_log = app.config.get("AUDIT")
        items = audit_log.recent_triage_results(page_size * 4) if audit_log else []
        # Sort by severity (critical first), then confidence descending
        items.sort(
            key=lambda i: (
                _SEVERITY_ORDER.get(i.get("severity", "low"), 3),
                -(i.get("confidence") or 0),
            )
        )
        items = items[:page_size]
        return render_template("index.html", items=items, cfg=cfg)

    @app.route("/stats")
    def stats():
        audit_log = app.config.get("AUDIT")
        data = audit_log.stats() if audit_log else {}
        return render_template("stats.html", stats=data, cfg=cfg)

    @app.route("/action", methods=["POST"])
    def action():
        item_id = request.form.get("item_id", "")
        act = request.form.get("action", "")
        audit_log = app.config.get("AUDIT")
        reddit_client = app.config.get("REDDIT")

        if audit_log:
            audit_log.log_action(item_id, f"manual:{act}")

        logger.info("Manual action %r on %s via dashboard.", act, item_id)
        # In a live deployment the reddit_client would be used here to carry
        # out the action; in the playtest environment the audit log is enough.
        _ = reddit_client  # reserved for live use

        return redirect(url_for("index"))

    # ------------------------------------------------------------------
    # JSON API
    # ------------------------------------------------------------------

    @app.route("/api/queue")
    def api_queue():
        audit_log = app.config.get("AUDIT")
        items = audit_log.recent_triage_results(100) if audit_log else []
        return jsonify({"items": items})

    @app.route("/api/stats")
    def api_stats():
        audit_log = app.config.get("AUDIT")
        data = audit_log.stats() if audit_log else {}
        return jsonify(data)

    return app
