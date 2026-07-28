"""Tests for target-language story validation and deterministic repair."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from story_quality import (  # noqa: E402
    deterministic_story_repair,
    issues_summary,
    normalize_story_fields,
    story_length_limits,
    target_language,
    target_locale,
    validate_story_fields,
)


class StoryQualityTest(unittest.TestCase):
    def test_target_language_defaults_to_korean(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TARGET_LANGUAGE", None)
            os.environ.pop("TARGET_LOCALE", None)
            self.assertEqual(target_language(), "ko")
            self.assertEqual(target_locale(), "ko-KR")

    def test_target_language_strips_region_subtag(self) -> None:
        with patch.dict(os.environ, {"TARGET_LANGUAGE": "ko-KR"}, clear=False):
            os.environ.pop("TARGET_LOCALE", None)
            self.assertEqual(target_language(), "ko")
            self.assertEqual(target_locale(), "ko-KR")
        with patch.dict(os.environ, {"TARGET_LANGUAGE": "zh_CN"}, clear=False):
            os.environ.pop("TARGET_LOCALE", None)
            self.assertEqual(target_language(), "zh")
            self.assertEqual(target_locale(), "zh-CN")

    def test_locale_tag_still_runs_language_validation(self) -> None:
        with patch.dict(os.environ, {"TARGET_LANGUAGE": "ko-KR"}, clear=False):
            issues = validate_story_fields(
                {
                    "headline": "中国经济新闻",
                    "what_happened": "中国市场今天上涨。",
                    "why_important": "这会影响投资者情绪。",
                    "watch_next": "关注后续数据。",
                    "one_liner": "中国市场今天上涨。",
                }
            )
        self.assertTrue(any("language:" in issue for issue in issues))

    def test_story_length_limits_ignores_invalid_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "STORY_HEADLINE_MAX_CHARS": "not-a-number",
                "STORY_ONE_LINER_MAX_CHARS": "-5",
                "STORY_WHAT_MAX_CHARS": "50",
            },
            clear=False,
        ):
            limits = story_length_limits()
        self.assertEqual(limits["headline"], 60)
        self.assertEqual(limits["one_liner"], 110)
        self.assertEqual(limits["what_happened"], 50)

    def test_normalize_story_fields_injects_source(self) -> None:
        article = {"title": "기사", "source": "소스", "link": "https://x"}
        story = normalize_story_fields(
            {
                "headline": "헤드",
                "what_happened": "무슨 일이 있었습니다.",
                "why_important": "중요합니다.",
                "watch_next": "후속을 봅니다.",
                "one_liner": "한 줄 요약입니다.",
            },
            article,
        )
        self.assertEqual(story["source_name"], "소스")
        self.assertEqual(story["source_url"], "https://x")

    def test_rejects_han_dominant_when_target_is_korean(self) -> None:
        with patch.dict(os.environ, {"TARGET_LANGUAGE": "ko"}, clear=False):
            issues = validate_story_fields(
                {
                    "headline": "中国经济新闻",
                    "what_happened": "中国市场今天上涨。",
                    "why_important": "这会影响投资者情绪。",
                    "watch_next": "关注后续数据。",
                    "one_liner": "中国市场今天上涨。",
                }
            )
        self.assertTrue(any("language:" in issue for issue in issues))

    def test_accepts_valid_korean_story(self) -> None:
        with patch.dict(os.environ, {"TARGET_LANGUAGE": "ko"}, clear=False):
            issues = validate_story_fields(
                {
                    "headline": "금리 인하 기대가 커졌습니다",
                    "what_happened": "미국 물가 지표가 둔화했습니다.",
                    "why_important": "금리 경로 기대에 영향을 줄 수 있습니다.",
                    "watch_next": "연준 발언과 국채 금리를 확인하세요.",
                    "one_liner": "물가 둔화가 금리 기대를 흔들고 있습니다.",
                }
            )
        self.assertEqual(issues, [])

    def test_detects_duplicate_fields(self) -> None:
        issues = validate_story_fields(
            {
                "headline": "같은 문장",
                "what_happened": "같은 문장",
                "why_important": "같은 문장",
                "watch_next": "같은 문장",
                "one_liner": "같은 문장",
            }
        )
        self.assertTrue(any("duplicate" in issue for issue in issues))

    def test_deterministic_repair_trims_long_fields(self) -> None:
        repaired = deterministic_story_repair(
            {
                "headline": "가" * 120,
                "what_happened": "나" * 400,
                "why_important": "다" * 400,
                "watch_next": "라" * 300,
                "one_liner": "마" * 200,
            }
        )
        self.assertLessEqual(len(repaired["headline"]), 60)
        self.assertLessEqual(len(repaired["one_liner"]), 110)

    def test_issues_summary_formats(self) -> None:
        self.assertEqual(issues_summary([]), "- none")
        self.assertIn("- a", issues_summary(["a", "b"]))


if __name__ == "__main__":
    unittest.main()
