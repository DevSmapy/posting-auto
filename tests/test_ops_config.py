"""Tests for ops console config and cron schedule gate."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ops_config import (  # noqa: E402
    load_ops_config,
    normalize_ops,
    resolve_bundle_id,
    resolve_feeds,
    resolve_notify_at,
    save_ops_config,
    should_run_now,
    write_last_run_date,
)


class OpsConfigTest(unittest.TestCase):
    def test_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ops.json"
            data = load_ops_config(path)
            self.assertEqual(data["schedule"]["run_at"], "07:00")
            self.assertEqual(data["cards"]["bundle_id"], "daily_briefing")
            self.assertGreaterEqual(len(data["feeds"]), 2)

    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ops.json"
            save_ops_config(
                {
                    "timezone": "Asia/Seoul",
                    "schedule": {
                        "weekdays": [1, 3, 5],
                        "run_at": "8:05",
                        "notify_at": "8:30",
                    },
                    "feeds": [{"label": "TECH", "url": "https://example.com/rss"}],
                    "cards": {"bundle_id": "numbers"},
                },
                path,
            )
            loaded = load_ops_config(path)
            self.assertEqual(loaded["schedule"]["run_at"], "08:05")
            self.assertEqual(loaded["schedule"]["notify_at"], "08:30")
            self.assertEqual(loaded["schedule"]["weekdays"], [1, 3, 5])
            self.assertEqual(loaded["feeds"][0]["label"], "TECH")
            self.assertEqual(loaded["cards"]["bundle_id"], "numbers")

    def test_failed_atomic_replace_preserves_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ops.json"
            path.write_text('{"existing": true}\n', encoding="utf-8")
            with patch("ops_config.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    save_ops_config({}, path)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"existing": true}\n')
            self.assertEqual(list(path.parent.glob(".ops.json.*.tmp")), [])

    def test_normalize_rejects_bad_time(self) -> None:
        with self.assertRaises(ValueError):
            normalize_ops({"schedule": {"run_at": "25:00", "notify_at": "07:50"}})

    def test_resolve_notify_env_wins(self) -> None:
        with patch.dict(os.environ, {"NOTIFY_SEND_AT": "09:15"}, clear=False):
            self.assertEqual(resolve_notify_at({"schedule": {"notify_at": "07:50"}}), "09:15")

    def test_resolve_notify_from_ops(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "NOTIFY_SEND_AT"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                resolve_notify_at({"schedule": {"notify_at": "08:40"}}),
                "08:40",
            )

    def test_resolve_feeds_from_ops(self) -> None:
        ops = normalize_ops(
            {
                "feeds": [
                    {"label": "A", "url": "https://a.example/rss"},
                    {"label": "B", "url": "https://b.example/rss"},
                    {"label": "skip", "url": ""},
                ]
            }
        )
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"GNEWS_BUSINESS_RSS", "GNEWS_NATION_RSS"}
        }
        with patch.dict(os.environ, env, clear=True):
            feeds = resolve_feeds(ops)
        self.assertEqual(
            feeds,
            [("A", "https://a.example/rss"), ("B", "https://b.example/rss")],
        )

    def test_resolve_feeds_env_wins_over_ops(self) -> None:
        ops = normalize_ops(
            {"feeds": [{"label": "A", "url": "https://a.example/rss"}]}
        )
        with patch.dict(
            os.environ,
            {
                "GNEWS_BUSINESS_RSS": "https://env.example/business",
                "GNEWS_NATION_RSS": "",
            },
            clear=False,
        ):
            feeds = resolve_feeds(ops)
        self.assertEqual(feeds[0], ("BUSINESS", "https://env.example/business"))
        self.assertEqual(feeds[1][0], "NATION")
        self.assertNotEqual(feeds[1][1], "https://a.example/rss")

    def test_write_last_run_uses_configured_timezone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "last-run"
            with (
                patch("ops_config.load_ops_config", return_value={"timezone": "UTC"}),
                patch("ops_config.datetime") as mocked_datetime,
            ):
                mocked_datetime.now.return_value = datetime(
                    2026, 7, 30, 23, 30, tzinfo=ZoneInfo("UTC")
                )
                write_last_run_date(path=path)
                mocked_datetime.now.assert_called_once_with(ZoneInfo("UTC"))
            self.assertEqual(path.read_text(encoding="utf-8"), "2026-07-30\n")

    def test_resolve_bundle_env_wins(self) -> None:
        ops = normalize_ops({"cards": {"bundle_id": "daily_briefing"}})
        with patch.dict(os.environ, {"CARD_BUNDLE_ID": "myth_vs_truth"}):
            self.assertEqual(resolve_bundle_id(ops), "myth_vs_truth")


class ShouldRunNowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tz = ZoneInfo("Asia/Seoul")
        self.ops = normalize_ops(
            {
                "timezone": "Asia/Seoul",
                "schedule": {
                    "weekdays": [1, 2, 3, 4, 5],
                    "run_at": "07:00",
                    "notify_at": "07:50",
                },
            }
        )

    def test_inside_window(self) -> None:
        now = datetime(2026, 7, 28, 7, 2, tzinfo=self.tz)
        ok, reason = should_run_now(now, ops=self.ops, last_run=None, window_minutes=5)
        self.assertTrue(ok, reason)

    def test_outside_window(self) -> None:
        now = datetime(2026, 7, 28, 7, 10, tzinfo=self.tz)
        ok, reason = should_run_now(now, ops=self.ops, last_run=None, window_minutes=5)
        self.assertFalse(ok)
        self.assertIn("outside run window", reason)

    def test_wrong_weekday(self) -> None:
        now = datetime(2026, 7, 26, 7, 0, tzinfo=self.tz)
        ok, reason = should_run_now(now, ops=self.ops, last_run=None)
        self.assertFalse(ok)
        self.assertIn("weekday", reason)

    def test_already_ran_today(self) -> None:
        now = datetime(2026, 7, 28, 7, 1, tzinfo=self.tz)
        ok, reason = should_run_now(
            now, ops=self.ops, last_run="2026-07-28", window_minutes=5
        )
        self.assertFalse(ok)
        self.assertIn("already ran", reason)

    def test_window_crossing_midnight_uses_scheduled_date(self) -> None:
        ops = normalize_ops(
            {
                "timezone": "Asia/Seoul",
                "schedule": {
                    "weekdays": [1],
                    "run_at": "23:58",
                    "notify_at": "23:59",
                },
            }
        )
        now = datetime(2026, 7, 28, 0, 1, tzinfo=self.tz)
        ok, reason = should_run_now(now, ops=ops, last_run=None, window_minutes=5)
        self.assertTrue(ok, reason)

        ok, reason = should_run_now(
            now,
            ops=ops,
            last_run="2026-07-27",
            window_minutes=5,
        )
        self.assertFalse(ok)
        self.assertIn("2026-07-27", reason)


if __name__ == "__main__":
    unittest.main()
