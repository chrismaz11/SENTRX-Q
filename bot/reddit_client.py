"""Reddit client for SENTRX-Q.

Wraps PRAW to provide:
* OAuth2 password-flow authentication
* Mod-queue fetching across multiple subreddits
* High-level mod actions (remove, approve, ban, lock)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Generator

import praw
import praw.models

logger = logging.getLogger(__name__)


@dataclass
class ModQueueItem:
    """A normalised representation of a single mod-queue entry."""

    item_id: str
    item_type: str  # "submission" | "comment"
    subreddit: str
    author: str
    title: str
    body: str
    permalink: str
    report_reasons: list[str] = field(default_factory=list)
    score: int = 0
    num_reports: int = 0
    raw: Any = field(default=None, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "subreddit": self.subreddit,
            "author": self.author,
            "title": self.title,
            "body": self.body,
            "permalink": self.permalink,
            "report_reasons": self.report_reasons,
            "score": self.score,
            "num_reports": self.num_reports,
        }


class RedditClient:
    """Authenticated PRAW-based Reddit client."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        reddit_cfg = cfg.get("reddit", {})
        self._reddit = praw.Reddit(
            client_id=reddit_cfg["client_id"],
            client_secret=reddit_cfg["client_secret"],
            username=reddit_cfg["username"],
            password=reddit_cfg["password"],
            user_agent=reddit_cfg.get("user_agent", "SENTRX-Q/0.1.0"),
        )
        self._subreddits: list[str] = reddit_cfg.get("subreddits", [])
        self._fetch_limit: int = int(reddit_cfg.get("fetch_limit", 100))
        logger.info("RedditClient initialised for subreddits: %s", self._subreddits)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_mod_queue(self, subreddit: str | None = None) -> list[ModQueueItem]:
        """Return all items currently in the mod queue.

        Parameters
        ----------
        subreddit:
            Override the configured subreddit list and fetch from a single sub.
        """
        targets = [subreddit] if subreddit else self._subreddits
        items: list[ModQueueItem] = []
        for sub_name in targets:
            items.extend(self._fetch_from_subreddit(sub_name))
        logger.info("Fetched %d mod-queue items total.", len(items))
        return items

    def remove(self, item: ModQueueItem, mod_note: str = "") -> None:
        """Remove a submission or comment from Reddit."""
        raw = item.raw
        if raw is None:
            logger.warning("Cannot remove item %s — no raw PRAW object.", item.item_id)
            return
        raw.mod.remove(mod_note=mod_note)
        logger.info("Removed %s (%s).", item.item_id, item.item_type)

    def approve(self, item: ModQueueItem) -> None:
        """Approve a submission or comment."""
        raw = item.raw
        if raw is None:
            logger.warning("Cannot approve item %s — no raw PRAW object.", item.item_id)
            return
        raw.mod.approve()
        logger.info("Approved %s (%s).", item.item_id, item.item_type)

    def ban_author(
        self,
        item: ModQueueItem,
        duration: int | None = None,
        reason: str = "",
        note: str = "",
    ) -> None:
        """Ban the author of a mod-queue item from the subreddit."""
        raw = item.raw
        if raw is None or item.author == "[deleted]":
            logger.warning("Cannot ban author of %s.", item.item_id)
            return
        sub = self._reddit.subreddit(item.subreddit)
        kwargs: dict[str, Any] = {"ban_reason": reason[:100], "note": note[:300]}
        if duration is not None:
            kwargs["duration"] = duration
        sub.banned.add(item.author, **kwargs)
        logger.info("Banned u/%s from r/%s.", item.author, item.subreddit)

    def lock(self, item: ModQueueItem) -> None:
        """Lock a submission or comment."""
        raw = item.raw
        if raw is None:
            return
        raw.mod.lock()
        logger.info("Locked %s.", item.item_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_from_subreddit(self, sub_name: str) -> Generator[ModQueueItem, None, None]:
        sub = self._reddit.subreddit(sub_name)
        try:
            for item in sub.mod.queue(limit=self._fetch_limit):
                yield self._normalise(item, sub_name)
        except Exception as exc:
            logger.error("Error fetching queue for r/%s: %s", sub_name, exc)

    @staticmethod
    def _normalise(item: Any, sub_name: str) -> ModQueueItem:
        is_submission = isinstance(item, praw.models.Submission)
        author = str(item.author) if item.author else "[deleted]"
        report_reasons: list[str] = []
        for reason, _ in (item.user_reports or []):
            report_reasons.append(str(reason))
        for reason in (item.mod_reports or []):
            report_reasons.append(str(reason[0]) if isinstance(reason, (list, tuple)) else str(reason))

        return ModQueueItem(
            item_id=item.id,
            item_type="submission" if is_submission else "comment",
            subreddit=sub_name,
            author=author,
            title=item.title if is_submission else "",
            body=item.selftext if is_submission else item.body,
            permalink=f"https://reddit.com{item.permalink}",
            report_reasons=report_reasons,
            score=item.score,
            num_reports=len(report_reasons),
            raw=item,
        )
