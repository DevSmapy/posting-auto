"""Unit tests for template studio theme listing/clone helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "template_studio"))

from themes import clone_theme, list_editorial_themes, theme_dir  # noqa: E402


class TemplateStudioHelpersTest(unittest.TestCase):
    def test_clone_theme_copies_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            templates = Path(tmp) / "cards"
            src = templates / "editorial"
            src.mkdir(parents=True)
            (src / "design-system.css").write_text(":root{--x:1;}\n", encoding="utf-8")
            (src / "01-hook.html").write_text("<html></html>", encoding="utf-8")
            dest = clone_theme("editorial", "dawn", templates_dir=templates)
            self.assertEqual(dest.name, "editorial_dawn")
            self.assertTrue((dest / "design-system.css").is_file())
            self.assertTrue((dest / "01-hook.html").is_file())
            themes = list_editorial_themes(templates)
            self.assertIn("editorial", themes)
            self.assertIn("editorial_dawn", themes)

    def test_clone_theme_rejects_empty_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            templates = Path(tmp) / "cards"
            (templates / "editorial").mkdir(parents=True)
            with self.assertRaises(ValueError):
                clone_theme("editorial", "   ", templates_dir=templates)

    def test_clone_theme_rejects_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            templates = Path(tmp) / "cards"
            (templates / "editorial").mkdir(parents=True)
            (templates / "editorial_dawn").mkdir(parents=True)
            with self.assertRaises(FileExistsError):
                clone_theme("editorial", "dawn", templates_dir=templates)

    def test_clone_theme_rejects_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            templates = Path(tmp) / "cards"
            templates.mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):
                clone_theme("editorial", "dawn", templates_dir=templates)

    def test_theme_dir_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            templates = Path(tmp) / "cards"
            templates.mkdir(parents=True)
            with self.assertRaises(ValueError):
                theme_dir("../secret", templates_dir=templates)
            with self.assertRaises(ValueError):
                theme_dir("/tmp/secret", templates_dir=templates)
            with self.assertRaises(ValueError):
                clone_theme("../secret", "dawn", templates_dir=templates)


if __name__ == "__main__":
    unittest.main()
