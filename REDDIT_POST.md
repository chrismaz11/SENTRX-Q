# Reddit Post Draft — SENTRX-Q

> Ready to copy into r/redditdev, r/Python, or r/modhelp.

---

**Title:**
`[Open Source] SENTRX-Q — AI-powered mod queue triage bot (GPT-4 + heuristics, Flask dashboard, full audit log)`

---

**Body:**

Tired of manually reviewing hundreds of mod queue items? I built **SENTRX-Q** to fix that.

SENTRX-Q is an open-source Reddit mod-queue triage bot that uses GPT-4 to automatically classify the severity of each item, categorise the violation, suggest a removal reason, and optionally take action — all with a full audit log so nothing slips through the cracks. When the AI is unavailable it falls back to fast keyword-based heuristics, so it keeps working even without an OpenAI key.

**Key features:**

- 🤖 **GPT-4 AI triage** — severity scoring (low/medium/high/critical), violation categorisation, confidence scoring
- 🔍 **Heuristic fallback** — 9 keyword rules, zero external dependencies
- 🖥️ **Flask web dashboard** — prioritised queue view, quick-action buttons, colour-coded severity bars, stats page
- 🗄️ **Full audit log** — every AI decision and mod action stored in SQLite via SQLAlchemy
- ⚙️ **Safe defaults** — auto-actions are `false` out of the box; you enable them only when ready
- ✅ **Full test suite** — mocked PRAW + OpenAI, passing on Python 3.10 / 3.11 / 3.12

**Playtest subreddit:** [r/sentrx_q_dev](https://www.reddit.com/r/sentrx_q_dev/?playtest=sentrx-q) — spin it up and see it triage live posts right now.

**GitHub:** https://github.com/chrismaz11/SENTRX-Q

It's **MIT licensed and free to self-host** — clone the repo, drop in your Reddit API creds and an OpenAI key, and you're live in under 5 minutes.

---

**Coming soon (pro/enterprise tiers):**

- ⚡ AI triage fully unlocked (GPT-4 auto-classification at scale)
- 🤖 Automated mod actions with confidence gating
- 🌐 Multi-subreddit monitoring from a single dashboard
- 🔧 Custom keyword rule sets per subreddit
- 📬 Webhook / Slack / Discord alerts for critical escalations

---

**Star the repo, try the playtest, and let me know what you think!**
Any feedback on the triage accuracy, dashboard UX, or features you'd want in a hosted version is hugely appreciated. 🙏
