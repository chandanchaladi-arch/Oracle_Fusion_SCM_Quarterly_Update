#!/usr/bin/env python3
"""One-off debug: list every distinct 'Area' value in the Financials and
Self Service Financials feature-summary tables, plus check tag chips for
AI/Redwood, to verify real Oracle naming before building the Finance
sub-area filter and AI/Redwood tag filter.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
import build_latest_summary as bls  # noqa: E402


def inspect(url: str, label: str) -> None:
    print(f"\n=== {label}: {url} ===", file=sys.stderr)
    table, page_url = bls.find_feature_table(url)
    if not table:
        print("  no feature table found", file=sys.stderr)
        return
    rows = bls.parse_feature_rows(table, page_url)
    areas = sorted(set(r["module"] for r in rows))
    print(f"  {len(rows)} feature(s), distinct Area values:", file=sys.stderr)
    for a in areas:
        print("   -", a, file=sys.stderr)

    # tag chip classes actually present on this table (raw HTML inspection)
    chip_classes = set()
    for span in table.find_all("span", class_=True):
        for c in span["class"]:
            if "chip" in c:
                chip_classes.add(c)
    print("  tag-chip classes seen:", sorted(chip_classes), file=sys.stderr)

    # sample a couple of rows with any chip, printing area + feature + tag text
    tbody = table.find("tbody")
    for tr in tbody.find_all("tr")[:60]:
        chip_spans = tr.find_all("span", class_=lambda c: c and "chip" in c)
        if chip_spans:
            tds = tr.find_all("td")
            area = tds[0].get_text(strip=True) if tds else "?"
            feat = tds[1].get_text(strip=True) if len(tds) > 1 else "?"
            tags = [c.get_text(strip=True) for c in chip_spans]
            print(f"   TAGGED: [{area}] {feat} -> {tags}", file=sys.stderr)


def main() -> None:
    inspect("https://docs.oracle.com/en/cloud/saas/readiness/erp/26d/fins26d/index.html", "Financials")
    inspect(
        "https://docs.oracle.com/en/cloud/saas/readiness/erp/26d/ssfin26d/index.html",
        "Self Service Financials",
    )


if __name__ == "__main__":
    main()
