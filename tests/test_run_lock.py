"""Tests for autonomous run lock."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime.run_lock import RunLock, _pid_alive, autonomous_run_lock  # noqa: E402


def _race_acquire(path_str: str, run_id: str, barrier: mp.Barrier, queue: mp.Queue) -> None:
    barrier.wait(timeout=5)
    lock = RunLock(Path(path_str), run_id=run_id)
    ok, reason = lock.acquire()
    queue.put((run_id, ok, reason))
    if ok:
        # Hold briefly so losers observe the active lock.
        barrier.wait(timeout=5)
        lock.release()
    else:
        try:
            barrier.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass


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

    def test_concurrent_acquire_only_one_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "autonomous.lock"
            ctx = mp.get_context("spawn")
            barrier = ctx.Barrier(2)
            queue: mp.Queue = ctx.Queue()
            procs = [
                ctx.Process(
                    target=_race_acquire,
                    args=(str(path), f"run-{i}", barrier, queue),
                )
                for i in range(2)
            ]
            for p in procs:
                p.start()
            results = [queue.get(timeout=10) for _ in procs]
            for p in procs:
                p.join(timeout=10)
                self.assertEqual(p.exitcode, 0)
            wins = [r for r in results if r[1]]
            losses = [r for r in results if not r[1]]
            self.assertEqual(len(wins), 1, results)
            self.assertEqual(len(losses), 1, results)
            self.assertIn("active lock", losses[0][2])

    def test_pid_alive_permission_error_means_alive(self) -> None:
        with patch("runtime.run_lock.os.kill", side_effect=PermissionError):
            self.assertTrue(_pid_alive(12345))
        with patch("runtime.run_lock.os.kill", side_effect=ProcessLookupError):
            self.assertFalse(_pid_alive(12345))

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

    def test_corrupt_lock_reclaimed_after_grace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "autonomous.lock"
            path.write_text("{not json", encoding="utf-8")
            past = time.time() - 60
            os.utime(path, (past, past))
            lock = RunLock(path, run_id="new")
            ok, reason = lock.acquire()
            self.assertTrue(ok, reason)
            lock.release()

    def test_empty_lock_reclaimed_after_grace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "autonomous.lock"
            path.write_text("", encoding="utf-8")
            past = time.time() - 60
            os.utime(path, (past, past))
            lock = RunLock(path, run_id="new")
            ok, reason = lock.acquire()
            self.assertTrue(ok, reason)
            lock.release()

    def test_young_incomplete_lock_not_stolen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "autonomous.lock"
            path.write_text("", encoding="utf-8")
            lock = RunLock(path, run_id="new")
            with patch("runtime.run_lock.time.sleep"):
                ok, reason = lock.acquire()
            self.assertFalse(ok)
            self.assertIn("incomplete", reason)
            self.assertTrue(path.is_file())

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
