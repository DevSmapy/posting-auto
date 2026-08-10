"""Runtime preflight unit checks (no live network required for output dir)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime.preflight import check_output_dir, check_publish_env, run_preflight  # noqa: E402


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
                with patch(
                    "runtime.preflight.check_publish_env",
                    return_value={"name": "publish_env", "ok": True, "present": {}},
                ):
                    result = run_preflight(require_ollama=False)
        self.assertTrue(result["ok"], result)

    def test_preflight_requires_ollama_when_asked(self) -> None:
        with patch("runtime.preflight.check_network", return_value={"name": "network", "ok": True}):
            with patch(
                "runtime.preflight.check_ollama",
                return_value={"name": "ollama", "ok": False, "error": "down"},
            ):
                with patch(
                    "runtime.preflight.check_publish_env",
                    return_value={"name": "publish_env", "ok": True, "present": {}},
                ):
                    result = run_preflight(require_ollama=True)
        self.assertFalse(result["ok"], result)

    def test_publish_env_fails_when_auto_publish_cards_missing_creds(self) -> None:
        env = {
            "AUTO_PUBLISH": "1",
            "PUBLISH_CARDS": "1",
            "R2_ENDPOINT": "",
            "IG_USER_ID": "",
            "META_ACCESS_TOKEN": "",
        }
        with patch.dict("os.environ", env, clear=False):
            result = check_publish_env()
        self.assertFalse(result["ok"], result)
        self.assertTrue(result.get("missing"), result)


if __name__ == "__main__":
    unittest.main()
