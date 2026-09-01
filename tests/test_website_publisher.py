"""WebsitePublisher: briefing JSON → site Markdown."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from publish.protocol import PublishResult  # noqa: E402
from publish.website import (  # noqa: E402
    WebsitePublisher,
    article_slug,
    maybe_git_push,
    maybe_verify_deploy,
    public_http_url,
    publish_approved_briefing,
    render_post,
    sources_of,
)
from test_assemble_blog import BRIEFING_V2  # noqa: E402

from mvp_pipeline import assemble_blog_markdown  # noqa: E402


class WebsitePublisherTest(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_graphic = os.environ.get("WEBSITE_INFOGRAPHIC")
        os.environ["WEBSITE_INFOGRAPHIC"] = "0"

    def tearDown(self) -> None:
        if self._prev_graphic is None:
            os.environ.pop("WEBSITE_INFOGRAPHIC", None)
        else:
            os.environ["WEBSITE_INFOGRAPHIC"] = self._prev_graphic
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
            self.assertIn("kind: \"briefing\"", text)
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

    def test_kind_note_is_written(self) -> None:
        briefing = dict(BRIEFING_V2)
        briefing["kind"] = "note"
        briefing["title"] = "지하철 파업 예고"
        with TemporaryDirectory() as tmp:
            publisher = WebsitePublisher(Path(tmp) / "posts")
            result = publisher.publish({"briefing": briefing})
            self.assertEqual(result.status, "success")
            text = Path(result.detail or "").read_text(encoding="utf-8")
            self.assertIn("kind: \"note\"", text)

    def test_unknown_kind_falls_back_to_briefing(self) -> None:
        briefing = dict(BRIEFING_V2)
        briefing["kind"] = "flash"
        _, rendered = render_post(briefing)
        self.assertIn("kind: \"briefing\"", rendered)

    def test_pipeline_news_tag_stays_in_market_category(self) -> None:
        briefing = dict(BRIEFING_V2)
        briefing["blog_tags"] = ["경제", "브리핑", "뉴스"]
        _, rendered = render_post(briefing)
        self.assertIn("category: \"시장\"", rendered)
        self.assertIn("  - \"뉴스\"", rendered)

    def test_strips_pipeline_infographic_embed_from_body(self) -> None:
        md = (
            "# 제목\n\n"
            "![브리핑 인포그래픽](infographic.png)\n\n"
            "오늘 아침 이슈를 정리했습니다.\n"
        )
        _, rendered = render_post(BRIEFING_V2, markdown=md)
        _fm, body = rendered.split("\n---\n", 1)
        self.assertNotIn("infographic.png", body)
        self.assertNotIn("브리핑 인포그래픽", body)
        self.assertIn("오늘 아침 이슈를 정리했습니다.", body)

    def test_verify_skipped_without_site_url(self) -> None:
        with patch.dict(os.environ, {"SITE_BASE_URL": ""}, clear=False):
            self.assertIsNone(maybe_verify_deploy("/articles/x", "제목"))

    def test_verify_checks_status_and_title(self) -> None:
        class _Resp:
            status = 200

            def read(self) -> bytes:
                return "<h1>확인제목</h1>".encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):  # noqa: ANN002
                return None

        with patch.dict(os.environ, {"SITE_BASE_URL": "https://briefing.example"}, clear=False):
            with patch("publish.website.urlopen", return_value=_Resp()):
                result = maybe_verify_deploy("/articles/x", "확인제목")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "success")


    def test_non_http_source_urls_are_dropped(self) -> None:
        briefing = dict(BRIEFING_V2)
        briefing["stories"] = [
            {
                **BRIEFING_V2["stories"][0],
                "source_url": "javascript:alert(1)",
            }
        ]
        briefing["sources"] = [{"title": "파일", "url": "file:///etc/passwd"}]
        sources = sources_of(briefing)
        self.assertEqual(sources[0]["title"], "연합뉴스")
        self.assertNotIn("url", sources[0])
        self.assertNotIn("url", sources[1])
        _, rendered = render_post(briefing)
        self.assertNotIn("javascript:", rendered)
        self.assertNotIn("file://", rendered)

    def test_http_source_urls_are_kept(self) -> None:
        self.assertEqual(public_http_url("https://news.example/a"), "https://news.example/a")
        self.assertIsNone(public_http_url("javascript:alert(1)"))
        self.assertIsNone(public_http_url(""))

    def test_write_failure_payload_includes_detail(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with patch.object(
                WebsitePublisher,
                "publish",
                return_value=PublishResult(
                    channel="website",
                    status="failed",
                    error_type="CONTENT_WRITE_FAILED",
                    detail="disk",
                ),
            ):
                payload = publish_approved_briefing({"title": "x"}, "md", run_dir)
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["detail"], "disk")
            self.assertIsNone(payload.get("path"))
            saved = (run_dir / "website_result.json").read_text(encoding="utf-8")
            self.assertIn("disk", saved)

    def test_git_push_commits_only_the_post(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001
            calls.append(list(cmd))

            class Result:
                returncode = 0
                stdout = ""
                stderr = ""

            return Result()

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            post = root / "website" / "src" / "content" / "posts" / "note.md"
            post.parent.mkdir(parents=True)
            post.write_text("x\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {"WEBSITE_GIT_PUSH": "1"}, clear=False),
                patch("publish.website.REPO_ROOT", root),
                patch("publish.website.subprocess.run", side_effect=fake_run),
            ):
                result = maybe_git_push(post)
        self.assertIsNone(result)
        commit = next(cmd for cmd in calls if cmd[:2] == ["git", "commit"])
        self.assertEqual(commit[-2], "--")
        self.assertEqual(commit[-1], "website/src/content/posts/note.md")

    def test_graphic_frontmatter_when_renderer_writes_png(self) -> None:
        def fake_shot(html_doc: str, out_path: Path) -> None:
            out_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 20)

        from cards.renderer import CardRenderer

        with TemporaryDirectory() as tmp:
            posts = Path(tmp) / "posts"
            images = Path(tmp) / "images"
            publisher = WebsitePublisher(
                posts, images_dir=images, renderer=CardRenderer(screenshot_fn=fake_shot)
            )
            result = publisher.publish({"briefing": BRIEFING_V2, "render_graphic": True})
            self.assertEqual(result.status, "success")
            text = Path(result.detail or "").read_text(encoding="utf-8")
            self.assertIn("graphic: \"/images/posts/", text)
            self.assertIn("-infographic.png", text)
            pngs = list(images.glob("*-infographic.png"))
            self.assertEqual(len(pngs), 1)


if __name__ == "__main__":
    unittest.main()
