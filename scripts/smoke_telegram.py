#!/usr/bin/env python3
"""Smoke: Telegram bot token + chat id (getMe + optional ping)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def main() -> int:
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token:
        print("FAIL: TELEGRAM_BOT_TOKEN empty — set in .env (BotFather)")
        return 1
    r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        print(f"FAIL: getMe {data}")
        return 1
    bot = data["result"]
    print(f"OK getMe: @{bot.get('username')} id={bot.get('id')}")
    if not chat_id:
        print("WARN: TELEGRAM_CHAT_ID empty — draft Approve will use CLI fallback")
        return 0
    ping = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": "[smoke] posting-auto Telegram OK"},
        timeout=20,
    )
    ping.raise_for_status()
    if not ping.json().get("ok"):
        print(f"FAIL: sendMessage {ping.json()}")
        return 1
    print(f"OK sendMessage → chat_id={chat_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
