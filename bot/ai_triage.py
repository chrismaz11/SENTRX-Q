"""AI triage engine for SENTRX-Q.

Uses OpenAI GPT-4 to:
* Classify the *severity* of a mod-queue item (low / medium / high / critical)
* Categorise the type of violation
* Suggest a human-readable removal reason
* Produce a confidence score (0.0 – 1.0)

The result is a :class:`TriageResult` dataclass that is stored in the audit
database and optionally used to drive automatic mod actions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import openai

from bot.reddit_client import ModQueueItem

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Severity levels (ordered)
# ──────────────────────────────────────────────────────────────────────────────
SEVERITY_LEVELS = ("low", "medium", "high", "critical")

# ──────────────────────────────────────────────────────────────────────────────
# Violation categories
# ──────────────────────────────────────────────────────────────────────────────
VIOLATION_CATEGORIES = (
    "spam",
    "harassment",
    "hate_speech",
    "misinformation",
    "threat",
    "self_harm",
    "csam",
    "doxxing",
    "ban_evasion",
    "off_topic",
    "other",
    "none",
)

_SYSTEM_PROMPT = """\
You are an expert Reddit moderator assistant.  Given a mod-queue item you must
return a JSON object (and nothing else) with the following fields:

{
  "severity":        "<low|medium|high|critical>",
  "category":        "<one of the violation categories below>",
  "removal_reason":  "<concise, human-readable reason for removal, or empty string if no removal>",
  "action":          "<remove|approve|escalate|none>",
  "confidence":      <float 0.0–1.0>,
  "explanation":     "<brief reasoning>"
}

Violation categories: spam, harassment, hate_speech, misinformation, threat,
self_harm, csam, doxxing, ban_evasion, off_topic, other, none.

Rules:
* Use "critical" severity for threats, self-harm, CSAM, or doxxing.
* Use "none" category when no rule is broken.
* Set action to "escalate" for critical severity items.
* Confidence must reflect genuine uncertainty; never output exactly 1.0.
* Output valid JSON only — no markdown, no prose.
"""


@dataclass
class TriageResult:
    """The structured output of one AI triage run."""

    item_id: str
    severity: str
    category: str
    removal_reason: str
    action: str
    confidence: float
    explanation: str
    source: str = "ai"  # "ai" | "heuristic" | "error"

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "severity": self.severity,
            "category": self.category,
            "removal_reason": self.removal_reason,
            "action": self.action,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "source": self.source,
        }


class AITriageEngine:
    """Calls OpenAI to triage a :class:`~bot.reddit_client.ModQueueItem`."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        openai_cfg = cfg.get("openai", {})
        self._client = openai.OpenAI(api_key=openai_cfg.get("api_key", ""))
        self._model: str = openai_cfg.get("model", "gpt-4")
        self._max_tokens: int = int(openai_cfg.get("max_tokens", 512))
        self._temperature: float = float(openai_cfg.get("temperature", 0.2))
        self._escalation_categories: list[str] = (
            cfg.get("triage", {}).get("escalation_categories", ["threat", "self_harm", "csam"])
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def triage(self, item: ModQueueItem) -> TriageResult:
        """Return a :class:`TriageResult` for the given mod-queue item."""
        prompt = self._build_prompt(item)
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            raw_json = response.choices[0].message.content or ""
            return self._parse_response(item.item_id, raw_json)
        except openai.OpenAIError as exc:
            logger.warning("OpenAI API error for %s: %s — falling back to heuristics.", item.item_id, exc)
            raise
        except Exception as exc:
            logger.error("Unexpected error triaging %s: %s", item.item_id, exc)
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(item: ModQueueItem) -> str:
        lines = [
            f"Subreddit: r/{item.subreddit}",
            f"Type: {item.item_type}",
            f"Author: u/{item.author}",
        ]
        if item.title:
            lines.append(f"Title: {item.title}")
        if item.body:
            body_snippet = item.body[:1500]
            lines.append(f"Body:\n{body_snippet}")
        if item.report_reasons:
            lines.append("Report reasons: " + "; ".join(item.report_reasons))
        return "\n".join(lines)

    @staticmethod
    def _parse_response(item_id: str, raw: str) -> TriageResult:
        """Parse the raw JSON string returned by the model."""
        raw = raw.strip()
        # Strip markdown code fences if the model wraps the JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("Could not parse AI response: %s — raw: %r", exc, raw)
            return TriageResult(
                item_id=item_id,
                severity="medium",
                category="other",
                removal_reason="",
                action="none",
                confidence=0.0,
                explanation="Failed to parse AI response.",
                source="error",
            )

        severity = data.get("severity", "medium")
        if severity not in SEVERITY_LEVELS:
            severity = "medium"

        category = data.get("category", "other")
        if category not in VIOLATION_CATEGORIES:
            category = "other"

        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(0.99, confidence))

        return TriageResult(
            item_id=item_id,
            severity=severity,
            category=category,
            removal_reason=str(data.get("removal_reason", "")),
            action=str(data.get("action", "none")),
            confidence=confidence,
            explanation=str(data.get("explanation", "")),
            source="ai",
        )
