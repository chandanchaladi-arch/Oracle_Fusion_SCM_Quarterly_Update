#!/usr/bin/env python3
"""Reply with the current SCM summary when someone messages the bot.

There's no always-on server here to receive a real Telegram webhook, so
this polls Telegram's getUpdates on a short interval instead (driven by
telegram-on-demand.yml, scheduled every 5 minutes -- GitHub Actions'
practical minimum). That means a reply can take a few minutes to arrive,
not be instant like a live bot.

The last processed update_id is kept in data/telegram_offset.json so the
same incoming message never gets two replies.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OFFSET_PATH = ROOT / "data" / "telegram_offset.json"
SUMMARY_MD = ROOT / "docs" / "Latest_SCM_Update_Summary.md"
SUMMARY_TXT = ROOT / "docs" / "Latest_SCM_Update_Summary_telegram.txt"

TRIGGER_WORDS = {"hi", "hello", "hey", "update", "status", "/start", "/update"}
API_BASE = "https://api.telegram.org/bot{token}/{method}"


def load_offset() -> int:
    if OFFSET_PATH.exists():
        return json.loads(OFFSET_PATH.read_text()).get("last_update_id", 0)
    return 0


def save_offset(update_id: int) -> None:
    OFFSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_PATH.write_text(json.dumps({"last_update_id": update_id}) + "\n")


def get_updates(token: str, offset: int) -> list[dict]:
    resp = requests.get(
        API_BASE.format(token=token, method="getUpdates"),
        params={"offset": offset + 1, "timeout": 0},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN not set, skipping.")
        return 0

    offset = load_offset()
    if not OFFSET_PATH.exists():
        # Make sure the file exists after every run so the workflow's
        # `git add` on a fixed path list never fails with "did not match
        # any files" on a repo that has never had this run before.
        save_offset(offset)
    updates = get_updates(token, offset)
    if not updates:
        print("No new Telegram messages.")
        return 0

    max_update_id = offset
    triggered_chats: set[int] = set()
    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        message = update.get("message") or update.get("edited_message")
        if not message or "text" not in message:
            continue
        text = message["text"].strip().lower()
        if text in TRIGGER_WORDS:
            triggered_chats.add(message["chat"]["id"])

    save_offset(max_update_id)

    if not triggered_chats:
        print("No trigger words in the new messages, nothing to reply to.")
        return 0

    print(f"Rebuilding the summary for {len(triggered_chats)} chat(s) that asked for an update...")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_latest_summary.py")], check=True
    )

    sys.path.insert(0, str(ROOT / "scripts"))
    import send_telegram as st

    text = SUMMARY_TXT.read_text() if SUMMARY_TXT.exists() else "Summary unavailable right now."
    for chat_id in triggered_chats:
        st.send_message(token, str(chat_id), text)
        if SUMMARY_MD.exists():
            st.send_document(token, str(chat_id), str(SUMMARY_MD), caption=SUMMARY_MD.name)
    print(f"Replied to {len(triggered_chats)} chat(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
