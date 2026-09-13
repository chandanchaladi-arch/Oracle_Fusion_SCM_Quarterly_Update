#!/usr/bin/env python3
"""Send a summary to Telegram via the Bot API.

Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as environment variables
(set as GitHub repo secrets). If either is missing, this exits quietly
(0) so it never breaks a workflow for repos that haven't set up Telegram.

Usage:
    python scripts/send_telegram.py path/to/report.md
    python scripts/send_telegram.py path/to/report.md --document path/to/attachment.md
"""
from __future__ import annotations

import os
import sys

import requests

TELEGRAM_MESSAGE_LIMIT = 4096
API_BASE = "https://api.telegram.org/bot{token}/{method}"


def send_message(token: str, chat_id: str, text: str) -> None:
    for start in range(0, len(text), TELEGRAM_MESSAGE_LIMIT):
        chunk = text[start : start + TELEGRAM_MESSAGE_LIMIT]
        resp = requests.post(
            API_BASE.format(token=token, method="sendMessage"),
            data={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
            timeout=30,
        )
        if not resp.ok:
            print(f"WARNING: Telegram sendMessage failed: {resp.status_code} {resp.text}", file=sys.stderr)


def send_document(token: str, chat_id: str, file_path: str, caption: str = "") -> None:
    with open(file_path, "rb") as f:
        resp = requests.post(
            API_BASE.format(token=token, method="sendDocument"),
            data={"chat_id": chat_id, "caption": caption[:1024]},
            files={"document": f},
            timeout=60,
        )
    if not resp.ok:
        print(f"WARNING: Telegram sendDocument failed: {resp.status_code} {resp.text}", file=sys.stderr)


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set, skipping Telegram send.")
        return 0

    if len(sys.argv) < 2:
        print("usage: send_telegram.py <text_file> [--document <file_to_attach>]", file=sys.stderr)
        return 1

    text_path = sys.argv[1]
    document_path = None
    if "--document" in sys.argv:
        document_path = sys.argv[sys.argv.index("--document") + 1]

    text = open(text_path, encoding="utf-8").read().strip()
    if text:
        send_message(token, chat_id, text)
    if document_path:
        send_document(token, chat_id, document_path, caption=os.path.basename(document_path))

    print("Sent to Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
