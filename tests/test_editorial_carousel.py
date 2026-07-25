"""Tests for editorial Instagram carousel UI template (placeholders)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cards.editorial import EditorialCarouselTemplate, placeholder_content  # noqa: E402


class EditorialCarouselTest(unittest.TestCase):
    def test_placeholder_keys_cover_all_slides(self) -> None:
        content = placeholder_content("BRAND")
        self.assertEqual(len(content), 8)
        for name in content:
            self.assertTrue(name.endswith(".html"))

    def test_render_has_no_unfilled_placeholders(self) -> None:
        slides = EditorialCarouselTemplate(brand="BRAND").render_all()
        self.assertEqual(len(slides), 8)
        for slide in slides:
            self.assertNotIn("{{", slide.html)
            self.assertIn("1080px", slide.html)
            self.assertIn("1350px", slide.html)
            # Must stay placeholder-like (no real news claims)
            self.assertTrue(
                "플레이스홀더" in slide.html
                or "PLACEHOLDER" in slide.html.upper()
                or "BRAND" in slide.html
                or "Scenario" in slide.html
                or "Save this post" in slide.html
            )

    def test_export_html_and_meta(self) -> None:
        pack = EditorialCarouselTemplate(brand="BRAND")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = pack.export(out, render_png=False)
            self.assertEqual(len(result["html"]), 8)
            self.assertTrue((out / "template_meta.json").exists())
            self.assertTrue((out / "placeholders.json").exists())
            self.assertTrue((out / "instagram_post.txt").exists())


if __name__ == "__main__":
    unittest.main()
