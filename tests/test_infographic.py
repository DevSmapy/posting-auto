"""Tests for the infographic pictogram catalog and deterministic resolver."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cards.infographic import (  # noqa: E402
    GENERIC_ID,
    LIMITS,
    build_infographic_fields,
    export_infographic,
    load_catalog,
    render_infographic_html,
    resolve_pictogram,
    resolve_pictograms,
    sprite_symbol_ids,
    validate_visual_tags,
    visual_tag_options,
)


BRIEFING = {
    "title": "반도체와 금리가 함께 움직인 하루 | 오늘의 경제 브리핑 (2026-08-22)",
    "intro": "오늘 아침 경제·시장에서 주목할 이슈를 정리했습니다. 각 이슈의 배경도 함께 봅니다.",
    "insight": "성장 기대는 살아 있지만 금리가 속도를 결정합니다. 다음 지표를 봅시다.",
    "stories": [
        {
            "headline": "반도체 수요 회복 기대가 커졌습니다",
            "one_liner": "고부가 메모리 주문이 늘었습니다.",
            "what_happened": "메모리 가격이 올랐습니다.",
            "watch_next": "다음 분기 실적을 확인하세요.",
        },
        {
            "headline": "한국은행이 기준금리를 동결했습니다",
            "one_liner": "정책 신호를 확인할 시점입니다.",
        },
        {
            "headline": "아파트 분양 물량이 줄었습니다",
            "one_liner": "공급 일정이 밀렸습니다.",
        },
    ],
    "market_impact": {
        "positive": ["수출 기업 실적 기대가 살아 있습니다."],
        "neutral": ["단기 변동성은 이어질 수 있습니다."],
        "negative": ["금융비용 부담이 남아 있습니다."],
    },
    "upcoming_events": [{"date": "", "title": "주요 지표 발표", "description": ""}],
}


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


class TemplateTest(unittest.TestCase):
    def test_briefing_maps_onto_every_slot(self) -> None:
        fields, matches = build_infographic_fields(BRIEFING, date="2026.08.22")
        self.assertEqual("반도체와 금리가 함께 움직인 하루", fields["title"])
        self.assertEqual("오늘 아침 경제·시장에서 주목할 이슈를 정리했습니다.", fields["intro"])
        self.assertEqual("성장 기대는 살아 있지만 금리가 속도를 결정합니다.", fields["insight"])
        self.assertEqual(
            ["semiconductor", "central-bank", "real-estate"], [m.id for m in matches]
        )
        self.assertEqual("pg-semiconductor", fields["story_1_icon"])
        self.assertEqual("01", fields["story_1_index"])
        self.assertEqual("수출 기업 실적 기대가 살아 있습니다.", fields["impact_1_body"])
        self.assertEqual("주요 지표 발표", fields["impact_4_body"])

    def test_every_slot_respects_its_character_budget(self) -> None:
        long_briefing = dict(
            BRIEFING,
            title="가" * 200,
            intro="나" * 200,
            insight="다" * 200,
            stories=[{"headline": "라" * 200, "one_liner": "마" * 200}],
            market_impact={"positive": ["바" * 200], "neutral": [], "negative": []},
        )
        fields, _ = build_infographic_fields(long_briefing)
        for key, limit in (
            ("title", LIMITS["title"]),
            ("intro", LIMITS["intro"]),
            ("insight", LIMITS["insight"]),
            ("story_1_title", LIMITS["story_title"]),
            ("story_1_body", LIMITS["story_body"]),
            ("impact_1_body", LIMITS["impact_body"]),
        ):
            self.assertLessEqual(len(fields[key]), limit, key)
            self.assertTrue(fields[key].endswith("…"), key)

    def test_missing_stories_hide_their_row_instead_of_faking_copy(self) -> None:
        fields, _ = build_infographic_fields(dict(BRIEFING, stories=BRIEFING["stories"][:1]))
        self.assertEqual("", fields["story_1_state"])
        self.assertEqual("is-empty", fields["story_2_state"])
        self.assertEqual("", fields["story_2_title"])
        self.assertEqual("pg-generic", fields["story_2_icon"])

    def test_empty_impact_buckets_hide_their_cell(self) -> None:
        fields, _ = build_infographic_fields(
            dict(BRIEFING, market_impact={"positive": [], "neutral": [], "negative": []})
        )
        self.assertEqual("is-empty", fields["impact_1_state"])
        self.assertEqual("is-empty", fields["impact_2_state"])
        self.assertEqual("is-empty", fields["impact_3_state"])
        # NEXT is fed by upcoming_events, so it survives an empty market_impact.
        self.assertEqual("", fields["impact_4_state"])

    def test_next_cell_reads_bare_string_events_like_the_markdown_does(self) -> None:
        fields, _ = build_infographic_fields(
            dict(BRIEFING, upcoming_events=["다음 주 연준 의사록 공개"])
        )
        self.assertEqual("다음 주 연준 의사록 공개", fields["impact_4_body"])
        self.assertEqual("", fields["impact_4_state"])

    def test_next_cell_falls_back_to_watch_next(self) -> None:
        fields, _ = build_infographic_fields(dict(BRIEFING, upcoming_events=[]))
        self.assertEqual("다음 분기 실적을 확인하세요.", fields["impact_4_body"])

    def test_html_has_no_unfilled_slots_and_escapes_content(self) -> None:
        document, fields, _ = render_infographic_html(
            dict(BRIEFING, title="<script>alert(1)</script> 위험"), date="2026.08.22"
        )
        self.assertNotIn("{{", document)
        self.assertNotIn("<script>alert(1)</script>", document)
        self.assertIn("&lt;script&gt;", document)
        self.assertIn('href="#pg-semiconductor"', document)
        self.assertIn("2026.08.22", document)
        self.assertEqual("2026.08.22", fields["date"])

    def test_html_inlines_the_sprite_and_css_without_remote_assets(self) -> None:
        document, _, _ = render_infographic_html(BRIEFING)
        self.assertIn('<symbol id="pg-semiconductor"', document)
        self.assertIn("--color-primary", document)
        # Browserless has no network; the render must not wait on a font or icon fetch.
        self.assertNotIn("@import", document)
        self.assertNotIn("<link", document)
        self.assertNotIn("url(http", document)
        self.assertNotIn("<img", document)

    def test_website_labels_and_green_tokens_can_override_defaults(self) -> None:
        document, fields, _ = render_infographic_html(
            BRIEFING,
            labels={"kicker": "장전 브리핑", "impact_1_label": "긍정"},
            css_vars={"color-primary": "#006241"},
        )
        self.assertEqual("장전 브리핑", fields["kicker"])
        self.assertEqual("긍정", fields["impact_1_label"])
        self.assertIn("장전 브리핑", document)
        self.assertIn("--color-primary: #006241;", document)

    def test_export_writes_html_meta_and_survives_png_failure(self) -> None:
        class Boom:
            def screenshot_html(self, _document: str, _out: Path) -> None:
                raise RuntimeError("no chrome")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "infographic"
            result = export_infographic(
                BRIEFING, out, date="2026.08.22", renderer=Boom()
            )
            self.assertTrue(result["html"].exists())
            self.assertIsNone(result["png"])
            meta = json.loads(result["meta"].read_text(encoding="utf-8"))
            self.assertEqual({"width": 1080, "height": 1080}, meta["canvas"])
            self.assertEqual("no chrome", meta["error"])
            self.assertEqual("semiconductor", meta["pictograms"][0]["id"])

    def test_export_records_the_png_when_rendering_succeeds(self) -> None:
        class Stub:
            def screenshot_html(self, _document: str, out: Path) -> None:
                out.write_bytes(b"png")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "infographic"
            result = export_infographic(BRIEFING, out, renderer=Stub())
            self.assertEqual(out / "infographic.png", result["png"])
            meta = json.loads(result["meta"].read_text(encoding="utf-8"))
            self.assertEqual("infographic.png", meta["png"])
            self.assertEqual("", meta["error"])

    def test_png_screenshot_embeds_pretendard_as_data_url(self) -> None:
        seen: list[str] = []

        class Stub:
            def screenshot_html(self, document: str, out: Path) -> None:
                seen.append(document)
                out.write_bytes(b"png")

        with tempfile.TemporaryDirectory() as tmp:
            export_infographic(BRIEFING, Path(tmp) / "infographic", renderer=Stub())
        self.assertTrue(seen)
        self.assertIn("data:font/woff2;base64,", seen[0])
        self.assertNotIn('url("PretendardVariable.woff2")', seen[0])


if __name__ == "__main__":
    unittest.main()
