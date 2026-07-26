"""Unit tests for Browserless screenshot URL construction."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cards.config import CardFormatConfig  # noqa: E402
from cards.renderer import CardRenderer  # noqa: E402


class BrowserlessScreenshotTest(unittest.TestCase):
    def test_default_path_is_chromium_not_chrome(self) -> None:
        cfg = CardFormatConfig()
        self.assertEqual(cfg.browserless_screenshot_path, "/chromium/screenshot")
        self.assertNotIn("/chrome/", cfg.browserless_screenshot_path)

    def test_posts_chromium_path_with_token(self) -> None:
        cfg = CardFormatConfig(
            browserless_url="http://localhost:3000",
            browserless_screenshot_path="/chromium/screenshot",
            browserless_token="local-dev-token",
            width=1080,
            height=1350,
        )
        renderer = CardRenderer(cfg)
        fake = MagicMock()
        fake.raise_for_status = MagicMock()
        fake.content = b"PNGDATA"

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "slide.png"
            with patch("cards.renderer.requests.post", return_value=fake) as post:
                renderer._screenshot_browserless("<html></html>", out)
            args, kwargs = post.call_args
            self.assertEqual(args[0], "http://localhost:3000/chromium/screenshot")
            self.assertEqual(kwargs["params"]["token"], "local-dev-token")
            self.assertEqual(out.read_bytes(), b"PNGDATA")


if __name__ == "__main__":
    unittest.main()
