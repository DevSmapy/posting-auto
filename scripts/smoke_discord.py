#!/usr/bin/env python3
"""Smoke: Discord bot token + channel (identity + optional ping)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

API = "https://discord.com/api/v10"


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def main() -> int:
    token = env("DISCORD_BOT_TOKEN")
    channel_id = env("DISCORD_CHANNEL_ID")
    if not token:
        print("FAIL: DISCORD_BOT_TOKEN empty — set in .env (Discord Developer Portal → Bot)")
        return 1
    headers = {"Authorization": f"Bot {token}"}
    r = requests.get(f"{API}/users/@me", headers=headers, timeout=20)
    r.raise_for_status()
    me = r.json()
    print(f"OK @me: {me.get('username')}#{me.get('discriminator')} id={me.get('id')}")
    if not channel_id:
        print("WARN: DISCORD_CHANNEL_ID empty — Approve will fall back unless set")
        return 0

    ch = requests.get(f"{API}/channels/{channel_id}", headers=headers, timeout=20)
    if ch.status_code == 404:
        print("FAIL: channel not found — check DISCORD_CHANNEL_ID / bot is in that server")
        return 1
    ch.raise_for_status()
    info = ch.json()
    ch_type = info.get("type")
    # 0=text, 5=announcement, 11/12=thread; 4=category (cannot send)
    print(f"OK channel: name={info.get('name')!r} type={ch_type}")
    if ch_type == 4:
        print(
            "FAIL: DISCORD_CHANNEL_ID is a category, not a text channel.\n"
            "  Discord 개발자 모드 ON → #일반 같은 텍스트 채널을 우클릭 → '채널 ID 복사'\n"
            "  (카테고리 이름이 아니라 #로 시작하는 채널이어야 합니다)"
        )
        return 1
    if ch_type not in {0, 5, 11, 12}:
        print(f"FAIL: channel type={ch_type} does not accept normal messages")
        return 1

    ping = requests.post(
        f"{API}/channels/{channel_id}/messages",
        headers={**headers, "Content-Type": "application/json"},
        json={"content": "[smoke] posting-auto Discord OK"},
        timeout=20,
    )
    if ping.status_code == 403:
        print(
            "FAIL: 403 Forbidden — invite bot to the server with Send Messages "
            "+ Add Reactions (+ Read Message History) on that channel"
        )
        return 1
    if not ping.ok:
        print(f"FAIL: {ping.status_code} {ping.text[:500]}")
        return 1
    print(f"OK message → channel_id={channel_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
