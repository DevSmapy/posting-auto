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
    briefing_timeout_ms,
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
