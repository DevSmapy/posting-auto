"""Unit tests for story timeout fallback and lifecycle defaults."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mvp_pipeline import (  # noqa: E402
    _generation_mode_label,
    briefing_timeout_ms,
    ensure_runtime_before_llm,
    main,
    ollama_is_ready,
    ollama_options,
    release_ollama_after_llm,
    story_timeout_ms,
)


class StoryTimeoutTest(unittest.TestCase):
    def test_prefers_story_timeout(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OLLAMA_STORY_TIMEOUT_MS": "90000",
                "OLLAMA_BRIEFING_TIMEOUT_MS": "900000",
                "OLLAMA_TIMEOUT_MS": "300000",
            },
            clear=False,
        ):
            self.assertEqual(story_timeout_ms(), 90000)
            self.assertEqual(briefing_timeout_ms(), 90000)

    def test_falls_back_to_briefing_timeout(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "OLLAMA_STORY_TIMEOUT_MS"}
        env["OLLAMA_BRIEFING_TIMEOUT_MS"] = "900000"
        env["OLLAMA_TIMEOUT_MS"] = "300000"
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(story_timeout_ms(), 900000)

    def test_falls_back_to_ollama_timeout(self) -> None:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"OLLAMA_STORY_TIMEOUT_MS", "OLLAMA_BRIEFING_TIMEOUT_MS"}
        }
        env["OLLAMA_TIMEOUT_MS"] = "300000"
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(story_timeout_ms(), 300000)

    def test_final_default_120000(self) -> None:
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "OLLAMA_STORY_TIMEOUT_MS",
                "OLLAMA_BRIEFING_TIMEOUT_MS",
                "OLLAMA_TIMEOUT_MS",
            }
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(story_timeout_ms(), 120000)


class OllamaOptionsTest(unittest.TestCase):
    def test_num_ctx_defaults_to_4096_when_unset(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "OLLAMA_NUM_CTX"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(ollama_options()["num_ctx"], 4096)

    def test_num_ctx_respects_env(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_NUM_CTX": "2048"}, clear=False):
            self.assertEqual(ollama_options()["num_ctx"], 2048)


class GenerationModeLabelTest(unittest.TestCase):
    def test_known_modes(self) -> None:
        self.assertEqual(_generation_mode_label("llm"), "llm")
        self.assertEqual(_generation_mode_label("mixed"), "mixed")
        self.assertEqual(_generation_mode_label("heuristic"), "heuristic")

    def test_unknown_defaults_to_llm(self) -> None:
        self.assertEqual(_generation_mode_label("other"), "llm")


class ReleaseLifecycleDefaultTest(unittest.TestCase):
    def test_release_skipped_when_auto_off(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_AUTO_CONTAINER": "0", "DRAFT_AUTO_AUX": "0"}):
            with patch("mvp_pipeline.subprocess.run") as run:
                release_ollama_after_llm()
                run.assert_not_called()

    def test_release_invoked_when_auto_on(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_AUTO_CONTAINER": "1", "DRAFT_AUTO_AUX": "0"}):
            with patch("mvp_pipeline.subprocess.run") as run:
                release_ollama_after_llm()
                run.assert_called_once()
                self.assertIn("draft_release_after_llm", " ".join(run.call_args[0][0]))


class RuntimeBootstrapTest(unittest.TestCase):
    def test_ollama_ready_short_circuits(self) -> None:
        with patch("mvp_pipeline.requests.get") as get:
            get.return_value.ok = True
            self.assertTrue(ollama_is_ready())

        with patch("mvp_pipeline.requests.get") as get:
            get.return_value.ok = False
            self.assertFalse(ollama_is_ready())

        with patch(
            "mvp_pipeline.requests.get",
            side_effect=requests.RequestException("boom"),
        ):
            self.assertFalse(ollama_is_ready())

        with patch("mvp_pipeline.ollama_is_ready", return_value=True):
            with patch("mvp_pipeline.subprocess.run") as run:
                ensure_runtime_before_llm("draft")
                run.assert_not_called()

    def test_dry_run_does_not_bootstrap(self) -> None:
        with patch("mvp_pipeline.ollama_is_ready", return_value=False):
            with patch("mvp_pipeline.subprocess.run") as run:
                ensure_runtime_before_llm("dry_run")
                run.assert_not_called()

    def test_draft_bootstraps_when_ollama_is_down(self) -> None:
        with patch.dict(
            os.environ,
            {"OLLAMA_AUTO_CONTAINER": "0", "DRAFT_AUTO_AUX": "0"},
            clear=False,
        ):
            with patch("mvp_pipeline.ollama_is_ready", return_value=False):
                with patch("mvp_pipeline.subprocess.run") as run:
                    ensure_runtime_before_llm("draft")
                    run.assert_called_once()
                    self.assertEqual(os.environ["OLLAMA_AUTO_CONTAINER"], "1")
                    self.assertEqual(os.environ["DRAFT_AUTO_AUX"], "1")
                    self.assertIn("draft_start_all", " ".join(run.call_args[0][0]))


class DraftApproveFlowTest(unittest.TestCase):
    def test_two_stage_gates_then_cleanup(self) -> None:
        calls: list[str] = []

        class _Store:
            backend = "memory"

            def filter_new(self, candidates):  # noqa: ANN001
                return candidates

            def reopen(self) -> None:
                calls.append("store.reopen")

            def close(self) -> None:
                calls.append("store.close")

        class _Notifier:
            def wait_for_gate(self, stage, preview, **kwargs):  # noqa: ANN001
                from notify.base import GateAction, GateStage

                stage_s = GateStage(stage) if not isinstance(stage, GateStage) else stage
                calls.append(f"gate:{stage_s.value}")
                if stage_s == GateStage.CLEANUP:
                    return GateAction.KEEP_FINAL
                return GateAction.APPROVE

            def send_text(self, text):  # noqa: ANN001
                calls.append("notifier.send_text")

        briefing = {"title": "draft", "slides": [], "core_summary": []}
        picked = [{"title": "A", "score": 1, "link": "https://example.com/a"}]

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.dict(
                    os.environ,
                    {
                        "MVP_MODE": "draft",
                        "OUTPUT_DIR": tmp,
                        "CONTENT_RETRY_MAX": "3",
                        "RENDER_RETRY_MAX": "3",
                    },
                    clear=False,
                ),
                patch("mvp_pipeline.ensure_runtime_before_llm"),
                patch("mvp_pipeline.get_notifier", return_value=_Notifier()),
                patch("mvp_pipeline.resolve_channel", return_value="slack"),
                patch("mvp_pipeline.SeenUrlsStore", return_value=_Store()),
                patch(
                    "mvp_pipeline.fetch_candidates",
                    return_value=[{"id": "1", "title": "A", "link": "https://example.com/a"}],
                ),
                patch("mvp_pipeline.rank_articles", return_value=picked),
                patch("mvp_pipeline.build_briefing", return_value=(briefing, "llm")),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.render_cards_for_approve", return_value=[]),
                patch("mvp_pipeline.preview_text", return_value="preview"),
                patch("mvp_pipeline.release_ollama_after_llm"),
                patch(
                    "mvp_pipeline.ensure_aux_before_publish",
                    side_effect=lambda: calls.append("ensure_aux_before_publish"),
                ),
                patch(
                    "mvp_pipeline.release_aux_after_approve_render",
                    side_effect=lambda: calls.append("release_aux_after_approve_render"),
                ),
                patch(
                    "mvp_pipeline.wait_until_notify_send_at",
                    side_effect=lambda: calls.append("wait_until_notify_send_at"),
                ),
                patch(
                    "mvp_pipeline.run_publish",
                    side_effect=lambda *args, **kwargs: calls.append("run_publish"),
                ),
            ):
                self.assertEqual(main(), 0)

        self.assertEqual(
            calls,
            [
                "wait_until_notify_send_at",
                "gate:content",
                "ensure_aux_before_publish",
                "release_aux_after_approve_render",
                "gate:render",
                "ensure_aux_before_publish",
                "store.reopen",
                "run_publish",
                "gate:cleanup",
                "notifier.send_text",
                "store.close",
            ],
        )


if __name__ == "__main__":
    unittest.main()
