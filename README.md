# Oracle Fusion Cloud Readiness Tracker

Automatically checks Oracle's public **Cloud Applications Readiness** site
every day for new or changed "What's New" pages, and reports a summarized
diff so you never have to manually re-check the site to catch new features
ahead of each quarterly release (e.g. 26A/26B/26C/26D). Reports are split
into five categories: **SCM, Finance, PPM, AI, and Redwood**.

## Categories

See `scripts/module_scope.py` for the exact definitions.

- **SCM** — Order Management, Procurement, Inventory Management, Product
  Lifecycle Management (PIM), and the planning family (Supply Planning,
  Demand Management, Sales and Operations Planning).
- **Finance** — features from the Financials and Self Service Financials
  modules, narrowed to five sub-areas: General Ledger, Accounts Payable,
  Accounts Receivable, Fixed Assets, and Cash Management. Oracle doesn't
  actually label features with those five names (its own "Area" labels are
  far more granular and change every release, e.g. "Cash Processing Agent"
  or "Payables Agent"), so matching is by keyword against those labels —
  a heuristic, refined by watching real output over time.
- **PPM** — the Project Management module (Oracle's name for Project
  Portfolio Management in its readiness pages).
- **AI** — not a module. Any feature from any tracked module (SCM, Finance,
  or PPM) that Oracle tags "AI agent" or "Agentic app".
- **Redwood** — same idea, for features tagged "Redwood Platform". (There's
  no dedicated "Redwood" readiness page — the "Adopt Redwood" page is a
  static getting-started guide with no quarterly feature list, so this has
  to be tag-based like AI.)

Everything else Oracle publishes under the SCM and ERP readiness pillars
(Manufacturing, Warehouse Management, Transportation Management, HCM, EPM,
Sales, Service, Marketing, Common Technologies, etc.) is intentionally
ignored — AI/Redwood scanning is scoped to the modules above, not
everything Oracle publishes. To change scope, edit `module_scope.py`; both
the daily checker and the summary tool import from there.

## How it works

1. **Daily checker** (`.github/workflows/daily-scm-update.yml`, runs every
   day at 06:00 UTC, or manually via **Actions → Daily Oracle Fusion
   Readiness Update Check → Run workflow**): `scripts/check_scm_updates.py`
   fetches Oracle's SCM and ERP readiness pages, extracts every tracked
   module's "What's New" page, and diffs that list against the previous
   day's snapshot in `data/state.json`. For each category (SCM/Finance/PPM)
   with new or changed pages that day:
   - A dated report is written to `updates/YYYY-MM-DD-<category>.md`.
   - `CHANGELOG.md` gets a new entry for that category.
   - A GitHub Issue is opened (labeled e.g. `oracle-finance-update`).
   - That category's report is sent to Telegram, if configured.

   AI and Redwood aren't covered by the daily checker — they're feature-tag
   classifications that require crawling deep into each module's feature
   table (see below), not simple "a new module page appeared" events. If
   nothing changed that day, the workflow exits quietly — no commit, no
   issue, no Telegram message.

2. **On-demand full summary** (`.github/workflows/build-latest-summary.yml`,
   manual trigger only): `scripts/build_latest_summary.py` crawls every
   tracked module's current-release feature table once, then builds five
   separate documents — `docs/Latest_Update_Summary_<Category>.md` for
   SCM/Finance/PPM/AI/Redwood — each with its own condensed Telegram digest
   (`..._telegram.txt`). This is the only path that produces AI/Redwood
   reports, since those require the full crawl.

3. **On-demand via Telegram** (`.github/workflows/telegram-on-demand.yml`):
   polls Telegram every 5 minutes (GitHub Actions' practical minimum for
   scheduled workflows — expect a few minutes' delay, not an instant reply)
   for a message from you containing one of: `hi`, `hello`, `hey`,
   `update`, `status`, `/start`, `/update`. If it sees one, it rebuilds all
   five summaries fresh and replies to whichever chat sent it with all five
   digests + attached reports. The last processed message is tracked in
   `data/telegram_offset.json` so the same message never gets two replies.
   Only needs `TELEGRAM_BOT_TOKEN` (not the chat ID secret, since it replies
   to whoever messaged it).

## AI-written summaries (optional)

If you add an `ANTHROPIC_API_KEY` repository secret (**Settings → Secrets
and variables → Actions**), the daily checker uses Claude to turn each
category's raw list of new pages into a short narrative summary (grouped
by module, with likely impact) instead of just a bullet list of links.
Without the secret, it still fully works — you just get the plain
bullet-list version.

## Telegram delivery (optional)

All three workflows will post to Telegram automatically once you add two
repository secrets. Setup (one-time, on your end — this can't be done for
you since it requires a Telegram account):

1. **Create a bot**: open a chat with [@BotFather](https://t.me/BotFather)
   on Telegram, send `/newbot`, and follow the prompts. It replies with a
   token that looks like `123456789:AAH...`. This is `TELEGRAM_BOT_TOKEN`.
2. **Get your chat ID**:
   - For a personal DM: send any message to your new bot first (bots can't
     message you until you've messaged them), then open
     `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser —
     the JSON response has `message.chat.id`.
   - For a group: add the bot to the group, send a message in the group,
     then use the same `getUpdates` URL — the group's `chat.id` is
     negative (e.g. `-123456789`).
3. **Add both as repo secrets**: **Settings → Secrets and variables →
   Actions → New repository secret** — add `TELEGRAM_BOT_TOKEN` and
   `TELEGRAM_CHAT_ID`.

Once both secrets exist, the next run of any workflow will deliver to
Telegram automatically — no code changes needed. Without them, all three
workflows skip the Telegram send silently and continue normally (GitHub
issue/commit still happen for the daily checker).

## Repository layout

```
.github/workflows/daily-scm-update.yml       # daily cron + manual trigger
.github/workflows/build-latest-summary.yml   # on-demand full current-release summaries
.github/workflows/telegram-on-demand.yml     # poll Telegram, reply to "hi" etc.
scripts/check_scm_updates.py                 # fetch, diff, summarize, report (SCM/Finance/PPM)
scripts/build_latest_summary.py              # on-demand full summaries (all 5 categories)
scripts/telegram_on_demand.py                # poll + reply logic
scripts/send_telegram.py                     # Telegram Bot API delivery
scripts/module_scope.py                      # category/keyword/tag definitions
scripts/requirements.txt                     # Python dependencies
data/state.json                              # last-known snapshot (auto-updated)
data/telegram_offset.json                    # last Telegram message processed (auto-updated)
updates/YYYY-MM-DD-<category>.md             # one report per day per category with changes
docs/Latest_Update_Summary_<Category>.md     # full current-release summary per category (on demand)
CHANGELOG.md                                 # running index of update days
```

## Running it locally

```bash
pip install -r scripts/requirements.txt
python scripts/check_scm_updates.py
```

This will fetch the live Oracle pages, compare against `data/state.json`,
and (if there's anything new) write a report per category under
`updates/` — useful for testing changes to the scraper before they run on
schedule.

## Notes

- This project only reads Oracle's **public** readiness pages; it does not
  require or use an Oracle Support / My Oracle Support login.
- Not affiliated with or endorsed by Oracle. Always confirm feature details
  against the official Oracle Fusion Cloud Readiness pages before acting on
  them.
- The Finance sub-area keyword matching is a heuristic (see Categories
  above) — treat it as a starting point and refine `FINANCE_SUBAREA_KEYWORDS`
  in `scripts/module_scope.py` as you see real output diverge from what you
  expect.
