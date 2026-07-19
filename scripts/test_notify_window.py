#!/usr/bin/env python3
"""Unit checks: news window + NOTIFY_CHANNEL resolve (no network)."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["NEWS_TIMEZONE"] = "Asia/Seoul"
os.environ["NEWS_WINDOW_MODE"] = "since_prev_day_hour"
os.environ["NEWS_WINDOW_PREV_DAY_HOUR"] = "15"

import mvp_pipeline as mvp  # noqa: E402
from notify.factory import get_notifier, resolve_channel  # noqa: E402

TZ = ZoneInfo("Asia/Seoul")


def _clear_notify_env() -> None:
    for key in list(os.environ):
        if key.startswith(("TELEGRAM_", "DISCORD_", "NOTIFY_", "APPROVE_")):
            os.environ.pop(key, None)


def test_news_window() -> None:
    os.environ["NEWS_WINDOW_MODE"] = "since_prev_day_hour"
    os.environ["NEWS_WINDOW_PREV_DAY_HOUR"] = "15"
    now = datetime(2026, 7, 15, 7, 30, tzinfo=TZ)
    start = mvp.news_window_start(now)
    assert start == datetime(2026, 7, 14, 15, 0, tzinfo=TZ), start
    assert mvp.in_news_window(datetime(2026, 7, 14, 15, 0, tzinfo=TZ), now, start)
    assert mvp.in_news_window(datetime(2026, 7, 14, 16, 0, tzinfo=TZ), now, start)
    assert not mvp.in_news_window(datetime(2026, 7, 14, 14, 59, tzinfo=TZ), now, start)
    assert mvp.in_news_window(None, now, start)

    os.environ["NEWS_WINDOW_MODE"] = "today"
    start_today = mvp.news_window_start(now)
    assert start_today == datetime(2026, 7, 15, 0, 0, tzinfo=TZ), start_today
    os.environ["NEWS_WINDOW_MODE"] = "since_prev_day_hour"
    print("OK news_window")


def test_per_article_rank_helpers() -> None:
    assert mvp.normalize_importance_item({"id": "a1", "score": 9, "drop": False})["score"] == 9
    assert mvp.normalize_importance_item({"ranked": [{"id": "a1", "score": 7}]})["id"] == "a1"
    assert mvp.normalize_importance_item({}) is None

    base = {
        "id": "a1",
        "title": "t",
        "feed_rank": 1,
        "score": 8,
        "audience": "market",
        "reason": "heuristic",
    }
    kept = mvp.apply_importance_row(base, {"score": 9, "audience": "market", "reason": "ok", "drop": False})
    assert kept is not None and kept["score"] == 9
    assert mvp.apply_importance_row(base, {"score": 1, "drop": True}) is None

    scored = [
        {"id": "hi", "score": 12, "feed_rank": 1},
        {"id": "mid", "score": 8, "feed_rank": 2},
        {"id": "lo", "score": 5, "feed_rank": 3},
    ]
    picked = mvp.select_llm_candidates(scored, min_score=8, limit=10)
    assert [a["id"] for a in picked] == ["hi", "mid"]
    capped = mvp.select_llm_candidates(scored, min_score=8, limit=1)
    assert [a["id"] for a in capped] == ["hi"]
    print("OK per_article_rank_helpers")


def test_notify_send_at() -> None:
    assert mvp.parse_notify_send_at("") is None
    assert mvp.parse_notify_send_at("07:50") == (7, 50)
    assert mvp.parse_notify_send_at("7:05") == (7, 5)
    try:
        mvp.parse_notify_send_at("25:00")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass

    now = datetime(2026, 7, 20, 7, 10, tzinfo=TZ)
    os.environ["NOTIFY_SEND_AT"] = "07:50"
    target = mvp.notify_send_at_target(now)
    assert target == datetime(2026, 7, 20, 7, 50, tzinfo=TZ), target

    late = datetime(2026, 7, 20, 7, 55, tzinfo=TZ)
    assert mvp.notify_send_at_target(late) == datetime(2026, 7, 20, 7, 50, tzinfo=TZ)
    # Past target: wait helper must return without sleeping when now is injected
    mvp.wait_until_notify_send_at(late)

    os.environ.pop("NOTIFY_SEND_AT", None)
    assert mvp.notify_send_at_target(now) is None
    print("OK notify_send_at")


def test_resolve_channel() -> None:
    _clear_notify_env()
    assert resolve_channel() == "cli"
    assert get_notifier().name == "cli"

    os.environ["NOTIFY_CHANNEL"] = "auto"
    assert resolve_channel() == "auto"
    assert get_notifier().name == "auto"

    os.environ["NOTIFY_CHANNEL"] = "discord"
    assert resolve_channel() == "discord"

    os.environ.pop("NOTIFY_CHANNEL", None)
    os.environ["DISCORD_BOT_TOKEN"] = "x"
    os.environ["DISCORD_CHANNEL_ID"] = "1"
    assert resolve_channel() == "discord"

    os.environ.pop("DISCORD_BOT_TOKEN", None)
    os.environ.pop("DISCORD_CHANNEL_ID", None)
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    os.environ["TELEGRAM_CHAT_ID"] = "1"
    assert resolve_channel() == "telegram"
    _clear_notify_env()
    print("OK resolve_channel")


def main() -> int:
    test_news_window()
    test_per_article_rank_helpers()
    test_notify_send_at()
    test_resolve_channel()
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
