# Oracle Fusion SCM Quarterly Update Tracker

Automatically checks Oracle's public **Cloud Applications Readiness** site
every day for new or changed "What's New" pages covering the Oracle Fusion
Cloud **Supply Chain & Manufacturing (SCM)** pillar, and reports a
summarized diff so you never have to manually re-check the site to catch
new features ahead of each quarterly release (e.g. 26A/26B/26C).

## How it works

1. A GitHub Actions workflow (`.github/workflows/daily-scm-update.yml`)
   runs every day at 06:00 UTC (and can be triggered manually via
   **Actions → Daily Oracle Fusion SCM Update Check → Run workflow**).
2. `scripts/check_scm_updates.py` fetches Oracle's public readiness pages:
   - https://docs.oracle.com/en/cloud/saas/readiness/scm.html (current release)
   - https://docs.oracle.com/en/cloud/saas/readiness/scm-all.html (archive of all releases)
3. It extracts every linked per-module "What's New" page (Procurement,
   Supply Planning, Product Lifecycle Management, Inventory, Manufacturing,
   Supply Chain Collaboration, etc.) and compares that list against the
   previous day's snapshot stored in `data/state.json`.
4. If any pages are new or changed:
   - A dated report is written to `updates/YYYY-MM-DD.md`.
   - `CHANGELOG.md` gets a new entry linking to that report.
   - A GitHub Issue is opened (labeled `oracle-scm-update`) containing the
     summary, so you get a notification without having to watch the repo.
   - `data/state.json` is updated and all of the above is committed back
     to the repository by the workflow.
5. If nothing changed, the workflow exits quietly — no commit, no issue.

## AI-written summaries (optional)

If you add an `ANTHROPIC_API_KEY` repository secret (**Settings → Secrets
and variables → Actions**), the script uses Claude to turn the raw list of
new pages into a short narrative summary (grouped by module, with likely
impact) instead of just a bullet list of links. Without the secret, it
still fully works — you just get the plain bullet-list version.

## Repository layout

```
.github/workflows/daily-scm-update.yml   # daily cron + manual trigger
scripts/check_scm_updates.py             # fetch, diff, summarize, report
scripts/requirements.txt                 # Python dependencies
data/state.json                          # last-known snapshot (auto-updated)
updates/YYYY-MM-DD.md                    # one report per day with changes
CHANGELOG.md                             # running index of update days
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
