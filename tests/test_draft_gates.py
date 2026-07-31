"""Tests for draft run attempt/manifest helpers and gate copy."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from draft_run import DraftRunStore  # noqa: E402
from notify.approve_copy import (  # noqa: E402
    KEEP_FINAL_WARNING,
    cleanup_prompt,
    empty_rerank_pool_message,
    exhausted_message,
    parked_timeout_message,
    remaining_line,
    reminder_message,
    render_stage_start_ack,
    timeout_message,
)
from notify.auto import AutoNotifier  # noqa: E402
from notify.base import GateAction, GateStage  # noqa: E402
from notify.cli import CliNotifier  # noqa: E402
from notify.envutil import approve_reminder_sec, approve_timeout_sec  # noqa: E402


class DraftRunStoreTest(unittest.TestCase):
    def test_content_attempts_and_exclude_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DraftRunStore(Path(tmp) / "run1", content_max=3, render_max=3)
            store.init_layout()
            a1 = store.new_content_attempt()
            (a1 / "ranked.json").write_text(
                json.dumps([{"link": "https://a.example", "title": "A"}]),
                encoding="utf-8",
            )
            a2 = store.new_content_attempt()
            (a2 / "ranked.json").write_text(
                json.dumps([{"link": "https://b.example", "title": "B"}]),
                encoding="utf-8",
            )
            store.set_selected_content("content-02")
            candidates = [
                {"link": "https://a.example", "title": "A"},
                {"link": "https://b.example", "title": "B"},
                {"link": "https://c.example", "title": "C"},
            ]
            filtered = store.exclude_prior_picks(candidates)
            self.assertEqual([c["link"] for c in filtered], ["https://c.example"])
            self.assertEqual(store.manifest.selected_content, "content-02")
            self.assertTrue(store.manifest_path.is_file())

    def test_restore_content_retry_undoes_consume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DraftRunStore(Path(tmp) / "run-retry", content_max=3, render_max=2)
            store.init_layout()
            self.assertEqual(store.consume_content_retry(), 2)
            self.assertEqual(store.restore_content_retry(), 3)
            self.assertEqual(store.manifest.content_remaining, 3)
            self.assertEqual(store.consume_render_retry(), 1)
            self.assertEqual(store.restore_render_retry(), 2)

    def test_mark_parked_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DraftRunStore(Path(tmp) / "park")
            store.init_layout()
            store.new_content_attempt()
            store.mark_parked("content")
            self.assertEqual(store.manifest.status, "parked")
            self.assertEqual(store.manifest.parked_stage, "content")
            data = json.loads(store.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "parked")
            store.clear_parked()
            self.assertEqual(store.manifest.status, "active")
            self.assertIsNone(store.manifest.parked_stage)

    def test_cleanup_keep_final_deletes_siblings_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DraftRunStore(Path(tmp) / "run2")
            store.init_layout()
            c1 = store.new_content_attempt()
            (c1 / "ranked.json").write_text("[]", encoding="utf-8")
            c2 = store.new_content_attempt()
            (c2 / "briefing.json").write_text("{}", encoding="utf-8")
            store.set_selected_content("content-02")
            r1 = store.new_render_attempt()
            (r1 / "cards" / "x.png").write_bytes(b"png")
            r2 = store.new_render_attempt()
            (r2 / "cards" / "y.png").write_bytes(b"png")
            deleted = store.cleanup_keep_final()
            self.assertIn("attempts/content-01", deleted)
            self.assertIn("renders/render-01", deleted)
            self.assertFalse((store.attempts_dir / "content-01").exists())
            self.assertTrue((store.attempts_dir / "content-02").is_dir())
            self.assertFalse((store.renders_dir / "render-01").exists())
            self.assertTrue((store.renders_dir / "render-02").is_dir())


class GateCopyTest(unittest.TestCase):
    def test_remaining_and_exhausted(self) -> None:
        self.assertIn("2️⃣", remaining_line(GateStage.CONTENT, 2, 3))
        self.assertIn("내용 재생성", exhausted_message(GateStage.CONTENT))
        self.assertIn("run_draft.sh", exhausted_message(GateStage.RENDER))

    def test_render_stage_start_ack(self) -> None:
        text = render_stage_start_ack(
            run_id="20260728_070000",
            content_attempt="content-01",
        )
        self.assertIn("① 내용 확정", text)
        self.assertIn("② 이미지 생성", text)
        self.assertIn("content-01", text)

    def test_empty_rerank_pool_message(self) -> None:
        text = empty_rerank_pool_message()
        self.assertIn("Rerank 불가", text)
        self.assertIn("차감되지 않았습니다", text)

    def test_cleanup_warning(self) -> None:
        text = cleanup_prompt(
            selected_label="content-02+render-01",
            unselected=["attempts/content-01"],
            run_id="20260728_070000",
        )
        self.assertIn(KEEP_FINAL_WARNING, text)
        self.assertIn("attempts/content-01", text)

    def test_timeout_and_parked_copy(self) -> None:
        text = timeout_message(GateStage.CONTENT, 3600, run_id="20260728_070000")
        self.assertIn("parked", text)
        self.assertIn("resume_draft.sh output/20260728_070000", text)
        self.assertIn("resume_draft.sh", parked_timeout_message("render", "rid"))
        self.assertIn("리마인더", reminder_message(GateStage.RENDER, 600))

    def test_approve_timeout_defaults(self) -> None:
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=False):
            for key in (
                "APPROVE_TIMEOUT_SEC",
                "DISCORD_APPROVE_TIMEOUT_SEC",
                "TELEGRAM_APPROVE_TIMEOUT_SEC",
                "APPROVE_REMINDER_SEC",
            ):
                os.environ.pop(key, None)
            self.assertEqual(approve_timeout_sec(), 3600)
            self.assertEqual(approve_reminder_sec(), 600)


class AutoCliGateTest(unittest.TestCase):
    def test_auto_gate_actions(self) -> None:
        n = AutoNotifier()
        self.assertEqual(
            n.wait_for_gate(GateStage.CONTENT, "p"),
            GateAction.APPROVE,
        )
        self.assertEqual(
            n.wait_for_gate(GateStage.CLEANUP, "p"),
            GateAction.KEEP_FINAL,
        )

    def test_cli_content_rerank(self) -> None:
        from unittest.mock import patch

        with patch("builtins.input", return_value="rerank"):
            action = CliNotifier().wait_for_gate(GateStage.CONTENT, "preview")
        self.assertEqual(action, GateAction.RERANK)


if __name__ == "__main__":
    unittest.main()
