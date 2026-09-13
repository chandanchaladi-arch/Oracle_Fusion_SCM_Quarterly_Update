# Oracle Fusion SCM Quarterly Update Tracker

Automatically checks Oracle's public **Cloud Applications Readiness** site
every day for new or changed "What's New" pages covering the Oracle Fusion
Cloud **Supply Chain & Manufacturing (SCM)** pillar, and reports a
summarized diff so you never have to manually re-check the site to catch
new features ahead of each quarterly release (e.g. 26A/26B/26C).

## Module scope

Only these modules are tracked (see `scripts/module_scope.py`):

- Order Management
- Procurement
- Inventory Management
- Product Lifecycle Management (PIM)
- Supply Planning, Demand Management, and Sales and Operations Planning (the "planning" family)

Everything else Oracle publishes under SCM readiness (Manufacturing,
Warehouse Management, Transportation Management, Global Trade Management,
Supply Chain Collaboration, Common Technologies, Maintenance, etc.) is
intentionally ignored. To change scope, edit `TRACKED_MODULE_PREFIXES` in
`scripts/module_scope.py` — both the daily checker and the summary tool
import from there, so it only needs to change in one place.

## How it works

1. A GitHub Actions workflow (`.github/workflows/daily-scm-update.yml`)
   runs every day at 06:00 UTC (and can be triggered manually via
   **Actions → Daily Oracle Fusion SCM Update Check → Run workflow**).
2. `scripts/check_scm_updates.py` fetches Oracle's public readiness pages:
   - https://docs.oracle.com/en/cloud/saas/readiness/scm.html (current release)
   - https://docs.oracle.com/en/cloud/saas/readiness/scm-all.html (archive of all releases)
3. It extracts every linked per-module "What's New" page within the
   tracked module scope above, and compares that list against the
   previous day's snapshot stored in `data/state.json`.
4. If any pages are new or changed:
   - A dated report is written to `updates/YYYY-MM-DD.md`.
   - `CHANGELOG.md` gets a new entry linking to that report.
   - A GitHub Issue is opened (labeled `oracle-scm-update`) containing the
     summary, so you get a notification without having to watch the repo.
   - The same summary is sent to Telegram, if configured (see below).
   - `data/state.json` is updated and all of the above is committed back
     to the repository by the workflow.
5. If nothing changed, the workflow exits quietly — no commit, no issue,
   no Telegram message.

There's also a second, manually-triggered workflow — **Build Latest SCM
Update Summary** (`.github/workflows/build-latest-summary.yml`) — for
getting a full picture of the *current* quarterly release right now,
independent of the daily diff (useful right after setup, since the daily
checker only reports future changes). It writes
`docs/Latest_SCM_Update_Summary.md` with every feature for the current
release across the tracked modules, and also sends a condensed digest +
that file to Telegram if configured.

## On-demand via Telegram ("send hi for an update")

A third workflow — **Telegram On-Demand Update**
(`.github/workflows/telegram-on-demand.yml`) — polls Telegram every 5
minutes (GitHub Actions' practical minimum for scheduled workflows; it
isn't instant like a live chatbot) for a message from you containing one
of: `hi`, `hello`, `hey`, `update`, `status`, `/start`, `/update`. If it
sees one, it rebuilds the summary fresh and replies to whichever chat
sent it, the same digest + attached report as the on-demand workflow
above. The last processed message is tracked in
`data/telegram_offset.json` so the same message never gets two replies.
This only needs `TELEGRAM_BOT_TOKEN` (not the chat ID secret, since it
replies to whoever messaged it) and no-ops if that secret isn't set.

## AI-written summaries (optional)

If you add an `ANTHROPIC_API_KEY` repository secret (**Settings → Secrets
and variables → Actions**), the script uses Claude to turn the raw list of
new pages into a short narrative summary (grouped by module, with likely
impact) instead of just a bullet list of links. Without the secret, it
still fully works — you just get the plain bullet-list version.

## Telegram delivery (optional)

Both workflows will post to Telegram automatically once you add two
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

Once both secrets exist, the next run of either workflow will deliver to
Telegram automatically — no code changes needed. Without them, both
workflows print "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set, skipping
Telegram send." and continue normally (GitHub issue/commit still happen).

## Repository layout

```
.github/workflows/daily-scm-update.yml       # daily cron + manual trigger
.github/workflows/build-latest-summary.yml   # on-demand full current-release summary
.github/workflows/telegram-on-demand.yml     # poll Telegram, reply to "hi" etc.
scripts/check_scm_updates.py                 # fetch, diff, summarize, report
scripts/build_latest_summary.py              # on-demand full current-release summary
scripts/telegram_on_demand.py                # poll + reply logic
scripts/send_telegram.py                     # Telegram Bot API delivery
scripts/module_scope.py                      # which SCM modules are tracked
scripts/requirements.txt                     # Python dependencies
data/state.json                              # last-known snapshot (auto-updated)
data/telegram_offset.json                    # last Telegram message processed (auto-updated)
updates/YYYY-MM-DD.md                        # one report per day with changes
docs/Latest_SCM_Update_Summary.md            # full current-release summary (on demand)
CHANGELOG.md                                 # running index of update days
```

## Running it locally

```bash
pip install -r scripts/requirements.txt
python scripts/check_scm_updates.py
```

This will fetch the live Oracle pages, compare against `data/state.json`,
and (if there's anything new) write a report under `updates/` — useful for
testing changes to the scraper before they run on schedule.

## Notes

- This project only reads Oracle's **public** readiness pages; it does not
  require or use an Oracle Support / My Oracle Support login.
- Not affiliated with or endorsed by Oracle. Always confirm feature details
  against the official Oracle Fusion Cloud Readiness pages before acting on
  them.
