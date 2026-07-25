"""Tests for card news assembly, caption, and HTML templates."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cards import (  # noqa: E402
    CardAssembler,
    CardCopyRules,
    CardFormatConfig,
    CardTemplateRenderer,
    InstagramCaptionBuilder,
    SlideType,
)
from cards.fixtures import sample_related_keywords, sample_stories  # noqa: E402
from mvp_pipeline import assemble_briefing_from_stories, preview_text  # noqa: E402


class CardCopyRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = CardCopyRules(
            CardFormatConfig(story_body_max_chars=40, headline_max_chars=20)
        )

    def test_prefers_one_liner(self) -> None:
        body = self.rules.story_body(
            {
                "one_liner": "한 줄 요약입니다.",
                "what_happened": "긴 사실 서술입니다. 두 번째 문장.",
            }
        )
        self.assertEqual(body, "한 줄 요약입니다.")

    def test_falls_back_to_what_happened(self) -> None:
        body = self.rules.story_body(
            {"what_happened": "첫 문장입니다. 둘째 문장입니다."}
        )
        self.assertIn("첫 문장", body)
        self.assertLessEqual(len(body), 41)

    def test_clips_long_headline(self) -> None:
        hl = self.rules.story_headline({"headline": "가" * 50})
        self.assertLessEqual(len(hl), 21)
        self.assertTrue(hl.endswith("…"))


class InstagramCaptionBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = InstagramCaptionBuilder(CardFormatConfig())
        self.now = datetime(2026, 7, 25, 7, 30, tzinfo=timezone.utc)

    def test_sections_and_hashtags(self) -> None:
        post = self.builder.build(
            sample_stories(),
            self.now,
            related_keywords=sample_related_keywords(),
        )
        self.assertIn("오늘의 포인트", post.body)
        self.assertIn("1)", post.body)
        self.assertIn("투자 권유", post.body)
        self.assertIn("경제뉴스", post.hashtags)
        self.assertIn("금리", post.hashtags)
        self.assertIn("#경제뉴스", post.full_text)
        self.assertLessEqual(len(post.full_text), 2100)

    def test_truncates_to_caption_max(self) -> None:
        cfg = CardFormatConfig(caption_max_chars=80, max_hashtags=2)
        post = InstagramCaptionBuilder(cfg).build(sample_stories(), self.now)
        self.assertLessEqual(len(post.full_text), 80)

    def test_empty_stories_fallback(self) -> None:
        post = self.builder.build([], self.now)
        self.assertIn("오늘의 포인트", post.body)
        self.assertTrue(post.full_text)


class CardAssemblerTest(unittest.TestCase):
    def test_slide_order_and_counts(self) -> None:
        now = datetime(2026, 7, 25, tzinfo=timezone.utc)
        bundle = CardAssembler(CardFormatConfig()).assemble(
            sample_stories(), now, related_keywords=sample_related_keywords()
        )
        self.assertEqual(bundle.slides[0].type, SlideType.COVER)
        self.assertEqual(bundle.slides[-1].type, SlideType.DISCLAIMER)
        self.assertEqual(len(bundle.slides), 5)  # cover + 3 + disclaimer
        self.assertEqual(bundle.slides[1].index, "01")
        self.assertTrue(bundle.post.body)
        self.assertTrue(bundle.post.hashtags)

    def test_pipeline_briefing_uses_cards(self) -> None:
        now = datetime(2026, 7, 25, tzinfo=timezone.utc)
        briefing = assemble_briefing_from_stories(sample_stories(), now)
        self.assertEqual(briefing["slides"][0]["type"], "cover")
        self.assertEqual(briefing["slides"][-1]["type"], "disclaimer")
        self.assertIn("오늘의 포인트", briefing["caption"])
        self.assertIn("instagram_post", briefing)
        self.assertIn("#", briefing["instagram_post"])

    def test_preview_includes_caption(self) -> None:
        now = datetime(2026, 7, 25, tzinfo=timezone.utc)
        briefing = assemble_briefing_from_stories(sample_stories(), now)
        text = preview_text(briefing, [], generation_mode="heuristic")
        self.assertIn("인스타 본문", text)
        self.assertIn("슬라이드:", text)


class CardTemplateRendererTest(unittest.TestCase):
    def test_no_placeholders_left(self) -> None:
        now = datetime(2026, 7, 25, tzinfo=timezone.utc)
        bundle = CardAssembler(CardFormatConfig()).assemble(sample_stories(), now)
        renderer = CardTemplateRenderer(CardFormatConfig())
        for slide in bundle.slides:
            html_doc = renderer.render_slide(slide)
            self.assertNotIn("{{", html_doc)
            self.assertIn(slide.headline, html_doc)


if __name__ == "__main__":
    unittest.main()
