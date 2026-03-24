"""Fallback heuristics triage for SENTRX-Q.

Used when the OpenAI API is unavailable or rate-limited.  Returns a
:class:`~bot.ai_triage.TriageResult` in the same format as the AI engine so
the rest of the pipeline is unaffected.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from bot.ai_triage import SEVERITY_LEVELS, TriageResult
from bot.reddit_client import ModQueueItem

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Keyword → (category, severity, action) mappings
# Each pattern is matched case-insensitively against the combined text.
# ──────────────────────────────────────────────────────────────────────────────
_RULES: list[tuple[re.Pattern[str], str, str, str]] = [
    # (pattern, category, severity, action)
    (re.compile(r"\bkill\s+your?self\b|\bkys\b", re.I), "threat", "critical", "escalate"),
    (re.compile(r"\bsuicid\w*\b|\bend\s+it\s+all\b|\bwant\s+to\s+die\b", re.I), "self_harm", "critical", "escalate"),
    (re.compile(r"\bcsam\b|\bchild\s+porn\b|\bcp\s+link\b", re.I), "csam", "critical", "escalate"),
    (re.compile(r"\bdoxx(ing|ed)?\b|\bpersonal\s+info\b|\breal\s+address\b", re.I), "doxxing", "high", "remove"),
    (re.compile(r"\bn[i1][g6]{2}(er|a)\b|\bfagg?[o0]t\b|\btr[a@]nn[yi]\b", re.I), "hate_speech", "high", "remove"),
    (
        re.compile(r"\bi\s+will\s+(kill|hurt|attack|shoot)\b|\bwatch\s+your\s+back\b", re.I),
        "threat", "high", "remove",
    ),
    (
        re.compile(r"\bbuy\s+(now|cheap|discount)\b|\bclick\s+here\b|\bfree\s+bitcoin\b|\bpromo\s+code\b", re.I),
        "spam", "low", "remove",
    ),
    (
        re.compile(r"\bfake\s+news\b|\bhoax\b|\bconspiracy\b|\bwake\s+up\s+sheeple\b", re.I),
        "misinformation", "medium", "none",
    ),
    (re.compile(r"\bstop\s+spamming\b|\bban\s+evasion\b|\balt\s+account\b", re.I), "ban_evasion", "medium", "remove"),
]

_BASE_CONFIDENCE = 0.60  # heuristics are less reliable than AI


def triage_heuristic(item: ModQueueItem, cfg: dict[str, Any] | None = None) -> TriageResult:
    """Analyse *item* using keyword rules and return a :class:`TriageResult`.

    Parameters
    ----------
    item:
        The mod-queue item to analyse.
    cfg:
        Optional config dict (unused but kept for API symmetry with the AI engine).
    """
    text = _combined_text(item)
    matched: list[tuple[str, str, str]] = []

    for pattern, category, severity, action in _RULES:
        if pattern.search(text):
            matched.append((category, severity, action))
            logger.debug("Heuristic match for %s: %s (%s)", item.item_id, category, severity)

    if not matched:
        return TriageResult(
            item_id=item.item_id,
            severity="low",
            category="none",
            removal_reason="",
            action="none",
            confidence=_BASE_CONFIDENCE,
            explanation="No keyword rules matched.",
            source="heuristic",
        )

    # Escalate to the worst-matched severity
    severity_rank = {s: i for i, s in enumerate(SEVERITY_LEVELS)}
    matched.sort(key=lambda t: severity_rank.get(t[1], 0), reverse=True)
    top_category, top_severity, top_action = matched[0]

    # Slightly raise confidence when multiple rules fire
    confidence = min(0.80, _BASE_CONFIDENCE + 0.04 * len(matched))

    reason_map = {
        "spam": "This content appears to be unsolicited advertising or spam.",
        "harassment": "This content contains targeted harassment.",
        "hate_speech": "This content contains hate speech or slurs.",
        "misinformation": "This content may spread false information.",
        "threat": "This content contains threatening language.",
        "self_harm": "This content may relate to self-harm or suicide.",
        "csam": "This content may involve CSAM — escalated for immediate review.",
        "doxxing": "This content may expose personal information (doxxing).",
        "ban_evasion": "Suspected ban evasion or alternate account.",
        "off_topic": "This content is off-topic for the subreddit.",
        "other": "This content violates subreddit rules.",
        "none": "",
    }

    return TriageResult(
        item_id=item.item_id,
        severity=top_severity,
        category=top_category,
        removal_reason=reason_map.get(top_category, ""),
        action=top_action,
        confidence=confidence,
        explanation=f"Keyword heuristic matched {len(matched)} rule(s): "
        + ", ".join(f"{c}({s})" for c, s, _ in matched),
        source="heuristic",
    )


def _combined_text(item: ModQueueItem) -> str:
    parts = [item.title, item.body] + item.report_reasons
    return " ".join(p for p in parts if p)
