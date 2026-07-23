"""Unit tests for story timeout fallback and lifecycle defaults."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mvp_pipeline import (  # noqa: E402
    _generation_mode_label,
    briefing_timeout_ms,
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


if __name__ == "__main__":
    unittest.main()
