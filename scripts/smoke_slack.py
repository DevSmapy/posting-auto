#!/usr/bin/env python3
"""Smoke: Slack bot token + channel (auth.test + optional ping)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

API = "https://slack.com/api"


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def main() -> int:
    token = env("SLACK_BOT_TOKEN")
    channel_id = env("SLACK_CHANNEL_ID")
    if not token:
        print("FAIL: SLACK_BOT_TOKEN empty — set in .env (Slack app → OAuth Bot Token)")
        return 1
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    auth = requests.post(f"{API}/auth.test", headers=headers, json={}, timeout=20)
    auth.raise_for_status()
    data = auth.json()
    if not data.get("ok"):
        print(f"FAIL: auth.test — {data.get('error')}")
        return 1
    print(f"OK auth: user={data.get('user')} team={data.get('team')} bot_id={data.get('user_id')}")

    if not channel_id:
        print("WARN: SLACK_CHANNEL_ID empty — Approve will fail until set")
        return 0

    ping = requests.post(
        f"{API}/chat.postMessage",
        headers=headers,
        json={"channel": channel_id, "text": "[smoke] posting-auto Slack OK"},
        timeout=20,
    )
    ping.raise_for_status()
    body = ping.json()
    if not body.get("ok"):
        err = body.get("error")
        print(f"FAIL: chat.postMessage — {err}")
        if err == "not_in_channel":
            print("  Invite the bot to the channel (/invite @bot) and retry.")
        return 1
    print(f"OK message → channel_id={channel_id} ts={body.get('ts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
