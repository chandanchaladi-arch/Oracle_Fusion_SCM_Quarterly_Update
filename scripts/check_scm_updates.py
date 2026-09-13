#!/usr/bin/env python3
"""Daily check for new Oracle Fusion Cloud SCM readiness / What's New pages.

Fetches Oracle's public Cloud Applications Readiness pages for the Supply
Chain & Manufacturing (SCM) pillar, diffs the list of module "What's New"
pages against the last known snapshot (data/state.json), and — when new
pages have appeared — writes a dated Markdown report to updates/ and an
entry to CHANGELOG.md.

If ANTHROPIC_API_KEY is set, new items are additionally summarized into a
short narrative using Claude; otherwise a plain bullet list is produced.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

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
]

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; OracleFusionSCMUpdateBot/1.0; "
        "+https://github.com/) daily-readiness-checker"
    )
}
REQUEST_TIMEOUT = 30


def fetch(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
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
        if not title:
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


def summarize_with_claude(new_items: list[dict]) -> str | None:
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
        "You are summarizing newly published Oracle Fusion Cloud SCM (Supply "
        "Chain & Manufacturing) readiness / \"What's New\" pages for a functional "
        "and technical audience that supports an Oracle Fusion SCM implementation. "
        "Group related items, call out the module/release each item belongs to, "
        "and briefly note likely impact or why it matters. Be concise and use "
        "Markdown bullet points. Do not invent details beyond what's given.\n\n"
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


def write_report(date_str: str, new_items: list[dict], narrative: str | None) -> Path:
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    report_path = UPDATES_DIR / f"{date_str}.md"
    parts = [
        f"# Oracle Fusion Cloud SCM – Readiness Updates for {date_str}",
        "",
        f"Found **{len(new_items)}** new/changed readiness page(s) since the previous check.",
        "",
    ]
    if narrative:
        parts += ["## Summary", "", narrative, ""]
    parts += ["## New/Changed Pages", "", plain_summary(new_items), ""]
    report_path.write_text("\n".join(parts))
    return report_path


CHANGELOG_TITLE = "# Changelog — Oracle Fusion Cloud SCM Readiness Updates\n"


def update_changelog(date_str: str, count: int, report_path: Path) -> None:
    relative = report_path.relative_to(ROOT)
    entry = f"- **{date_str}**: {count} new/changed SCM readiness page(s) — see [{relative}]({relative})\n"

    existing_entries: list[str] = []
    if CHANGELOG_PATH.exists():
        existing_entries = [
            line for line in CHANGELOG_PATH.read_text().splitlines(keepends=True)
            if line.startswith("- **") and not line.startswith(f"- **{date_str}**")
        ]

    CHANGELOG_PATH.write_text(CHANGELOG_TITLE + "\n" + entry + "".join(existing_entries))


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
            f"First run: baselining {len(current_items)} known SCM readiness page(s) "
            "without generating a report (nothing to compare against yet)."
        )
        save_state(current_items, checked_at)
        set_output("changes_found", "false")
        return 0

    previous_ids = {item["id"] for item in previous_state.get("items", [])}
    new_ids = [item_id for item_id in current_items if item_id not in previous_ids]

    if not new_ids:
        print(f"No new SCM readiness pages found ({len(current_items)} tracked total).")
        save_state(current_items, checked_at)
        set_output("changes_found", "false")
        return 0

    new_items = [current_items[item_id] for item_id in new_ids]
    print(f"Found {len(new_items)} new SCM readiness page(s):")
    for item in new_items:
        print(f"  - {item['title']} -> {item['url']}")
        item["description"] = fetch_description(item["url"])

    narrative = summarize_with_claude(new_items)
    report_path = write_report(date_str, new_items, narrative)
    update_changelog(date_str, len(new_items), report_path)
    save_state(current_items, checked_at)

    set_output("changes_found", "true")
    set_output("summary_file", str(report_path.relative_to(ROOT)))
    set_output("new_item_count", str(len(new_items)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
