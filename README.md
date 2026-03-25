# SENTRX-Q 🛡️

[![CI](https://github.com/chrismaz11/SENTRX-Q/actions/workflows/ci.yml/badge.svg)](https://github.com/chrismaz11/SENTRX-Q/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Playtest: r/sentrx_q_dev](https://img.shields.io/badge/playtest-r%2Fsentrx__q__dev-ff4500.svg)](https://www.reddit.com/r/sentrx_q_dev/?playtest=sentrx-q)

> **AI-powered Reddit mod queue triage bot** — uses GPT-4 to classify severity,
> categorise violations, suggest removal reasons, and optionally act on them
> automatically.  Every decision is audited.  A live Flask dashboard lets you
> review the queue and execute quick actions.

---

## ✨ Features

| Component | Details |
|-----------|---------|
| **Reddit Integration** | PRAW-based client, OAuth2 password-flow auth, mod-queue fetching, auto-actions |
| **AI Triage Engine** | OpenAI GPT-4 — classifies severity (`low`/`medium`/`high`/`critical`), categorises violations, suggests removal reasons, confidence scoring |
| **Fallback Heuristics** | Keyword-based analysis when the AI is unavailable |
| **Web Dashboard** | Flask app with prioritised queue view, quick-action buttons, statistics page |
| **Database & Audit Log** | SQLite + SQLAlchemy — every AI decision and mod action logged |
| **Config System** | YAML-based config with safe defaults (`auto_actions: false`) |
| **Tests** | Full `pytest` suite with mocked Reddit / OpenAI calls |
| **CI Pipeline** | GitHub Actions running lint + tests on Python 3.10 / 3.11 / 3.12 |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        main.py                          │
│  (CLI entry-point — triage loop │ dashboard │ both)     │
└───────────────┬──────────────────────────┬──────────────┘
                │                          │
        ┌───────▼────────┐        ┌────────▼────────┐
        │  bot/          │        │  dashboard/     │
        │  reddit_client │        │  app.py (Flask) │
        │  ai_triage     │        └────────┬────────┘
        │  heuristics    │                 │
        │  actions       │        ┌────────▼────────┐
        └───────┬────────┘        │  database/      │
                │                 │  models.py      │
                └────────────────►│  (SQLite audit) │
                                  └─────────────────┘
```

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/chrismaz11/SENTRX-Q.git
cd SENTRX-Q
pip install -r requirements.txt
```

### 2. Configure credentials

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env   # then edit .env
```

```env
REDDIT_CLIENT_ID=your_app_client_id
REDDIT_CLIENT_SECRET=your_app_client_secret
REDDIT_USERNAME=your_bot_reddit_username
REDDIT_PASSWORD=your_bot_reddit_password
OPENAI_API_KEY=sk-...
DASHBOARD_SECRET_KEY=change_me_in_production
```

> **Reddit API credentials** — create an app at
> <https://www.reddit.com/prefs/apps> (choose *script* type).

### 3. Start the playtest environment

The official playtest subreddit is
[**r/sentrx_q_dev**](https://www.reddit.com/r/sentrx_q_dev/?playtest=sentrx-q).
The default config already points there so you can start triaging immediately:

```bash
# Single triage pass (safe, no auto-actions by default)
python main.py triage --once

# Start the web dashboard
python main.py dashboard
# → open http://127.0.0.1:5000

# Run both together
python main.py run
```

### 4. Enable auto-actions (optional)

Edit `config/default.yml` and set:

```yaml
triage:
  auto_actions: true          # ⚠️  validate on playtest first!
  confidence_threshold: 0.85  # only fire actions above this confidence
```

---

## ⚙️ Configuration Reference

All settings live in `config/default.yml`.  Every value can be overridden by an
environment variable using `${VAR_NAME}` / `${VAR_NAME:-default}` syntax.

| Key | Default | Description |
|-----|---------|-------------|
| `reddit.subreddits` | `[sentrx_q_dev]` | Subreddits to monitor |
| `reddit.fetch_limit` | `100` | Items fetched per poll |
| `openai.model` | `gpt-4` | OpenAI model to use |
| `triage.auto_actions` | `false` | **Keep false until validated** |
| `triage.confidence_threshold` | `0.85` | Minimum confidence to trigger auto-action |
| `triage.escalation_categories` | `[threat, self_harm, csam]` | Categories that always escalate |
| `database.path` | `sentrx_q.db` | SQLite file path |
| `dashboard.port` | `5000` | Dashboard port |

---

## 🧪 Running Tests

```bash
pytest                    # full suite with coverage
pytest tests/test_heuristics.py -v   # single module
```

The test suite uses mocked PRAW and OpenAI clients — no real API calls.

---

## 📁 Project Structure

```
SENTRX-Q/
├── bot/
│   ├── reddit_client.py   # PRAW client — auth, mod-queue, actions
│   ├── ai_triage.py       # GPT-4 triage engine
│   ├── heuristics.py      # Keyword-based fallback
│   └── actions.py         # Auto-action runner
├── dashboard/
│   ├── app.py             # Flask application factory
│   └── templates/         # Jinja2 HTML templates
├── database/
│   └── models.py          # SQLAlchemy models + AuditLog
├── config/
│   └── default.yml        # YAML config (safe defaults)
├── tests/                 # pytest suite (all mocked)
├── .github/workflows/
│   └── ci.yml             # GitHub Actions CI
├── config.py              # Config loader (env-var expansion)
├── main.py                # CLI entry point
└── requirements.txt
```

---

## 🗺️ Roadmap

- [ ] Webhook / push notifications for critical escalations
- [ ] Multi-subreddit dashboard filter
- [ ] Rate-limit aware polling with exponential back-off
- [ ] Docker image + `docker-compose.yml`
- [ ] GPT-4o / fine-tuned model support
- [ ] Slack / Discord alert integration

---

## 💰 Support

If SENTRX-Q saves you hours of manual mod-queue review, consider supporting the project:

- ❤️ **[GitHub Sponsors](https://github.com/sponsors/chrismaz11)** — one-time or recurring support
- ☕ Ko-fi, Buy Me a Coffee, and Patreon links coming soon

Your support helps fund API costs, new features, and keeping the hosted version free for small subreddits.

---

## 🏷️ Tiers

| Tier | Price | Features |
|------|-------|----------|
| **Free** | Self-host, free forever | Heuristic triage + web dashboard |
| **Pro** *(coming soon)* | TBD | AI triage (GPT-4), auto-actions, JSON API access |
| **Enterprise** *(coming soon)* | TBD | Everything in Pro + multi-subreddit, custom rules, priority support |

The free tier is fully functional for most small-to-medium subreddits.
Feature flags live in `config/default.yml` under the `tier:` key.

---

## 📄 License

MIT © chrismaz11
