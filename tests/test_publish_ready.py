"""Tests for final/publish_ready package helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from draft_run import DraftRunStore  # noqa: E402
from publish.ready import (  # noqa: E402
    ensure_publish_ready_from_run,
    load_publish_ready_package,
    write_publish_ready_package,
)


class PublishReadyPackageTest(unittest.TestCase):
    def test_write_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            png_a = root / "a.png"
            png_b = root / "b.png"
            png_a.write_bytes(b"png-a")
            png_b.write_bytes(b"png-b")
            final = root / "final"
            pkg = write_publish_ready_package(
                final,
                png_paths=[png_a, png_b],
                briefing={"instagram_post": "캡션 본문", "title": "타이틀"},
            )
            self.assertTrue((pkg.root / "publish_manifest.json").is_file())
            self.assertEqual(len(pkg.png_paths), 2)
            self.assertEqual(pkg.caption, "캡션 본문")
            loaded = load_publish_ready_package(root)
            self.assertEqual(loaded.caption, "캡션 본문")
            self.assertEqual([p.name for p in loaded.png_paths], ["a.png", "b.png"])
            self.assertEqual(loaded.manifest.get("title"), "타이틀")

    def test_copy_into_final_writes_publish_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DraftRunStore(Path(tmp) / "run")
            store.init_layout()
            png = Path(tmp) / "slide-01.png"
            png.write_bytes(b"x")
            store.copy_into_final(
                briefing={"instagram_post": "hello", "title": "T"},
                card_pngs=[png],
            )
            ready = store.final_dir / "publish_ready"
            self.assertTrue((ready / "publish_manifest.json").is_file())
            self.assertTrue((ready / "cards" / "slide-01.png").is_file())
            self.assertIn("hello", (ready / "instagram_post.txt").read_text(encoding="utf-8"))

    def test_copy_into_final_keeps_infographic_out_of_the_card_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DraftRunStore(Path(tmp) / "run")
            store.init_layout()
            png = Path(tmp) / "slide-01.png"
            png.write_bytes(b"x")
            info = Path(tmp) / "infographic.png"
            info.write_bytes(b"y")
            store.copy_into_final(
                briefing={"instagram_post": "hello", "title": "T"},
                card_pngs=[png],
                infographic_png=info,
            )
            self.assertTrue((store.final_dir / "infographic.png").is_file())
            self.assertFalse((store.final_dir / "cards" / "infographic.png").exists())
            ready = store.final_dir / "publish_ready"
            self.assertEqual(
                ["slide-01.png"], sorted(p.name for p in (ready / "cards").iterdir())
            )

    def test_ensure_builds_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            final_cards = run / "final" / "cards"
            final_cards.mkdir(parents=True)
            (final_cards / "s1.png").write_bytes(b"1")
            (final_cards / "s2.png").write_bytes(b"2")
            (run / "final" / "briefing.json").write_text(
                json.dumps({"instagram_post": "from briefing"}),
                encoding="utf-8",
            )
            pkg = ensure_publish_ready_from_run(run)
            self.assertEqual(pkg.caption, "from briefing")
            self.assertEqual(len(pkg.png_paths), 2)


if __name__ == "__main__":
    unittest.main()
