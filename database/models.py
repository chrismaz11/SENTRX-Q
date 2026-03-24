"""Database models and audit log for SENTRX-Q.

Uses SQLAlchemy 2.x with a SQLite backend.  Two tables are maintained:

* ``triage_results``  — every AI / heuristic decision
* ``mod_actions``     — every action taken (or skipped) by the runner
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from bot.ai_triage import TriageResult
from bot.reddit_client import ModQueueItem

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# ORM Base & models
# ──────────────────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


class TriageRecord(Base):
    """Persisted record of an AI / heuristic triage decision."""

    __tablename__ = "triage_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String(32), nullable=False, index=True)
    item_type = Column(String(16))
    subreddit = Column(String(128))
    author = Column(String(128))
    title = Column(Text)
    severity = Column(String(16))
    category = Column(String(32))
    removal_reason = Column(Text)
    action = Column(String(32))
    confidence = Column(Float)
    explanation = Column(Text)
    source = Column(String(16))  # "ai" | "heuristic" | "error"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ModActionRecord(Base):
    """Persisted record of a moderator action taken by the runner."""

    __tablename__ = "mod_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String(32), nullable=False, index=True)
    action_taken = Column(String(64))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ──────────────────────────────────────────────────────────────────────────────
# AuditLog façade
# ──────────────────────────────────────────────────────────────────────────────


class AuditLog:
    """High-level interface for reading and writing the audit database."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        db_path: str = cfg.get("database", {}).get("path", "sentrx_q.db")
        db_url = f"sqlite:///{db_path}"
        self._engine = create_engine(db_url, echo=False)

        # Enable WAL mode for better concurrent read performance
        @event.listens_for(self._engine, "connect")
        def _set_wal(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)
        logger.info("AuditLog database opened at %s", db_url)

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def log_triage(self, item: ModQueueItem, result: TriageResult) -> None:
        """Persist a triage decision to the database."""
        record = TriageRecord(
            item_id=item.item_id,
            item_type=item.item_type,
            subreddit=item.subreddit,
            author=item.author,
            title=item.title,
            severity=result.severity,
            category=result.category,
            removal_reason=result.removal_reason,
            action=result.action,
            confidence=result.confidence,
            explanation=result.explanation,
            source=result.source,
        )
        with self._Session() as session:
            session.add(record)
            session.commit()
        logger.debug("Logged triage for %s (%s / %s).", item.item_id, result.severity, result.category)

    def log_action(self, item_id: str, action_taken: str) -> None:
        """Persist a mod action to the database."""
        record = ModActionRecord(item_id=item_id, action_taken=action_taken)
        with self._Session() as session:
            session.add(record)
            session.commit()
        logger.debug("Logged action %r for %s.", action_taken, item_id)

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def recent_triage_results(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent triage records as plain dicts."""
        with self._Session() as session:
            rows = (
                session.query(TriageRecord)
                .order_by(TriageRecord.created_at.desc())
                .limit(limit)
                .all()
            )
        return [self._triage_to_dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """Return aggregate statistics for the dashboard."""
        with self._Session() as session:
            total = session.query(TriageRecord).count()
            by_severity: dict[str, int] = {}
            by_category: dict[str, int] = {}
            by_action: dict[str, int] = {}
            for row in session.query(TriageRecord).all():
                by_severity[row.severity] = by_severity.get(row.severity, 0) + 1
                by_category[row.category] = by_category.get(row.category, 0) + 1
                by_action[row.action] = by_action.get(row.action, 0) + 1
        return {
            "total": total,
            "by_severity": by_severity,
            "by_category": by_category,
            "by_action": by_action,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _triage_to_dict(row: TriageRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "item_id": row.item_id,
            "item_type": row.item_type,
            "subreddit": row.subreddit,
            "author": row.author,
            "title": row.title,
            "severity": row.severity,
            "category": row.category,
            "removal_reason": row.removal_reason,
            "action": row.action,
            "confidence": row.confidence,
            "explanation": row.explanation,
            "source": row.source,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
