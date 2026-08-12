"""Tests for autonomous run lock."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime.run_lock import RunLock, autonomous_run_lock  # noqa: E402


class RunLockTest(unittest.TestCase):
    def test_acquire_and_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "autonomous.lock"
            lock = RunLock(path, run_id="run-a")
            ok, reason = lock.acquire()
            self.assertTrue(ok, reason)
            self.assertTrue(path.is_file())
            lock.release()
            self.assertFalse(path.is_file())

    def test_second_acquire_blocked_while_held(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "autonomous.lock"
            first = RunLock(path, run_id="run-a")
            second = RunLock(path, run_id="run-b")
            ok1, _ = first.acquire()
            ok2, reason = second.acquire()
            self.assertTrue(ok1)
            self.assertFalse(ok2)
            self.assertIn("active lock", reason)
            first.release()

    def test_stale_lock_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "autonomous.lock"
            stale = {
                "pid": 999999,
                "started_at": "2000-01-01T00:00:00+00:00",
                "run_id": "old",
            }
            path.write_text(json.dumps(stale), encoding="utf-8")
            lock = RunLock(path, run_id="new")
            ok, _ = lock.acquire()
            self.assertTrue(ok)
            lock.release()

    def test_context_manager_releases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "autonomous.lock"
            with patch("runtime.run_lock.DEFAULT_LOCK_PATH", path):
                with autonomous_run_lock("ctx-run") as (acquired, _reason):
                    self.assertTrue(acquired)
                    self.assertTrue(path.is_file())
            self.assertFalse(path.is_file())


if __name__ == "__main__":
    unittest.main()
