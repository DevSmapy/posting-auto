from __future__ import annotations

import os


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def approve_timeout_sec() -> int:
    for key in ("APPROVE_TIMEOUT_SEC", "DISCORD_APPROVE_TIMEOUT_SEC", "TELEGRAM_APPROVE_TIMEOUT_SEC"):
        raw = env(key)
        if raw:
            return int(raw)
    return 900
