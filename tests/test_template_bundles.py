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

        renderer = CardTemplateRenderer(CardFormatConfig())
        for slide in bundle.slides:
            html_doc = renderer.render_slide(slide)
            self.assertNotIn("{{", html_doc)
            self.assertIn("<br />", html_doc)  # multiline headlines/bodies


if __name__ == "__main__":
    unittest.main()
