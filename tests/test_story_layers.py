"""Tests for layered story generation and fallback behavior."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mvp_pipeline import build_briefing, summarize_story_layers  # noqa: E402


ARTICLE = {
    "id": "aaaaaaaa",
    "title": "Fed holds rates steady",
    "snippet": "US inflation cooled and traders shifted rate expectations.",
    "source": "Reuters",
    "link": "https://example.com/a",
    "topic": "BUSINESS",
    "score": 9,
    "reason": "macro",
}


class StoryLayersTest(unittest.TestCase):
    def test_summarize_story_layers_success(self) -> None:
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        fact = {
            "headline_hint": "Rate pause",
            "event": "Inflation eased.",
            "cause": "Expectations shifted.",
            "impact": "Markets repriced policy.",
            "watch_next": "Watch the Fed.",
            "one_liner_hint": "Inflation eased and rate expectations moved.",
            "entities": ["Fed"],
            "tone_flags": ["macro"],
        }
        translated = {
            "headline": "금리 동결 기조가 이어졌습니다",
            "what_happened": "미국 물가 지표가 둔화했습니다.",
            "why_important": "금리 기대 경로를 바꿀 수 있습니다.",
            "watch_next": "연준 발언과 국채 금리를 보세요.",
            "one_liner": "물가 둔화가 금리 기대를 바꾸고 있습니다.",
        }
        with patch("mvp_pipeline.summarize_story_fact_llm", return_value=(fact, "fact-raw")):
            with patch(
                "mvp_pipeline.translate_story_fact_llm",
                return_value=(translated, "translated-raw"),
            ):
                with patch("mvp_pipeline.polish_story_llm") as polish:
                    story, debug = summarize_story_layers(ARTICLE, now)
        polish.assert_not_called()
        self.assertEqual(story["source_name"], "Reuters")
        self.assertIn("fact", debug)
        self.assertIn("translated", debug)

    def test_visual_tags_survive_the_translate_schema(self) -> None:
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        fact = {
            "headline_hint": "Rate pause",
            "event": "Inflation eased.",
            "cause": "Expectations shifted.",
            "impact": "Markets repriced policy.",
            "watch_next": "Watch the Fed.",
            "one_liner_hint": "Inflation eased and rate expectations moved.",
            "entities": ["Fed"],
            "tone_flags": ["macro"],
            "visual_tags": ["central-bank", "moon-rocket"],
        }
        translated = {
            "headline": "금리 동결 기조가 이어졌습니다",
            "what_happened": "미국 물가 지표가 둔화했습니다.",
            "why_important": "금리 기대 경로를 바꿀 수 있습니다.",
            "watch_next": "연준 발언과 국채 금리를 보세요.",
            "one_liner": "물가 둔화가 금리 기대를 바꾸고 있습니다.",
        }
        with patch("mvp_pipeline.summarize_story_fact_llm", return_value=(fact, "fact-raw")):
            with patch(
                "mvp_pipeline.translate_story_fact_llm",
                return_value=(translated, "translated-raw"),
            ):
                story, debug = summarize_story_layers(ARTICLE, now)
        self.assertEqual(["central-bank"], story["visual_tags"])
        self.assertEqual(["moon-rocket"], debug["visual_tags"]["rejected"])

    def test_summarize_story_layers_polish_repair(self) -> None:
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        fact = {
            "headline_hint": "Rate pause",
            "event": "Inflation eased.",
            "cause": "Expectations shifted.",
            "impact": "Markets repriced policy.",
            "watch_next": "Watch the Fed.",
            "one_liner_hint": "Inflation eased and rate expectations moved.",
            "entities": ["Fed"],
            "tone_flags": ["macro"],
        }
        bad_translated = {
            "headline": "中国市场新闻",
            "what_happened": "中国市场今天上涨。",
            "why_important": "这会影响投资者情绪。",
            "watch_next": "关注后续数据。",
            "one_liner": "中国市场今天上涨。",
        }
        repaired = {
            "headline": "금리 동결 기조가 이어졌습니다",
            "what_happened": "미국 물가 지표가 둔화했습니다.",
            "why_important": "금리 기대 경로를 바꿀 수 있습니다.",
            "watch_next": "연준 발언과 국채 금리를 보세요.",
            "one_liner": "물가 둔화가 금리 기대를 바꾸고 있습니다.",
            "source_name": "Reuters",
            "source_url": "https://example.com/a",
        }
        with patch.dict(os.environ, {"TARGET_LANGUAGE": "ko"}, clear=False):
            with patch("mvp_pipeline.summarize_story_fact_llm", return_value=(fact, "fact-raw")):
                with patch(
                    "mvp_pipeline.translate_story_fact_llm",
                    return_value=(bad_translated | {"source_name": "Reuters", "source_url": "https://example.com/a"}, "translated-raw"),
                ):
                    with patch(
                        "mvp_pipeline.polish_story_llm",
                        return_value=(repaired, "polish-raw"),
                    ) as polish:
                        story, debug = summarize_story_layers(ARTICLE, now)
        polish.assert_called_once()
        self.assertEqual(story["headline"], repaired["headline"])
        self.assertIn("final", debug)

    def test_build_briefing_writes_story_raw_and_fallbacks(self) -> None:
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        article2 = dict(ARTICLE, id="bbbbbbbb", title="기사 2", link="https://example.com/b")
        story = {
            "headline": "금리 동결 기조가 이어졌습니다",
            "what_happened": "미국 물가 지표가 둔화했습니다.",
            "why_important": "금리 기대 경로를 바꿀 수 있습니다.",
            "watch_next": "연준 발언과 국채 금리를 보세요.",
            "one_liner": "물가 둔화가 금리 기대를 바꾸고 있습니다.",
            "source_name": "Reuters",
            "source_url": "https://example.com/a",
        }

        def fake_layers(article, _now):  # noqa: ANN001
            if article["id"] == "aaaaaaaa":
                return story, {"id": article["id"], "final": story}
            raise RuntimeError("layer failed")

        with patch.dict(os.environ, {"BRIEFING_MODE": "llm", "ALLOW_BRIEFING_FALLBACK": "1"}):
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                with patch("mvp_pipeline.summarize_story_layers", side_effect=fake_layers):
                    briefing, mode = build_briefing([ARTICLE, article2], now, run_dir=run_dir)
                raw = json.loads((run_dir / "story_raw.json").read_text(encoding="utf-8"))
        self.assertEqual(mode, "mixed")
        self.assertEqual(briefing["stories"][1]["source_url"], "https://example.com/b")
        self.assertEqual(raw[1]["fallback"], "heuristic")
        self.assertEqual(raw[1]["error"], "layer failed")

    def test_summarize_story_layers_preserves_debug_on_failure(self) -> None:
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        fact = {
            "headline_hint": "Rate pause",
            "event": "Inflation eased.",
            "cause": "Expectations shifted.",
            "impact": "Markets repriced policy.",
            "watch_next": "Watch the Fed.",
            "one_liner_hint": "Inflation eased and rate expectations moved.",
            "entities": ["Fed"],
            "tone_flags": ["macro"],
        }
        bad = {
            "headline": "中国市场新闻",
            "what_happened": "中国市场今天上涨。",
            "why_important": "这会影响投资者情绪。",
            "watch_next": "关注后续数据。",
            "one_liner": "中国市场今天上涨。",
            "source_name": "Reuters",
            "source_url": "https://example.com/a",
        }
        with patch.dict(
            os.environ,
            {"TARGET_LANGUAGE": "ko", "BRIEFING_MODE": "llm", "ALLOW_BRIEFING_FALLBACK": "1"},
            clear=False,
        ):
            with patch("mvp_pipeline.summarize_story_fact_llm", return_value=(fact, "fact-raw")):
                with patch(
                    "mvp_pipeline.translate_story_fact_llm",
                    return_value=(bad, "translated-raw"),
                ):
                    with patch(
                        "mvp_pipeline.polish_story_llm",
                        return_value=(bad, "polish-raw"),
                    ):
                        with tempfile.TemporaryDirectory() as tmp:
                            run_dir = Path(tmp)
                            briefing, mode = build_briefing([ARTICLE], now, run_dir=run_dir)
                            raw = json.loads(
                                (run_dir / "story_raw.json").read_text(encoding="utf-8")
                            )
        self.assertEqual(mode, "heuristic")
        self.assertEqual(len(briefing["stories"]), 1)
        self.assertEqual(raw[0]["fallback"], "heuristic")
        self.assertIn("fact", raw[0])
        self.assertIn("translated", raw[0])
        self.assertIn("polished", raw[0])
        self.assertIn("final_issues", raw[0])
        self.assertIn("error", raw[0])


if __name__ == "__main__":
    unittest.main()
