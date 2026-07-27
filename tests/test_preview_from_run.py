"""Tests for preview_cardnews --from-run / --briefing-json."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import preview_cardnews as preview  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "briefing_min.json"


class PreviewFromRunTest(unittest.TestCase):
    def test_export_from_briefing_json_no_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "20260725_083000"
            run_dir.mkdir()
            shutil.copy(FIXTURE, run_dir / "briefing.json")
            out = run_dir / "cards-preview"

            argv = [
                "preview_cardnews.py",
                "--from-run",
                str(run_dir),
                "--no-png",
            ]
            with patch.object(sys, "argv", argv):
                code = preview.main()
            self.assertEqual(code, 0)
            self.assertTrue(out.is_dir())
            htmls = sorted(out.glob("slide-*.html"))
            self.assertGreaterEqual(len(htmls), 5)
            self.assertTrue((out / "instagram_post.txt").is_file())
            self.assertTrue((out / "caption.txt").is_file())
            post = (out / "instagram_post.txt").read_text(encoding="utf-8")
            self.assertIn("테스트 후킹", post)
            self.assertIn("#경제뉴스", post)
            # --no-png: no PNGs from this run
            self.assertEqual(list(out.glob("slide-*.png")), [])

    def test_briefing_json_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            argv = [
                "preview_cardnews.py",
                "--briefing-json",
                str(FIXTURE),
                "--out",
                str(out),
                "--no-png",
            ]
            with patch.object(sys, "argv", argv):
                code = preview.main()
            self.assertEqual(code, 0)
            self.assertGreaterEqual(len(list(out.glob("slide-*.html"))), 5)

    def test_missing_stories_and_slides_exits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.json"
            empty.write_text(json.dumps({"title": "x"}), encoding="utf-8")
            argv = [
                "preview_cardnews.py",
                "--briefing-json",
                str(empty),
                "--out",
                str(Path(tmp) / "out"),
                "--no-png",
            ]
            with (
                patch.object(sys, "argv", argv),
                self.assertRaises(SystemExit) as ctx,
            ):
                preview.main()
            self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
