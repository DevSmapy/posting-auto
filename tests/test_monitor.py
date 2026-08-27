"""Tests for dashboard state reader and text render."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dashboard import render_text  # noqa: E402
from monitor import emit, llm_begin, llm_end, read_state, reset_runtime_cache, set_run_dir  # noqa: E402


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(tmp: Path, name: str = "20260817_070001") -> Path:
    path = tmp / name
    path.mkdir(parents=True, exist_ok=True)
    return path


class MonitorStateTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("POSTING_MONITOR_DIR", None)
        os.environ.pop("MVP_MODE", None)
        os.environ.pop("DASHBOARD_STALE_SEC", None)

    def tearDown(self) -> None:
        os.environ.pop("POSTING_MONITOR_DIR", None)
        os.environ.pop("MVP_MODE", None)
        os.environ.pop("DASHBOARD_STALE_SEC", None)

    def test_idle_empty_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            out.mkdir()
            lock = Path(tmp) / "autonomous.lock"
            state = read_state(output=out, lock_file=lock, probe=False)
        self.assertEqual(state["status"], "IDLE")
        text = render_text(state)
        self.assertIn("IDLE", text)
        self.assertIn("Posting Auto 2.0", text)

    def test_running_from_lock_and_partial_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            _write(run / "candidates.json", [{"id": "a"}, {"id": "b"}])
            _write(
                run / "monitor.json",
                {
                    "run_id": run.name,
                    "mode": "autonomous",
                    "stage": "WRITE",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            lock = Path(tmp) / "lock.json"
            _write(lock, {"pid": os.getpid(), "run_id": run.name, "started_at": datetime.now(timezone.utc).isoformat()})
            state = read_state(output=out, lock_file=lock, probe=False)
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["run_id"], run.name)
        names = {row["name"]: row for row in state["pipeline"]}
        self.assertEqual(names["Collect"]["status"], "success")
        self.assertEqual(names["Collect"]["count"], 2)
        self.assertEqual(names["Write"]["status"], "running")
        text = render_text(state)
        self.assertIn("RUNNING", text)
        self.assertIn(run.name, text)
        self.assertIn("✓", text)
        self.assertIn("→", text)

    def test_complete_from_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            _write(run / "candidates.json", [1, 2, 3])
            _write(run / "ranked.json", [1, 2])
            _write(run / "briefing.json", {"stories": [{"headline": "미국 금리 동결"}]})
            _write(
                run / "editorial_result.json",
                {
                    "revision_count": 1,
                    "review": {"overall": "pass", "stories": [{"index": 0, "decision": "pass"}]},
                    "editor_decision": {"decision": "publish"},
                },
            )
            (run / "briefing.md").write_text("# hi\n", encoding="utf-8")
            _write(run / "publish_result.json", {"ig_media_id": "ig-1"})
            _write(
                run / "website_result.json",
                {"status": "success", "url": "/articles/2026-08-20-hi"},
            )
            _write(run / "monitor.json", {"ended": True, "ok": True, "run_id": run.name, "mode": "autonomous"})
            lock = Path(tmp) / "missing.lock"
            state = read_state(output=out, lock_file=lock, probe=False)
        self.assertEqual(state["status"], "COMPLETE")
        self.assertEqual(state["stories"][0]["status"], "pass")
        ig = [p for p in state["publish"] if p["channel"] == "Instagram"][0]
        self.assertEqual(ig["status"], "success")
        self.assertEqual(ig["id"], "ig-1")
        tistory = [p for p in state["publish"] if p["channel"] == "Tistory"][0]
        self.assertEqual(tistory["status"], "skipped")
        website = [p for p in state["publish"] if p["channel"] == "Website"][0]
        self.assertEqual(website["status"], "success")
        self.assertEqual(website["id"], "/articles/2026-08-20-hi")
        text = render_text(state)
        self.assertIn("COMPLETE", text)
        self.assertIn("미국 금리", text)
        self.assertIn("PASS", text)

    def test_failed_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            _write(run / "preflight.json", {"ok": False, "checks": []})
            _write(run / "monitor.json", {"ended": True, "ok": False, "run_id": run.name})
            state = read_state(output=out, lock_file=Path(tmp) / "no.lock", probe=False)
        self.assertEqual(state["status"], "FAILED")
        self.assertIn("preflight", state["failure_reason"])
        self.assertIn("FAILED", render_text(state))

    def test_failed_editorial_reject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            _write(
                run / "editorial_result.json",
                {"editor_decision": {"decision": "reject", "reason": "minimum_story_count:0<3"}},
            )
            _write(run / "briefing.json", {"stories": []})
            _write(run / "monitor.json", {"ended": True, "ok": True, "run_id": run.name})
            state = read_state(output=out, lock_file=Path(tmp) / "no.lock", probe=False)
        self.assertEqual(state["status"], "FAILED")
        self.assertIn("minimum_story_count", state["failure_reason"])

    def test_corrupt_json_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            (run / "briefing.json").write_text("{", encoding="utf-8")
            (run / "monitor.json").write_text("not-json", encoding="utf-8")
            (run / "candidates.json").write_text("[1,2", encoding="utf-8")
            state = read_state(output=out, lock_file=Path(tmp) / "no.lock", probe=False)
        self.assertIn(state["status"], {"IDLE", "COMPLETE", "RUNNING", "FAILED"})
        render_text(state)

    def test_missing_files_idle_or_empty_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            _run(out)
            state = read_state(output=out, lock_file=Path(tmp) / "no.lock", probe=False)
        self.assertTrue(state["status"] in {"IDLE", "COMPLETE"})
        self.assertEqual(state["stories"], [])
        render_text(state)

    def test_probe_exception_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            reset_runtime_cache()
            with patch("runtime.preflight.check_network", side_effect=RuntimeError("boom")):
                state = read_state(output=out, lock_file=Path(tmp) / "no.lock", probe=True)
        names = {row["name"]: row["status"] for row in state["runtime"]}
        self.assertEqual(names.get("Network"), "unknown")
        self.assertEqual(names.get("Ollama"), "unknown")

    def test_emit_and_llm_span(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "20260817_070001"
            run.mkdir()
            set_run_dir(run)
            emit(run_id=run.name, stage="COLLECT", event="run started")
            llm_begin("llm")
            llm_end(ok=True)
            llm_end(ok=False)
            data = json.loads((run / "monitor.json").read_text(encoding="utf-8"))
        self.assertEqual(data["stage"], "COLLECT")
        self.assertEqual(len(data["events"]), 1)
        self.assertFalse(data["llm"]["in_flight"])
        self.assertEqual(data["llm"]["calls"], 2)
        self.assertEqual(data["llm"]["failures"], 1)
        set_run_dir(None)

    def test_emit_never_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "not-a-dir"
            blocker.write_text("x", encoding="utf-8")
            self.addCleanup(set_run_dir, None)
            set_run_dir(blocker)
            emit(stage="COLLECT")

    def test_editor_snapshot_keeps_original_indexes(self) -> None:
        from editorial.loop import _story_snapshot

        rows = _story_snapshot(
            {"stories": [{"headline": "keep-me"}, {"headline": "drop-me"}]},
            {
                "stories": [
                    {"index": 0, "decision": "pass"},
                    {"index": 1, "decision": "reject"},
                ]
            },
            excluded_ids=[1],
        )
        self.assertEqual([row["index"] for row in rows], [0, 1])
        self.assertEqual(rows[0]["headline"], "keep-me")
        self.assertEqual(rows[1]["headline"], "drop-me")
        self.assertEqual(rows[1]["status"], "reject")

    def test_publish_hang_banner_and_steps(self) -> None:
        kst = __import__("zoneinfo").ZoneInfo("Asia/Seoul")
        now = datetime(2026, 8, 20, 7, 34, 0, tzinfo=kst)
        event_at = datetime(2026, 8, 20, 6, 42, 0, tzinfo=kst)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out, "20260820_060022")
            (run / "briefing.md").write_text("# md\n", encoding="utf-8")
            _write(
                run / "monitor.json",
                {
                    "run_id": run.name,
                    "mode": "autonomous",
                    "stage": "PUBLISH",
                    "started_at": datetime(2026, 8, 20, 6, 0, 22, tzinfo=kst).isoformat(),
                    "events": [{"timestamp": event_at.isoformat(), "message": "publish started"}],
                },
            )
            stamp = event_at.timestamp()
            os.utime(run / "briefing.md", (stamp, stamp))
            os.utime(run / "monitor.json", (stamp, stamp))
            lock = Path(tmp) / "lock.json"
            _write(
                lock,
                {"pid": os.getpid(), "run_id": run.name, "started_at": datetime(2026, 8, 20, 6, 0, 22, tzinfo=kst).isoformat()},
            )
            state = read_state(output=out, lock_file=lock, probe=False, now=now)
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["stale_level"], "hang")
        names = {row["name"]: row["status"] for row in state["publish_steps"]}
        self.assertEqual(names["MD"], "success")
        self.assertEqual(names["Cards"], "running")
        ig = [p for p in state["publish"] if p["channel"] == "Instagram"][0]
        self.assertEqual(ig["status"], "pending")
        text = render_text(state)
        self.assertIn("SUSPECT HANG", text)
        self.assertIn("52m since last event", text)
        self.assertIn("MD ✓", text)
        self.assertIn("now: Cards", text)

    def test_stale_banner_follows_fresher_artifact_age(self) -> None:
        text = render_text(
            {
                "status": "RUNNING",
                "stale_level": "stale",
                "last_event_age_sec": 52 * 60,
                "last_artifact_age_sec": 12 * 60,
                "activity_age_sec": 12 * 60,
                "clock": "07:34:00 KST",
            }
        )
        self.assertIn("STALE?", text)
        self.assertIn("12m since last artifact", text)
        self.assertNotIn("52m", text)

    def test_stale_banner_newer_artifact_via_read_state(self) -> None:
        kst = __import__("zoneinfo").ZoneInfo("Asia/Seoul")
        now = datetime(2026, 8, 20, 7, 34, 0, tzinfo=kst)
        event_at = datetime(2026, 8, 20, 6, 42, 0, tzinfo=kst)
        artifact_at = datetime(2026, 8, 20, 7, 22, 0, tzinfo=kst)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out, "20260820_060022")
            (run / "briefing.md").write_text("# md\n", encoding="utf-8")
            _write(
                run / "monitor.json",
                {
                    "run_id": run.name,
                    "mode": "autonomous",
                    "stage": "PUBLISH",
                    "started_at": datetime(2026, 8, 20, 6, 0, 22, tzinfo=kst).isoformat(),
                    "events": [{"timestamp": event_at.isoformat(), "message": "publish started"}],
                },
            )
            os.utime(run / "briefing.md", (artifact_at.timestamp(), artifact_at.timestamp()))
            os.utime(run / "monitor.json", (event_at.timestamp(), event_at.timestamp()))
            lock = Path(tmp) / "lock.json"
            _write(
                lock,
                {"pid": os.getpid(), "run_id": run.name, "started_at": datetime(2026, 8, 20, 6, 0, 22, tzinfo=kst).isoformat()},
            )
            state = read_state(output=out, lock_file=lock, probe=False, now=now)
        text = render_text(state)
        self.assertEqual(state["stale_level"], "stale")
        self.assertIn("12m since last artifact", text)
        self.assertNotIn("52m", text)

    def test_autonomous_no_lock_no_ended_is_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            _write(
                run / "monitor.json",
                {
                    "run_id": run.name,
                    "mode": "autonomous",
                    "stage": "PUBLISH",
                    "events": [{"timestamp": datetime.now(timezone.utc).isoformat(), "message": "publish started"}],
                },
            )
            lock = Path(tmp) / "missing.lock"
            state = read_state(output=out, lock_file=lock, probe=False)
        self.assertEqual(state["status"], "FAILED")
        self.assertIn("ended missing (no live lock)", state["failure_reason"])

    def test_draft_no_lock_no_ended_stays_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            _write(
                run / "monitor.json",
                {
                    "run_id": run.name,
                    "mode": "draft",
                    "stage": "REVIEW",
                    "events": [{"timestamp": datetime.now(timezone.utc).isoformat(), "message": "waiting approve"}],
                },
            )
            lock = Path(tmp) / "missing.lock"
            state = read_state(output=out, lock_file=lock, probe=False)
        self.assertEqual(state["status"], "RUNNING")

    def test_publish_guard_failed_step_and_strip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            (run / "briefing.md").write_text("# md\n", encoding="utf-8")
            _write(run / "publish_guard.json", {"ok": False, "blockers": ["instagram_not_configured"]})
            _write(
                run / "monitor.json",
                {
                    "run_id": run.name,
                    "mode": "autonomous",
                    "stage": "PUBLISH",
                    "events": [{"timestamp": datetime.now(timezone.utc).isoformat(), "message": "publish blocked"}],
                },
            )
            lock = Path(tmp) / "lock.json"
            _write(lock, {"pid": os.getpid(), "run_id": run.name, "started_at": datetime.now(timezone.utc).isoformat()})
            state = read_state(output=out, lock_file=lock, probe=False)
            names = {row["name"]: row["status"] for row in state["publish_steps"]}
            text = render_text(state)
        self.assertEqual(state["status"], "FAILED")
        self.assertIn("publish_guard:", state["failure_reason"])
        self.assertIn("instagram_not_configured", state["failure_reason"])
        self.assertEqual(names["MD"], "success")
        self.assertEqual(names["Guard"], "failed")
        self.assertIn("Guard ✗", text)
        self.assertIn("FAILED", text)

    def test_website_failure_is_read_only_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            (run / "briefing.md").write_text("# md\n", encoding="utf-8")
            _write(
                run / "website_result.json",
                {"status": "failed", "error_type": "GIT_PUSH_FAILED"},
            )
            _write(
                run / "monitor.json",
                {"ended": True, "ok": False, "run_id": run.name, "mode": "autonomous"},
            )
            state = read_state(output=out, lock_file=Path(tmp) / "no.lock", probe=False)
        website = [p for p in state["publish"] if p["channel"] == "Website"][0]
        self.assertEqual(website["status"], "failed")
        ig = [p for p in state["publish"] if p["channel"] == "Instagram"][0]
        self.assertEqual(ig["status"], "paused")
        self.assertIn("GIT_PUSH_FAILED", state["failure_reason"])

    def test_zombie_dead_pid_is_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            _write(
                run / "monitor.json",
                {
                    "run_id": run.name,
                    "mode": "autonomous",
                    "stage": "PUBLISH",
                    "events": [{"timestamp": datetime.now(timezone.utc).isoformat(), "message": "publish started"}],
                },
            )
            lock = Path(tmp) / "lock.json"
            _write(lock, {"pid": 999999, "run_id": run.name, "started_at": datetime.now(timezone.utc).isoformat()})
            with patch("monitor._pid_alive", return_value=False):
                state = read_state(output=out, lock_file=lock, probe=False)
        self.assertEqual(state["status"], "FAILED")
        self.assertIn("ended missing (pid dead)", state["failure_reason"])
        text = render_text(state)
        self.assertIn("FAILED", text)
        self.assertIn("ended missing (pid dead)", text)
        self.assertIn("dead", text)

    def test_reject_leftover_without_ended_uses_fail_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            _write(
                run / "editorial_result.json",
                {"editor_decision": {"decision": "reject", "reason": "minimum_story_count:0<3"}},
            )
            _write(run / "briefing.json", {"stories": []})
            _write(run / "monitor.json", {"run_id": run.name, "stage": "REVIEW"})
            lock = Path(tmp) / "lock.json"
            _write(lock, {"pid": 999999, "run_id": run.name})
            with patch("monitor._pid_alive", return_value=False):
                state = read_state(output=out, lock_file=lock, probe=False)
        self.assertEqual(state["status"], "FAILED")
        self.assertIn("minimum_story_count", state["failure_reason"])

    def test_publish_steps_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            _write(run / "monitor.json", {"ended": True, "ok": True, "run_id": run.name})
            (run / "briefing.md").write_text("# md\n", encoding="utf-8")
            state = read_state(output=out, lock_file=Path(tmp) / "no.lock", probe=False)
            names = {row["name"]: row["status"] for row in state["publish_steps"]}
            self.assertEqual(names["MD"], "success")
            self.assertEqual(names["Cards"], "pending")
            cards = run / "cards"
            cards.mkdir()
            (cards / "01.png").write_bytes(b"png")
            _write(run / "image_urls.json", ["https://example/1.png"])
            _write(run / "creation_id.json", {"creation_id": "c1"})
            _write(run / "publish_result.json", {"ig_media_id": "ig-1"})
            state = read_state(output=out, lock_file=Path(tmp) / "no.lock", probe=False)
            names = {row["name"]: row["status"] for row in state["publish_steps"]}
        self.assertEqual(names["Cards"], "success")
        self.assertEqual(names["R2"], "success")
        self.assertEqual(names["IG"], "success")

    def test_live_recent_activity_not_stale(self) -> None:
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = _run(out)
            _write(
                run / "monitor.json",
                {
                    "run_id": run.name,
                    "mode": "autonomous",
                    "stage": "PUBLISH",
                    "started_at": now.isoformat(),
                    "events": [{"timestamp": now.isoformat(), "message": "publish started"}],
                },
            )
            lock = Path(tmp) / "lock.json"
            _write(lock, {"pid": os.getpid(), "run_id": run.name, "started_at": now.isoformat()})
            state = read_state(output=out, lock_file=lock, probe=False, now=now)
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["stale_level"], "")
        self.assertNotIn("STALE", render_text(state))
        self.assertNotIn("SUSPECT HANG", render_text(state))


if __name__ == "__main__":
    unittest.main()
