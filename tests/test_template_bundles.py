"""Tests for template bundle catalog and narrative assembly."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cards import (  # noqa: E402
    CardFormatConfig,
    CardTemplateRenderer,
    NarrativeAssembler,
    get_bundle,
    list_bundles,
    recommend_for_economy_society,
)
from cards.fixtures_why_cause_impact import (  # noqa: E402
    CAPTION_HOOK,
    why_cause_impact_example,
    why_cause_impact_keywords,
)


class TemplateCatalogTest(unittest.TestCase):
    def test_bundles_loaded(self) -> None:
        bundles = list_bundles()
        self.assertGreaterEqual(len(bundles), 6)
        ids = {b.id for b in bundles}
        self.assertIn("why_cause_impact", ids)
        self.assertIn("daily_briefing", ids)
        self.assertIn("editorial_carousel", ids)

    def test_recommend_why_cause_impact(self) -> None:
        picked = recommend_for_economy_society()
        self.assertEqual(picked.id, "why_cause_impact")
        self.assertEqual(picked.card_count, 8)


class NarrativeAssemblerTest(unittest.TestCase):
    def test_why_cause_impact_example(self) -> None:
        now = datetime(2026, 7, 25, tzinfo=timezone.utc)
        template = get_bundle("why_cause_impact")
        bundle = NarrativeAssembler(CardFormatConfig()).assemble(
            why_cause_impact_example(),
            now,
            bundle=template,
            related_keywords=why_cause_impact_keywords(),
            caption_hook=CAPTION_HOOK,
        )
        self.assertEqual(len(bundle.slides), 8)
        self.assertEqual(bundle.slides[0].type.value, "hook")
        self.assertEqual(bundle.slides[-1].type.value, "cta")
        self.assertEqual(bundle.template_id, "why_cause_impact")
        self.assertIn("미국", bundle.post.full_text)
        self.assertIn(CAPTION_HOOK, bundle.post.body)
        for tag in bundle.post.hashtags:
            self.assertIn(f"#{tag}", bundle.post.full_text)

        renderer = CardTemplateRenderer(CardFormatConfig())
        for slide in bundle.slides:
            html_doc = renderer.render_slide(slide)
            self.assertNotIn("{{", html_doc)
            self.assertIn("<br />", html_doc)  # multiline headlines/bodies

    def test_daily_briefing_repeatable_story_slot(self) -> None:
        now = datetime(2026, 7, 25, tzinfo=timezone.utc)
        template = get_bundle("daily_briefing")
        self.assertTrue(any(s.repeatable for s in template.slides))
        filled = [
            {"role": "cover", "headline": "표지", "body": "테마"},
            {"role": "story", "headline": "이슈1", "body": "한줄1"},
            {"role": "story", "headline": "이슈2", "body": "한줄2"},
            {"role": "story", "headline": "이슈3", "body": "한줄3"},
            {"role": "disclaimer", "headline": "면책", "body": "투자 권유 아님"},
        ]
        bundle = NarrativeAssembler(CardFormatConfig()).assemble(
            filled, now, bundle=template
        )
        self.assertEqual(len(bundle.slides), 5)
        self.assertEqual(bundle.slides[0].role, "cover")
        self.assertEqual(bundle.slides[-1].role, "disclaimer")

        filled5 = filled[:1] + [
            {"role": "story", "headline": f"이슈{i}", "body": f"한줄{i}"}
            for i in range(1, 6)
        ] + filled[-1:]
        bundle5 = NarrativeAssembler(CardFormatConfig()).assemble(
            filled5, now, bundle=template
        )
        self.assertEqual(len(bundle5.slides), 7)

        with self.assertRaises(ValueError):
            NarrativeAssembler(CardFormatConfig()).assemble(
                filled[:1]
                + [{"role": "story", "headline": "x", "body": "y"}]
                + filled[-1:],
                now,
                bundle=template,
            )

    def test_caption_hook_truncates_body_before_hashtags(self) -> None:
        now = datetime(2026, 7, 25, tzinfo=timezone.utc)
        template = get_bundle("why_cause_impact")
        # Tiny budget: body alone exceeds cap → no hashtags, body has ellipsis only.
        tight = CardFormatConfig(caption_max_chars=40)
        bundle = NarrativeAssembler(tight).assemble(
            why_cause_impact_example(),
            now,
            bundle=template,
            related_keywords=why_cause_impact_keywords(),
            caption_hook=CAPTION_HOOK,
        )
        self.assertEqual(bundle.post.body, bundle.post.full_text)
        self.assertEqual(bundle.post.hashtags, ())
        self.assertNotIn("#", bundle.post.body)
        self.assertTrue(bundle.post.body.endswith("…"))

        # Room for body + some tags: drop overflowing tags, never partial tags.
        mid = CardFormatConfig(caption_max_chars=900)
        bundle2 = NarrativeAssembler(mid).assemble(
            why_cause_impact_example(),
            now,
            bundle=template,
            related_keywords=why_cause_impact_keywords(),
            caption_hook=CAPTION_HOOK,
        )
        self.assertLessEqual(len(bundle2.post.full_text), 900)
        self.assertGreater(len(bundle2.post.hashtags), 0)
        for tag in bundle2.post.hashtags:
            self.assertIn(f"#{tag}", bundle2.post.full_text)
        # Body must stay free of hashtag text / partial fragments.
        self.assertNotRegex(bundle2.post.body, r"#\w")
        self.assertTrue(
            bundle2.post.full_text.startswith(bundle2.post.body),
        )


if __name__ == "__main__":
    unittest.main()
