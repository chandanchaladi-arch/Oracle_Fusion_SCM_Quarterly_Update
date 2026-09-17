#!/usr/bin/env python3
"""One-off debug: inspect Oracle readiness pages for ERP (Finance/PPM),
and check whether AI/Redwood are dedicated pages or cross-cutting tags.
Prints findings to stderr. Not part of the regular tooling.
"""
from __future__ import annotations

import sys

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; OracleFusionSCMUpdateBot/1.0; "
        "+https://github.com/) daily-readiness-checker"
    )
}


def fetch(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp.text


def main():
    print("=== erp.html: module 'book' titles ===", file=sys.stderr)
    html = fetch("https://docs.oracle.com/en/cloud/saas/readiness/erp.html")
    soup = BeautifulSoup(html, "html.parser")
    titles = set()
    for book in soup.select("div.book"):
        title_el = book.select_one(".h4")
        if title_el:
            titles.add(title_el.get_text(strip=True))
    for t in sorted(titles):
        print(" -", t, file=sys.stderr)

    print("\n=== nav links containing 'redwood' or 'ai' (case-insensitive) ===", file=sys.stderr)
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if "redwood" in href.lower() or "redwood" in text.lower():
            print(" REDWOOD:", text, "->", href, file=sys.stderr)

    print("\n=== Adopt Redwood page structure (redwood-adoption/index.html) ===", file=sys.stderr)
    try:
        rw_html = fetch("https://docs.oracle.com/en/cloud/saas/readiness/redwood-adoption/index.html")
        rw_soup = BeautifulSoup(rw_html, "html.parser")
        rw_title = rw_soup.find("title")
        print("title:", rw_title.get_text(strip=True) if rw_title else None, file=sys.stderr)
        rw_books = rw_soup.select("div.book")
        print("book count:", len(rw_books), file=sys.stderr)
        for book in rw_books[:10]:
            title_el = book.select_one(".h4")
            print(" -", title_el.get_text(strip=True) if title_el else None, file=sys.stderr)
        print(rw_soup.prettify()[:3000], file=sys.stderr)
    except Exception as exc:
        print("Adopt Redwood page fetch failed:", exc, file=sys.stderr)

    print("\n=== all module links on erp.html (href -> title) ===", file=sys.stderr)
    for book in soup.select("div.book"):
        title_el = book.select_one(".h4")
        link = book.find("a", href=True)
        if title_el and link:
            print(" -", title_el.get_text(strip=True), "->", link["href"], file=sys.stderr)


if __name__ == "__main__":
    main()
