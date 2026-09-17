#!/usr/bin/env python3
"""Daily check for new Oracle Fusion Cloud readiness / What's New pages.

Fetches Oracle's public Cloud Applications Readiness pages for the SCM
and ERP pillars, diffs the list of module "What's New" pages against the
last known snapshot (data/state.json), and — when new pages have
appeared — writes a dated Markdown report per category (SCM/Finance/PPM),
opens a labeled GitHub issue per category, and sends each to Telegram if
configured.

Only tracks the modules in module_scope.py — everything else Oracle
publishes under these pillars is ignored. AI and Redwood are not module
categories (they're feature-level tags), so they aren't covered by this
daily module-level diff; see build_latest_summary.py for those.

If ANTHROPIC_API_KEY is set, new items are additionally summarized into a
short narrative using Claude; otherwise a plain bullet list is produced.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from module_scope import category_for_module, is_tracked

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state.json"
UPDATES_DIR = ROOT / "updates"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"

SOURCES = [
    {
        "name": "SCM Readiness – Current Release",
        "url": "https://docs.oracle.com/en/cloud/saas/readiness/scm.html",
    },
    {
        "name": "SCM Readiness – All Releases (archive)",
        "url": "https://docs.oracle.com/en/cloud/saas/readiness/scm-all.html",
    },
    {
        "name": "ERP Readiness – Current Release",
        "url": "https://docs.oracle.com/en/cloud/saas/readiness/erp.html",
    },
    {
        "name": "ERP Readiness – All Releases (archive)",
        "url": "https://docs.oracle.com/en/cloud/saas/readiness/erp-all.html",
    },
]

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; OracleFusionSCMUpdateBot/1.0; "
        "+https://github.com/) daily-readiness-checker"
    )
}
REQUEST_TIMEOUT = 30

CATEGORY_LABELS = {
    "SCM": "oracle-scm-update",
    "Finance": "oracle-finance-update",
    "PPM": "oracle-ppm-update",
}


def fetch(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # Oracle's server doesn't send a charset in the Content-Type header,
        # so requests falls back to ISO-8859-1 and mangles UTF-8 punctuation
        # (e.g. "Here's" -> "Hereâ€™s"). Fall back to the sniffed encoding.
        if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        if os.environ.get("DEBUG_SCRAPE"):
            print(f"DEBUG {url}: status={resp.status_code} length={len(resp.text)}", file=sys.stderr)
        return resp.text
    except requests.RequestException as exc:
        print(f"WARNING: failed to fetch {url}: {exc}", file=sys.stderr)
        return None


def extract_module_links(html: str, base_url: str, source_name: str) -> dict[str, dict]:
    """Extract readiness entries from Oracle's help-center "book" cards.

    Each entry on the page is a `<div class="book">` containing a `.h4`
    title (e.g. "Supply Planning What's New 26C") and one or more format
    links (HTML/PDF) whose visible text is just the format name.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, dict] = {}
    for book in soup.select("div.book"):
        title_el = book.select_one(".h4")
        title = title_el.get_text(strip=True) if title_el else None
        if not title or not is_tracked(title):
            continue

        chosen_href = None
        for a in book.find_all("a", href=True):
            if a.get_text(strip=True).upper() == "HTML":
                chosen_href = a["href"]
                break
        if not chosen_href:
            first_link = book.find("a", href=True)
            chosen_href = first_link["href"] if first_link else None
        if not chosen_href:
            continue

        absolute_url = urljoin(base_url, chosen_href)
        items[absolute_url] = {
            "id": absolute_url,
            "title": title,
            "url": absolute_url,
            "source": source_name,
            "category": category_for_module(title),
        }
    return items


def fetch_description(url: str) -> str:
    html = fetch(url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 40:
            return text[:400]
    return ""


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"last_checked": None, "items": []}


def save_state(items: dict[str, dict], checked_at: str) -> None:
    payload = {"last_checked": checked_at, "items": sorted(items.values(), key=lambda i: i["id"])}
    STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def summarize_with_claude(category: str, new_items: list[dict]) -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        print("WARNING: anthropic package not installed, skipping AI summary", file=sys.stderr)
        return None

    bullet_source = "\n".join(
        f"- {item['title']} ({item['url']})"
        + (f"\n  Excerpt: {item['description']}" if item.get("description") else "")
        for item in new_items
    )
    prompt = (
        f"You are summarizing newly published Oracle Fusion Cloud {category} "
        "readiness / \"What's New\" pages for a functional and technical audience "
        "that supports an Oracle Fusion implementation. Group related items, call "
        "out the module/release each item belongs to, and briefly note likely "
        "impact or why it matters. Be concise and use Markdown bullet points. "
        "Do not invent details beyond what's given.\n\n"
        f"New/changed readiness pages found today:\n{bullet_source}"
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()
    except Exception as exc:  # noqa: BLE001 - best-effort enhancement, never fatal
        print(f"WARNING: Claude summarization failed: {exc}", file=sys.stderr)
        return None


def plain_summary(new_items: list[dict]) -> str:
    lines = []
    for item in new_items:
        line = f"- [{item['title']}]({item['url']})  \n  _Source: {item['source']}_"
        if item.get("description"):
            line += f"  \n  {item['description']}"
        lines.append(line)
    return "\n".join(lines)


def write_report(date_str: str, category: str, new_items: list[dict], narrative: str | None) -> Path:
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    report_path = UPDATES_DIR / f"{date_str}-{category.lower()}.md"
    parts = [
        f"# Oracle Fusion Cloud {category} — Readiness Updates for {date_str}",
        "",
        f"Found **{len(new_items)}** new/changed readiness page(s) since the previous check.",
        "",
    ]
    if narrative:
        parts += ["## Summary", "", narrative, ""]
    parts += ["## New/Changed Pages", "", plain_summary(new_items), ""]
    report_path.write_text("\n".join(parts))
    return report_path


CHANGELOG_TITLE = "# Changelog — Oracle Fusion Cloud Readiness Updates\n"


def update_changelog(date_str: str, category: str, count: int, report_path: Path) -> None:
    relative = report_path.relative_to(ROOT)
    entry = (
        f"- **{date_str}** [{category}]: {count} new/changed readiness page(s) "
        f"— see [{relative}]({relative})\n"
    )

    existing_entries: list[str] = []
    if CHANGELOG_PATH.exists():
        marker = f"**{date_str}** [{category}]"
        existing_entries = [
            line
            for line in CHANGELOG_PATH.read_text().splitlines(keepends=True)
            if line.startswith("- **") and marker not in line
        ]

    CHANGELOG_PATH.write_text(CHANGELOG_TITLE + "\n" + entry + "".join(existing_entries))


def ensure_label(label: str) -> None:
    if not os.environ.get("GH_TOKEN"):
        return
    subprocess.run(
        ["gh", "label", "create", label, "--color", "BFD4F2", "--description", "Automated Oracle readiness update", "--force"],
        check=False,
    )


def open_issue(category: str, date_str: str, count: int, report_path: Path) -> None:
    if not os.environ.get("GH_TOKEN"):
        return
    label = CATEGORY_LABELS.get(category, "oracle-readiness-update")
    ensure_label(label)
    subprocess.run(
        [
            "gh",
            "issue",
            "create",
            "--title",
            f"Oracle Fusion {category} updates - {date_str} ({count} new)",
            "--body-file",
            str(report_path),
            "--label",
            label,
        ],
        check=False,
    )


def send_to_telegram(report_path: Path) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    sys.path.insert(0, str(ROOT / "scripts"))
    import send_telegram as st

    text = report_path.read_text().strip()
    st.send_message(token, chat_id, text)


def set_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    with open(output_file, "a") as f:
        f.write(f"{name}={value}\n")


def main() -> int:
    checked_at = datetime.now(timezone.utc).isoformat()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    current_items: dict[str, dict] = {}
    fetched_any = False
    for source in SOURCES:
        html = fetch(source["url"])
        if html is None:
            continue
        fetched_any = True
        current_items.update(extract_module_links(html, source["url"], source["name"]))

    if not fetched_any:
        print("ERROR: could not reach any Oracle readiness source", file=sys.stderr)
        return 1

    previous_state = load_state()
    is_first_run = previous_state.get("last_checked") is None and not previous_state.get("items")
    if is_first_run:
        print(
            f"First run: baselining {len(current_items)} known readiness page(s) "
            "without generating a report (nothing to compare against yet)."
        )
        save_state(current_items, checked_at)
        set_output("changes_found", "false")
        return 0

    previous_ids = {item["id"] for item in previous_state.get("items", [])}
    previous_categories = {
        cat for item in previous_state.get("items", []) if (cat := category_for_module(item["title"]))
    }

    new_ids = []
    baselined_categories = set()
    for item_id, item in current_items.items():
        if item_id in previous_ids:
            continue
        category = item["category"]
        if category and category not in previous_categories:
            # This whole category is new to state.json (e.g. scope was just
            # expanded to include it) -- baseline its current backlog
            # silently rather than reporting years of history as "new."
            baselined_categories.add(category)
            continue
        new_ids.append(item_id)

    if baselined_categories:
        print(
            f"Silently baselining newly-tracked categor{'y' if len(baselined_categories) == 1 else 'ies'} "
            f"({', '.join(sorted(baselined_categories))}) -- their existing pages won't be reported as new."
        )

    if not new_ids:
        print(f"No new readiness pages found ({len(current_items)} tracked total).")
        save_state(current_items, checked_at)
        set_output("changes_found", "false")
        return 0

    new_items = [current_items[item_id] for item_id in new_ids]
    print(f"Found {len(new_items)} new readiness page(s):")
    by_category: dict[str, list[dict]] = defaultdict(list)
    for item in new_items:
        print(f"  - [{item['category']}] {item['title']} -> {item['url']}")
        item["description"] = fetch_description(item["url"])
        by_category[item["category"]].append(item)

    categories_with_changes = []
    for category, items in by_category.items():
        narrative = summarize_with_claude(category, items)
        report_path = write_report(date_str, category, items, narrative)
        update_changelog(date_str, category, len(items), report_path)
        open_issue(category, date_str, len(items), report_path)
        send_to_telegram(report_path)
        categories_with_changes.append(category)

    save_state(current_items, checked_at)

    set_output("changes_found", "true")
    set_output("categories", ",".join(sorted(categories_with_changes)))
    set_output("new_item_count", str(len(new_items)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
