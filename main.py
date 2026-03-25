"""SENTRX-Q main entry point.

Usage
-----
  # Run the triage bot (single pass)
  python main.py triage

  # Start the web dashboard
  python main.py dashboard

  # Run both (bot loop + dashboard in background)
  python main.py run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from config import is_feature_enabled, load_config


def _setup_logging(cfg: dict) -> None:
    log_cfg = cfg.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    log_file = log_cfg.get("file", "")
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(level=level, handlers=handlers, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")


def cmd_triage(cfg: dict, once: bool = False) -> None:
    """Fetch the mod queue and triage every item."""
    from bot.actions import ActionRunner
    from bot.heuristics import triage_heuristic
    from bot.reddit_client import RedditClient
    from database.models import AuditLog

    ai_triage_enabled = is_feature_enabled(cfg, "ai_triage")

    reddit = RedditClient(cfg)
    audit = AuditLog(cfg)
    runner = ActionRunner(reddit, audit, cfg)

    if ai_triage_enabled:
        import openai

        from bot.ai_triage import AITriageEngine

        ai_engine = AITriageEngine(cfg)
        logging.info("AI triage enabled (model=%s).", cfg.get("openai", {}).get("model", "gpt-4"))
    else:
        logging.info("AI triage disabled for this tier — using heuristics only.")

    poll_interval = 60  # seconds between passes
    while True:
        logging.info("Fetching mod queue…")
        items = reddit.fetch_mod_queue()
        for item in items:
            if ai_triage_enabled:
                try:
                    result = ai_engine.triage(item)
                except openai.OpenAIError as exc:
                    logging.warning("OpenAI error for %s (%s), falling back to heuristics.", item.item_id, exc)
                    result = triage_heuristic(item, cfg=cfg)
                except Exception as exc:
                    logging.warning("AI unavailable for %s (%s), falling back to heuristics.", item.item_id, exc)
                    result = triage_heuristic(item, cfg=cfg)
            else:
                result = triage_heuristic(item, cfg=cfg)
            outcome = runner.process(item, result)
            logging.info(
                "[%s] %s — %s/%s conf=%.2f outcome=%s",
                item.subreddit,
                item.item_id,
                result.severity,
                result.category,
                result.confidence,
                outcome,
            )
        if once:
            break
        logging.info("Sleeping %ds before next poll…", poll_interval)
        time.sleep(poll_interval)


def cmd_dashboard(cfg: dict) -> None:
    """Start the Flask web dashboard."""
    from database.models import AuditLog
    from dashboard.app import create_app

    audit = AuditLog(cfg)
    app = create_app(cfg, audit=audit)
    dash_cfg = cfg.get("dashboard", {})
    app.run(host=dash_cfg.get("host", "127.0.0.1"), port=int(dash_cfg.get("port", 5000)))


def main() -> None:
    parser = argparse.ArgumentParser(description="SENTRX-Q – AI Reddit mod triage bot")
    parser.add_argument("command", choices=["triage", "dashboard", "run"], help="Command to execute")
    parser.add_argument("--config", default=None, help="Path to YAML config file")
    parser.add_argument("--once", action="store_true", help="Run triage a single time then exit")
    args = parser.parse_args()

    cfg = load_config(args.config)
    _setup_logging(cfg)

    if args.command == "triage":
        cmd_triage(cfg, once=args.once)
    elif args.command == "dashboard":
        cmd_dashboard(cfg)
    elif args.command == "run":
        import threading

        t = threading.Thread(target=cmd_triage, args=(cfg,), daemon=True)
        t.start()
        cmd_dashboard(cfg)


if __name__ == "__main__":
    main()
