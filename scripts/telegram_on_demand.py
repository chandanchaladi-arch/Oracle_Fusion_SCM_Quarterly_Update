#!/usr/bin/env python3
"""Reply with the requested category summary when someone messages the bot.

Send "hi" (or hello/hey/update/status//start//update) for all five
categories, or one of scm/fin/ppm/ai/redwood for just that category.

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
DOCS_DIR = ROOT / "docs"
CATEGORIES = ("SCM", "Finance", "PPM", "AI", "Redwood")

TRIGGER_ALL = {"hi", "hello", "hey", "update", "status", "/start", "/update"}
CATEGORY_TRIGGERS = {
    "scm": "SCM",
    "fin": "Finance",
    "finance": "Finance",
    "ppm": "PPM",
    "ai": "AI",
    "redwood": "Redwood",
}
API_BASE = "https://api.telegram.org/bot{token}/{method}"


def categories_for_text(text: str) -> set[str] | None:
    text = text.strip().lower()
    if text in TRIGGER_ALL:
        return set(CATEGORIES)
    if text in CATEGORY_TRIGGERS:
        return {CATEGORY_TRIGGERS[text]}
    return None


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
    triggered_chats: dict[int, set[str]] = {}
    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        message = update.get("message") or update.get("edited_message")
        if not message or "text" not in message:
            continue
        categories = categories_for_text(message["text"])
        if categories:
            chat_id = message["chat"]["id"]
            triggered_chats.setdefault(chat_id, set()).update(categories)

    save_offset(max_update_id)

    if not triggered_chats:
        print("No trigger words in the new messages, nothing to reply to.")
        return 0

    print(f"Rebuilding the summaries for {len(triggered_chats)} chat(s) that asked for an update...")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_latest_summary.py")], check=True
    )

    sys.path.insert(0, str(ROOT / "scripts"))
    import send_telegram as st

    for chat_id, categories in triggered_chats.items():
        for category in CATEGORIES:
            if category not in categories:
                continue
            summary_md = DOCS_DIR / f"Latest_Update_Summary_{category}.md"
            summary_txt = DOCS_DIR / f"Latest_Update_Summary_{category}_telegram.txt"
            text = summary_txt.read_text() if summary_txt.exists() else f"{category} summary unavailable right now."
            st.send_message(token, str(chat_id), text)
            if summary_md.exists():
                st.send_document(token, str(chat_id), str(summary_md), caption=summary_md.name)
    print(f"Replied to {len(triggered_chats)} chat(s), each with their requested categories.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
