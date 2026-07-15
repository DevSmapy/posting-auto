"""Resolve NOTIFY_CHANNEL → Notifier."""

from __future__ import annotations

from .auto import AutoNotifier
from .cli import CliNotifier
from .discord import DiscordNotifier
from .envutil import env
from .telegram import TelegramNotifier


def resolve_channel() -> str:
    """discord | telegram | cli | auto

    Priority when NOTIFY_CHANNEL unset:
      APPROVE_MODE / TELEGRAM_APPROVE_MODE auto|cli
      else discord if configured
      else telegram if configured
      else cli
    """
    explicit = env("NOTIFY_CHANNEL").lower()
    if explicit in {"discord", "telegram", "cli", "auto"}:
        return explicit

    # Back-compat: TELEGRAM_APPROVE_MODE / APPROVE_MODE
    for key in ("APPROVE_MODE", "TELEGRAM_APPROVE_MODE"):
        mode = env(key).lower()
        if mode in {"auto", "cli"}:
            return mode
        if mode == "telegram":
            return "telegram"
        if mode == "discord":
            return "discord"

    if env("DISCORD_BOT_TOKEN") and env("DISCORD_CHANNEL_ID"):
        return "discord"
    if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        return "telegram"
    return "cli"


def get_notifier():
    channel = resolve_channel()
    if channel == "auto":
        return AutoNotifier()
    if channel == "cli":
        return CliNotifier()
    if channel == "discord":
        return DiscordNotifier()
    if channel == "telegram":
        return TelegramNotifier()
    raise RuntimeError(f"Unknown NOTIFY_CHANNEL={channel}")
