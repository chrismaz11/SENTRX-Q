"""Mod-action runner for SENTRX-Q.

Evaluates a :class:`~bot.ai_triage.TriageResult` against the configuration
and — if ``auto_actions`` is enabled and the confidence threshold is met —
executes the recommended action via the :class:`~bot.reddit_client.RedditClient`.

All decisions (both automated and skipped) are written to the audit log.
"""

from __future__ import annotations

import logging
from typing import Any

from bot.ai_triage import TriageResult
from bot.reddit_client import ModQueueItem, RedditClient
from database.models import AuditLog

logger = logging.getLogger(__name__)


class ActionRunner:
    """Decide whether and how to act on a triage result."""

    def __init__(
        self,
        reddit: RedditClient,
        audit: AuditLog,
        cfg: dict[str, Any],
    ) -> None:
        triage_cfg = cfg.get("triage", {})
        self._reddit = reddit
        self._audit = audit
        self._auto_actions: bool = bool(triage_cfg.get("auto_actions", False))
        self._confidence_threshold: float = float(triage_cfg.get("confidence_threshold", 0.85))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, item: ModQueueItem, result: TriageResult) -> str:
        """Apply the triage result to *item*.

        Returns a short string describing what was done (for logging /
        dashboard display).
        """
        self._audit.log_triage(item, result)

        if not self._auto_actions:
            logger.debug(
                "auto_actions disabled — skipping automated action for %s.", item.item_id
            )
            return "queued"

        if result.confidence < self._confidence_threshold:
            logger.info(
                "Confidence %.2f below threshold %.2f for %s — skipping action.",
                result.confidence,
                self._confidence_threshold,
                item.item_id,
            )
            self._audit.log_action(item.item_id, "skipped_low_confidence")
            return "skipped_low_confidence"

        action = result.action
        try:
            if action == "remove":
                self._reddit.remove(item, mod_note=result.removal_reason)
                self._audit.log_action(item.item_id, "removed")
                return "removed"

            if action == "approve":
                self._reddit.approve(item)
                self._audit.log_action(item.item_id, "approved")
                return "approved"

            if action == "escalate":
                # Lock the item and flag it for human review
                self._reddit.lock(item)
                self._audit.log_action(item.item_id, "escalated")
                logger.warning(
                    "ESCALATED item %s in r/%s — %s / %s",
                    item.item_id,
                    item.subreddit,
                    result.category,
                    result.severity,
                )
                return "escalated"

        except Exception as exc:
            logger.error("Action %r failed for %s: %s", action, item.item_id, exc)
            self._audit.log_action(item.item_id, f"error:{exc!s}")
            return f"error:{exc!s}"

        return "no_action"
