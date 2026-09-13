#!/usr/bin/env python3
"""One-off: build a human-readable summary of the current-quarter SCM
readiness pages (the latest release per module) into a Markdown file.

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


def extract_page_summary(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find(id="main") or soup.find("main") or soup.body

    intro = ""
    for p in main.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 60:
            intro = text
            break

    features = []
    for heading in main.find_all(["h2", "h3"]):
        text = heading.get_text(strip=True)
        if text and text.lower() not in {"summary of features", "give us feedback"}:
            features.append(text)

    return {"intro": intro, "features": features}


def main() -> int:
    if os.environ.get("DEBUG_SCRAPE"):
        # print raw structure for the first module page AND its "next" page
        state = json.loads(STATE_PATH.read_text())
        sample = latest_per_module(state["items"])[0]
        html = fetch(sample["url"])
        if html:
            soup = BeautifulSoup(html, "html.parser")
            print(f"DEBUG sample url: {sample['url']}", file=sys.stderr)
            next_link = soup.find("link", rel="next")
            next_href = next_link["href"] if next_link and next_link.get("href") else None
            print(f"DEBUG next href: {next_href!r}", file=sys.stderr)
            url = sample["url"]
            href = next_href
            for hop in range(4):
                if not href:
                    break
                url = requests.compat.urljoin(url, href)
                html = fetch(url)
                if not html:
                    break
                soup = BeautifulSoup(html, "html.parser")
                title = soup.find("title")
                h1 = soup.find(["h1", "h2"])
                print(
                    f"DEBUG hop {hop}: {url} title={title.get_text(strip=True) if title else None!r} "
                    f"heading={h1.get_text(strip=True) if h1 else None!r}",
                    file=sys.stderr,
                )
                if hop == 2:
                    print(soup.prettify()[:8000], file=sys.stderr)
                nxt = soup.find("link", rel="next")
                href = nxt["href"] if nxt and nxt.get("href") else None
        return 0

    state = json.loads(STATE_PATH.read_text())
    modules = latest_per_module(state["items"])
    print(f"Building summary for {len(modules)} current-release modules")

    sections = [
        "# Oracle Fusion Cloud SCM — Latest Quarterly Update Summary",
        "",
        f"_Generated from the current readiness snapshot ({state.get('last_checked')})._",
        "",
    ]
    for item in modules:
        html = fetch(item["url"])
        sections.append(f"## {item['title']}")
        sections.append("")
        sections.append(f"[{item['url']}]({item['url']})")
        sections.append("")
        if html:
            info = extract_page_summary(html)
            if info["intro"]:
                sections.append(info["intro"])
                sections.append("")
            if info["features"]:
                sections.append("**New/changed features:**")
                sections.append("")
                for feat in info["features"]:
                    sections.append(f"- {feat}")
                sections.append("")
        else:
            sections.append("_Could not fetch page content._")
            sections.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(sections))
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
