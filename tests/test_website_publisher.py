"""WebsitePublisher: briefing JSON → site Markdown."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from publish.website import WebsitePublisher, article_slug, render_post  # noqa: E402
from test_assemble_blog import BRIEFING_V2  # noqa: E402

from mvp_pipeline import assemble_blog_markdown  # noqa: E402


class WebsitePublisherTest(unittest.TestCase):
    def test_dry_run_does_not_write(self) -> None:
        with TemporaryDirectory() as tmp:
            posts = Path(tmp) / "posts"
            publisher = WebsitePublisher(posts)
            result = publisher.publish({"briefing": BRIEFING_V2, "dry_run": True})
            self.assertEqual(result.status, "dry_run")
            self.assertTrue(result.published_url.startswith("/articles/"))
            self.assertFalse(posts.exists() and any(posts.iterdir()))

    def test_writes_frontmatter_and_keeps_body(self) -> None:
        with TemporaryDirectory() as tmp:
            posts = Path(tmp) / "posts"
            briefing_md = Path(tmp) / "briefing.md"
            briefing_md.write_text("# keep\n", encoding="utf-8")
            md = assemble_blog_markdown(BRIEFING_V2)
            publisher = WebsitePublisher(posts)
            result = publisher.publish({"briefing": BRIEFING_V2, "markdown": md})
            self.assertEqual(result.status, "success")
            written = Path(result.detail or "")
            self.assertTrue(written.is_file())
            text = written.read_text(encoding="utf-8")
            self.assertIn("title: \"금리·반도체·AI가 동시에 흔든 하루\"", text)
            self.assertIn("category: \"시장\"", text)
            self.assertIn("status: \"published\"", text)
            self.assertIn("한국은행이 기준금리를 인상했습니다", text)
            self.assertTrue(briefing_md.is_file())
            self.assertEqual(briefing_md.read_text(encoding="utf-8"), "# keep\n")

    def test_slug_uses_date_and_title_not_date_only(self) -> None:
        when = datetime.fromisoformat("2026-07-20T07:00:00+09:00")
        slug = article_slug(BRIEFING_V2, when)
        self.assertTrue(slug.startswith("2026-07-20-"))
        self.assertNotEqual(slug, "2026-07-20")
        self.assertIn("금리", slug)

    def test_same_day_different_titles_get_different_files(self) -> None:
        other = dict(BRIEFING_V2)
        other["title"] = "부동산 대기 수요 | 오늘의 경제 브리핑 (2026-07-20)"
        with TemporaryDirectory() as tmp:
            posts = Path(tmp) / "posts"
            publisher = WebsitePublisher(posts)
            first = publisher.publish({"briefing": BRIEFING_V2})
            second = publisher.publish({"briefing": other})
            self.assertEqual(first.status, "success")
            self.assertEqual(second.status, "success")
            self.assertNotEqual(Path(first.detail or "").name, Path(second.detail or "").name)
            self.assertEqual(len(list(posts.glob("*.md"))), 2)

    def test_slug_collision_gets_suffix_and_does_not_clobber(self) -> None:
        with TemporaryDirectory() as tmp:
            posts = Path(tmp) / "posts"
            posts.mkdir()
            slug, rendered = render_post(BRIEFING_V2)
            other_title = "다른 글"
            (posts / f"{slug}.md").write_text(
                f"---\ntitle: \"{other_title}\"\n---\nkeep\n",
                encoding="utf-8",
            )
            publisher = WebsitePublisher(posts)
            result = publisher.publish({"briefing": BRIEFING_V2})
            self.assertEqual(result.status, "success")
            dest = Path(result.detail or "")
            self.assertEqual(dest.name, f"{slug}-2.md")
            original = (posts / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn("다른 글", original)

    def test_write_failure_does_not_delete_briefing_md(self) -> None:
        with TemporaryDirectory() as tmp:
            briefing_md = Path(tmp) / "briefing.md"
            briefing_md.write_text("original\n", encoding="utf-8")
            publisher = WebsitePublisher(Path(tmp) / "posts")
            with patch.object(Path, "write_text", side_effect=OSError("disk")):
                result = publisher.publish({"briefing": BRIEFING_V2})
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.error_type, "CONTENT_WRITE_FAILED")
            self.assertEqual(briefing_md.read_text(encoding="utf-8"), "original\n")

    def test_missing_briefing_fails(self) -> None:
        publisher = WebsitePublisher(Path("/tmp/unused-posts"))
        result = publisher.publish({})
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_type, "CONTENT_WRITE_FAILED")


if __name__ == "__main__":
    unittest.main()
