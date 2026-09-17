#!/usr/bin/env python3
"""One-off: build human-readable summaries of the current-quarter
readiness pages, split into five separate reports: SCM, Finance, PPM,
AI, and Redwood.

Each module's "What's New" page is the first page of a multi-page
Oracle Help Center "book" (index -> revision history -> feature summary
-> individual feature topics). The feature summary page a few hops in
has a table listing every feature for the release, which is what this
pulls out — walking every individual feature topic page per module
would be far larger than a summary needs.

SCM/Finance/PPM are module-based categories. AI and Redwood are not
modules — they're tags Oracle puts on individual features from ANY
tracked module, so those two reports scan every module's rows looking
for that tag rather than being tied to specific modules. See
module_scope.py for the category/tag definitions.

This is a manual/ad-hoc reporting tool, separate from the daily diff
checker (check_scm_updates.py). Run via workflow_dispatch on
build-latest-summary.yml.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from module_scope import (
    category_for_module,
    finance_subarea_for,
    has_ai_tag,
    has_redwood_tag,
    is_tracked,
)

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state.json"
DOCS_DIR = ROOT / "docs"

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; OracleFusionSCMUpdateBot/1.0; "
        "+https://github.com/) daily-readiness-checker"
    )
}
REQUEST_TIMEOUT = 30
MAX_HOPS = 6

MODULE_RE = re.compile(r"/(scm|logistics|common|erp)/(\d\d[a-d])/([a-z]+?)(\d\d[a-d])/index\.html")


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
        if not is_tracked(item["title"]):
            continue
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
        # "fsModule" is an extra class on some books (common/SCM); logistics
        # books only carry "rfs_table" on the same table, so match on that.
        table = soup.find("table", class_="rfs_table")
        if table:
            return table, url
        nxt = soup.find("link", rel="next")
        href = nxt["href"] if nxt and nxt.get("href") else None
        if not href:
            return None, None
        url = urljoin(url, href)
    return None, None


COLUMN_ALIASES = {
    "module": "module",
    "feature": "feature",
    "tags": "tags",
    "impact to existing processes": "impact",
    "impact": "impact",
    "action to enable": "action",
    "action": "action",
}


def header_index_map(table) -> dict[str, int]:
    """Map logical column names to their position, since the table's exact
    column set varies between books (e.g. logistics tables omit "Tags")."""
    header_cells = table.find("thead").find_all("th")
    index_map = {}
    for i, th in enumerate(header_cells):
        key = COLUMN_ALIASES.get(th.get_text(strip=True).lower())
        if key:
            index_map[key] = i
    return index_map


def parse_feature_rows(table, page_url: str) -> list[dict]:
    index_map = header_index_map(table)
    if "module" not in index_map or "feature" not in index_map:
        return []

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) <= max(index_map.values()):
            continue
        feature_cell = cells[index_map["feature"]]
        link = feature_cell.find("a")
        rows.append(
            {
                "module": cells[index_map["module"]].get_text(strip=True),
                "feature": feature_cell.get_text(strip=True),
                "feature_url": urljoin(page_url, link["href"]) if link and link.get("href") else None,
                "tags": cells[index_map["tags"]].get_text(" ", strip=True) if "tags" in index_map else "",
                "impact": cells[index_map["impact"]].get_text(strip=True) if "impact" in index_map else "",
                "action": cells[index_map["action"]].get_text(strip=True) if "action" in index_map else "",
            }
        )
    return rows


def gather_module_data(modules: list[dict]) -> list[dict]:
    """Fetch each tracked module's feature table exactly once, so the five
    category reports below can all draw from the same crawl."""
    results = []
    for item in modules:
        category = category_for_module(item["title"])
        table, page_url = find_feature_table(item["url"])
        rows = parse_feature_rows(table, page_url) if table else []
        print(f"  {item['title']} [{category}]: {len(rows)} feature(s)")
        results.append({"item": item, "category": category, "rows": rows})
    return results


def feature_cell_md(row: dict) -> str:
    return f"[{row['feature']}]({row['feature_url']})" if row["feature_url"] else row["feature"]


def write_doc(name: str, title: str, generated_at: str, module_sections: list[tuple[str, str, list[list[str]]]]) -> Path:
    """module_sections: list of (heading, doc_link, table_rows) where each
    table_rows entry is already-formatted markdown table cells."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DOCS_DIR / f"Latest_Update_Summary_{name}.md"
    parts = [f"# {title}", "", f"_Generated from the current readiness snapshot ({generated_at})._", ""]
    for heading, doc_link, header_and_rows in module_sections:
        parts.append(f"## {heading}")
        parts.append("")
        if doc_link:
            parts.append(f"[Full documentation]({doc_link})")
            parts.append("")
        header, rows = header_and_rows[0], header_and_rows[1:]
        if not rows:
            parts.append("_No matching features found._")
            parts.append("")
            continue
        parts.append("| " + " | ".join(header) + " |")
        parts.append("|" + "|".join("---" for _ in header) + "|")
        for row in rows:
            parts.append("| " + " | ".join(row) + " |")
        parts.append("")
    out_path.write_text("\n".join(parts))
    print(f"Wrote {out_path}")
    return out_path


def write_telegram_digest(name: str, title: str, generated_at: str, counts: list[tuple[str, int]]) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DOCS_DIR / f"Latest_Update_Summary_{name}_telegram.txt"
    total = sum(c for _, c in counts)
    lines = [title, f"({generated_at[:10]})", ""]
    for label, count in counts:
        lines.append(f"• {label}: {count} feature(s)")
    lines.append("")
    lines.append(f"Total: {total} feature(s) across {len(counts)} area(s).")
    lines.append("Full details attached." if total else "Nothing to report right now.")
    out_path.write_text("\n".join(lines))
    print(f"Wrote {out_path}")
    return out_path


def build_module_category_report(name: str, title: str, generated_at: str, entries: list[dict]) -> None:
    """SCM/PPM: full module list, no sub-filtering."""
    sections = []
    counts = []
    for entry in entries:
        header = ["Area", "Feature", "Impact", "Action to Enable"]
        rows = [[r["module"], feature_cell_md(r), r["impact"], r["action"]] for r in entry["rows"]]
        sections.append((entry["item"]["title"], entry["item"]["url"], [header] + rows))
        counts.append((entry["item"]["title"].split(" What's New")[0], len(entry["rows"])))
    write_doc(name, title, generated_at, sections)
    write_telegram_digest(name, title, generated_at, counts)


def build_finance_report(generated_at: str, entries: list[dict]) -> None:
    sections = []
    subarea_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        header = ["Oracle Area", "Sub-area", "Feature", "Impact", "Action to Enable"]
        rows = []
        for r in entry["rows"]:
            subarea = finance_subarea_for(r["module"])
            if not subarea:
                continue
            subarea_counts[subarea] += 1
            rows.append([r["module"], subarea, feature_cell_md(r), r["impact"], r["action"]])
        sections.append((entry["item"]["title"], entry["item"]["url"], [header] + rows))
    write_doc("Finance", "Oracle Fusion Cloud Finance — Latest Update Summary", generated_at, sections)
    counts = [(name, subarea_counts.get(name, 0)) for name in
              ("General Ledger", "Accounts Payable", "Accounts Receivable", "Fixed Assets", "Cash Management")]
    write_telegram_digest("Finance", "Oracle Fusion Cloud Finance — Latest Update Summary", generated_at, counts)


def build_tag_report(name: str, title: str, generated_at: str, tag_check, all_entries: list[dict]) -> None:
    """AI/Redwood: scan every tracked module's rows for a matching tag."""
    sections = []
    counts = []
    for entry in all_entries:
        matching = [r for r in entry["rows"] if tag_check(r["tags"])]
        if not matching:
            continue
        header = ["Area", "Feature", "Tags", "Impact", "Action to Enable"]
        rows = [[r["module"], feature_cell_md(r), r["tags"], r["impact"], r["action"]] for r in matching]
        sections.append((entry["item"]["title"], entry["item"]["url"], [header] + rows))
        counts.append((entry["item"]["title"].split(" What's New")[0], len(matching)))
    write_doc(name, title, generated_at, sections)
    write_telegram_digest(name, title, generated_at, counts)


def main() -> int:
    state = json.loads(STATE_PATH.read_text())
    modules = latest_per_module(state["items"])
    print(f"Crawling {len(modules)} current-release modules across SCM/Finance/PPM")

    all_data = gather_module_data(modules)
    generated_at = state.get("last_checked") or ""

    scm_entries = [d for d in all_data if d["category"] == "SCM"]
    finance_entries = [d for d in all_data if d["category"] == "Finance"]
    ppm_entries = [d for d in all_data if d["category"] == "PPM"]

    build_module_category_report("SCM", "Oracle Fusion Cloud SCM — Latest Update Summary", generated_at, scm_entries)
    build_finance_report(generated_at, finance_entries)
    build_module_category_report("PPM", "Oracle Fusion Cloud PPM — Latest Update Summary", generated_at, ppm_entries)
    build_tag_report("AI", "Oracle Fusion Cloud AI-Tagged Features — Latest Update Summary", generated_at, has_ai_tag, all_data)
    build_tag_report("Redwood", "Oracle Fusion Cloud Redwood-Tagged Features — Latest Update Summary", generated_at, has_redwood_tag, all_data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
