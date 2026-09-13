#!/usr/bin/env python3
"""One-off: build a human-readable summary of the current-quarter SCM
readiness pages (the latest release per module) into a Markdown file.

Each module's "What's New" page is the first page of a multi-page
Oracle Help Center "book" (index -> revision history -> feature summary
-> individual feature topics). The feature summary page a few hops in
has a table (class "fsModule") listing every feature for the release,
which is what this pulls out — walking every individual feature topic
page per module would be far larger than a summary needs.

This is a manual/ad-hoc reporting tool, separate from the daily diff
checker (check_scm_updates.py). Run via workflow_dispatch on
build-latest-summary.yml.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state.json"
OUT_PATH = ROOT / "docs" / "Latest_SCM_Update_Summary.md"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; OracleFusionSCMUpdateBot/1.0; "
        "+https://github.com/) daily-readiness-checker"
    )
}
REQUEST_TIMEOUT = 30
MAX_HOPS = 6

MODULE_RE = re.compile(r"/(scm|logistics|common)/(\d\d[a-d])/([a-z]+?)(\d\d[a-d])/index\.html")


def fetch(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        return resp.text
    except requests.RequestException as exc:
        print(f"WARNING: failed to fetch {url}: {exc}", file=sys.stderr)
        return None


def latest_per_module(items: list[dict]) -> list[dict]:
    by_code: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for item in items:
        m = MODULE_RE.search(item["url"])
        if not m:
            continue
        _, release, code, _ = m.groups()
        by_code[code].append((release, item))
    latest = []
    for code, entries in by_code.items():
        entries.sort(key=lambda e: e[0])
        latest.append(entries[-1][1])
    latest.sort(key=lambda it: it["title"])
    return latest


def find_feature_table(start_url: str) -> tuple[BeautifulSoup, str] | tuple[None, None]:
    """Walk the book's "next" chain until the feature-summary table appears."""
    url = start_url
    for _ in range(MAX_HOPS):
        html = fetch(url)
        if not html:
            return None, None
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="fsModule")
        if table:
            return table, url
        nxt = soup.find("link", rel="next")
        href = nxt["href"] if nxt and nxt.get("href") else None
        if not href:
            return None, None
        url = urljoin(url, href)
    return None, None


def parse_feature_rows(table, page_url: str) -> list[dict]:
    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue
        module, feature_cell, tags_cell, impact, action = cells[:5]
        link = feature_cell.find("a")
        rows.append(
            {
                "module": module.get_text(strip=True),
                "feature": feature_cell.get_text(strip=True),
                "feature_url": urljoin(page_url, link["href"]) if link and link.get("href") else None,
                "tags": tags_cell.get_text(" ", strip=True),
                "impact": impact.get_text(strip=True),
                "action": action.get_text(strip=True),
            }
        )
    return rows


def main() -> int:
    state = json.loads(STATE_PATH.read_text())
    modules = latest_per_module(state["items"])

    if os.environ.get("DEBUG_ZERO_MODULES"):
        zero_titles = {
            "Global Trade Management What's New 26C",
            "Transportation Management What's New 26C",
            "Warehouse Management What's New 26C",
        }
        for item in modules:
            if item["title"] not in zero_titles:
                continue
            url = item["url"]
            for hop in range(MAX_HOPS + 2):
                html = fetch(url)
                if not html:
                    print(f"DEBUG {item['title']}: hop {hop} fetch failed for {url}", file=sys.stderr)
                    break
                soup = BeautifulSoup(html, "html.parser")
                table = soup.find("table", class_="fsModule")
                title = soup.find("title")
                nxt = soup.find("link", rel="next")
                href = nxt["href"] if nxt and nxt.get("href") else None
                print(
                    f"DEBUG {item['title']}: hop {hop} url={url} title={title.get_text(strip=True) if title else None!r} "
                    f"has_table={bool(table)} next={href!r}",
                    file=sys.stderr,
                )
                if table or not href:
                    break
                url = urljoin(url, href)
        return 0

    print(f"Building summary for {len(modules)} current-release modules")

    sections = [
        "# Oracle Fusion Cloud SCM — Latest Quarterly Update Summary",
        "",
        f"_Generated from the current readiness snapshot ({state.get('last_checked')})._",
        "",
    ]
    for item in modules:
        sections.append(f"## {item['title']}")
        sections.append("")
        sections.append(f"[Full documentation]({item['url']})")
        sections.append("")

        table, page_url = find_feature_table(item["url"])
        if not table:
            sections.append("_Could not locate the feature summary table for this module._")
            sections.append("")
            continue

        rows = parse_feature_rows(table, page_url)
        print(f"  {item['title']}: {len(rows)} feature(s)")
        if not rows:
            sections.append("_No features listed._")
            sections.append("")
            continue

        sections.append("| Area | Feature | Impact | Action to Enable |")
        sections.append("|---|---|---|---|")
        for row in rows:
            feature_text = f"[{row['feature']}]({row['feature_url']})" if row["feature_url"] else row["feature"]
            sections.append(f"| {row['module']} | {feature_text} | {row['impact']} | {row['action']} |")
        sections.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(sections))
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
