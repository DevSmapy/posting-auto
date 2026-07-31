from __future__ import annotations

import os


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def approve_timeout_sec() -> int:
    for key in ("APPROVE_TIMEOUT_SEC", "DISCORD_APPROVE_TIMEOUT_SEC", "TELEGRAM_APPROVE_TIMEOUT_SEC"):
        raw = env(key)
        if raw:
            return int(raw)
    return 3600


def approve_reminder_sec() -> int:
    """Seconds before timeout to send a one-shot reminder (0 disables)."""
    raw = env("APPROVE_REMINDER_SEC", "600")
    if not raw:
        return 600
    return max(0, int(raw))
