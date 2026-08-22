"""Tests for the infographic pictogram catalog and deterministic resolver."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cards.infographic import (  # noqa: E402
    GENERIC_ID,
    load_catalog,
    resolve_pictogram,
    resolve_pictograms,
    sprite_symbol_ids,
    validate_visual_tags,
    visual_tag_options,
)


def story(**fields: object) -> dict[str, object]:
    base = {
        "headline": "",
        "one_liner": "",
        "what_happened": "",
        "why_important": "",
        "watch_next": "",
    }
    base.update(fields)
    return base


class CatalogTest(unittest.TestCase):
    def test_catalog_has_48_pictograms_plus_generic(self) -> None:
        catalog = load_catalog()
        self.assertIn(GENERIC_ID, catalog)
        self.assertEqual(48, len([p for p in catalog if p != GENERIC_ID]))

    def test_every_catalog_id_has_exactly_one_sprite_symbol(self) -> None:
        catalog = load_catalog()
        expected = {p.symbol_id for p in catalog.values()}
        self.assertEqual(expected, set(sprite_symbol_ids()))

    def test_catalog_ids_and_tags_are_unique(self) -> None:
        catalog = load_catalog()
        owner: dict[str, str] = {}
        for pictogram in catalog.values():
            for tag in pictogram.tags:
                self.assertNotIn(
                    tag, owner, f"tag {tag!r} shared by {owner.get(tag)} and {pictogram.id}"
                )
                owner[tag] = pictogram.id

    def test_generic_is_fallback_only_and_not_offered_to_the_llm(self) -> None:
        catalog = load_catalog()
        self.assertEqual((), catalog[GENERIC_ID].tags)
        self.assertNotIn(GENERIC_ID, visual_tag_options())
        self.assertEqual(48, len(visual_tag_options()))


class VisualTagValidationTest(unittest.TestCase):
    def test_unknown_tags_are_dropped_not_fatal(self) -> None:
        valid, invalid = validate_visual_tags(["semiconductor", "rocket", ""])
        self.assertEqual(["semiconductor"], valid)
        self.assertEqual(["rocket"], invalid)

    def test_accepts_a_bare_string_and_dedupes(self) -> None:
        self.assertEqual((["bank"], []), validate_visual_tags("bank"))
        self.assertEqual((["bank"], []), validate_visual_tags(["bank", "BANK"]))


class ResolverTest(unittest.TestCase):
    def test_valid_llm_tag_wins_over_headline_keyword(self) -> None:
        match = resolve_pictogram(
            story(headline="증시 마감 요약", visual_tags=["semiconductor"])
        )
        self.assertEqual("semiconductor", match.id)
        self.assertEqual("visual_tags", match.source)

    def test_invalid_llm_tag_falls_back_to_keyword_rules(self) -> None:
        match = resolve_pictogram(
            story(headline="코스피 상승 마감", visual_tags=["moon-rocket"])
        )
        self.assertEqual("stock-market", match.id)
        self.assertEqual("headline", match.source)
        self.assertEqual(("moon-rocket",), match.dropped_tags)

    def test_headline_outranks_body(self) -> None:
        match = resolve_pictogram(
            story(headline="전세 계약 구조가 바뀐다", what_happened="반도체 수출도 늘었다")
        )
        self.assertEqual("housing-lease", match.id)
        self.assertEqual("headline", match.source)

    def test_body_is_used_when_the_headline_has_no_signal(self) -> None:
        match = resolve_pictogram(
            story(headline="오늘의 이슈", what_happened="가계부채 대출 잔액이 늘었다")
        )
        self.assertEqual("loan", match.id)
        self.assertEqual("body", match.source)

    def test_tie_is_broken_by_catalog_priority(self) -> None:
        # semiconductor (10) and interest-rate (25) both match; the lower number wins.
        match = resolve_pictogram(story(headline="금리 인하 기대에 반도체주 강세"))
        self.assertEqual("semiconductor", match.id)

    def test_directional_llm_tag_without_direction_keyword_is_dropped(self) -> None:
        match = resolve_pictogram(
            story(headline="환율 흐름 점검", visual_tags=["trend-up"])
        )
        self.assertEqual("exchange-rate", match.id)
        self.assertEqual(("trend-up",), match.dropped_tags)

    def test_directional_llm_tag_is_kept_when_the_copy_states_direction(self) -> None:
        match = resolve_pictogram(
            story(headline="지표가 급등했다", visual_tags=["trend-up"])
        )
        self.assertEqual("trend-up", match.id)
        self.assertEqual((), match.dropped_tags)

    def test_generic_fallback_when_nothing_matches(self) -> None:
        match = resolve_pictogram(story(headline="오늘의 이야기", what_happened="특별한 일이 없었다"))
        self.assertEqual(GENERIC_ID, match.id)
        self.assertEqual("fallback", match.source)

    def test_latin_tags_need_word_boundaries(self) -> None:
        # "ai" must not fire inside "said"; the sentence has no other signal.
        match = resolve_pictogram(story(headline="he said nothing new today"))
        self.assertEqual(GENERIC_ID, match.id)

    def test_resolution_is_stable_across_repeated_calls(self) -> None:
        stories = [
            story(headline="반도체 수출 회복"),
            story(headline="한국은행 기준금리 동결"),
            story(headline="아파트 분양 물량 감소"),
        ]
        first = [m.id for m in resolve_pictograms(stories)]
        self.assertEqual(["semiconductor", "central-bank", "real-estate"], first)
        self.assertEqual(first, [m.id for m in resolve_pictograms(stories)])

    def test_missing_visual_tags_key_is_fine(self) -> None:
        match = resolve_pictogram({"headline": "국채 발행 확대"})
        self.assertEqual("bond", match.id)
        self.assertEqual((), match.dropped_tags)


if __name__ == "__main__":
    unittest.main()
