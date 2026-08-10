"""Runtime preflight unit checks (no live network required for output dir)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime.preflight import check_output_dir, run_preflight  # noqa: E402


class PreflightTest(unittest.TestCase):
    def test_output_dir_writable(self) -> None:
        result = check_output_dir()
        self.assertTrue(result["ok"], result)

    def test_preflight_without_requiring_ollama(self) -> None:
        with patch("runtime.preflight.check_network", return_value={"name": "network", "ok": True}):
            with patch(
                "runtime.preflight.check_ollama",
                return_value={"name": "ollama", "ok": False, "error": "down"},
            ):
                result = run_preflight(require_ollama=False)
        self.assertTrue(result["ok"], result)

    def test_preflight_requires_ollama_when_asked(self) -> None:
        with patch("runtime.preflight.check_network", return_value={"name": "network", "ok": True}):
            with patch(
                "runtime.preflight.check_ollama",
                return_value={"name": "ollama", "ok": False, "error": "down"},
            ):
                result = run_preflight(require_ollama=True)
        self.assertFalse(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
