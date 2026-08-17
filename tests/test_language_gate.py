"""Tests for Korean language hard gate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from editorial.editor import editor_decide  # noqa: E402
from editorial.validator import quality_gate_briefing  # noqa: E402
from story_quality import assess_korean_text, language_hard_fail_issues  # noqa: E402


def _ko_story(**overrides: str) -> dict:
    base = {
        "headline": "금리 인하 기대가 커졌습니다",
        "what_happened": "미국 물가 지표가 둔화했습니다.",
        "why_important": "금리 경로 기대에 영향을 줄 수 있습니다.",
        "watch_next": "연준 발언과 국채 금리를 확인하세요.",
        "one_liner": "물가 둔화가 금리 기대를 흔들고 있습니다.",
        "source_url": "https://example.com/1",
    }
    base.update(overrides)
    return base


class LanguageGateTest(unittest.TestCase):
    def test_valid_korean_passes(self) -> None:
        verdict, _ = assess_korean_text("미국 물가 지표가 둔화했습니다.")
        self.assertEqual(verdict, "pass")

    def test_english_company_name_warn_or_pass(self) -> None:
        verdict, _ = assess_korean_text("Apple 실적 발표가 시장에 영향을 줬습니다.")
        self.assertIn(verdict, {"pass", "warn"})

    def test_chinese_text_hard_fails(self) -> None:
        verdict, signals = assess_korean_text("中国市场今天上涨。")
        self.assertEqual(verdict, "hard_fail")
        self.assertTrue(signals)

    def test_mixed_headline_ko_body_cn_hard_fails(self) -> None:
        story = _ko_story(
            headline="금리 인하 기대",
            what_happened="中国市场今天上涨。",
        )
        issues = language_hard_fail_issues(story)
        self.assertTrue(any("what_happened:language:hard_fail" in i for i in issues))

    def test_small_han_in_company_name_not_hard_fail(self) -> None:
        story = _ko_story(headline="阿里巴巴 실적이 커졌습니다")
        issues = language_hard_fail_issues(story)
        self.assertFalse(issues)

    def test_validator_marks_language_hard_fail(self) -> None:
        briefing = {
            "stories": [
                _ko_story(what_happened="中国市场今天上涨。"),
                _ko_story(headline="두 번째", source_url="https://example.com/2"),
                _ko_story(headline="세 번째", source_url="https://example.com/3"),
            ]
        }
        result = quality_gate_briefing(briefing)
        self.assertIn(0, result["hard_fail_indices"])

    def test_editor_partial_reject_publish(self) -> None:
        stories = [
            _ko_story(),
            _ko_story(headline="두", source_url="https://example.com/2"),
            _ko_story(headline="세", source_url="https://example.com/3"),
        ]
        with patch.dict("os.environ", {"QUALITY_MINIMUM_STORY_COUNT": "2"}, clear=False):
            decision = editor_decide(
                briefing={"stories": stories},
                validation={"ok": True, "hard_fail_indices": []},
                review={
                    "overall": "reject",
                    "stories": [
                        {"index": 0, "decision": "reject", "risk_flags": ["bad"]},
                        {"index": 1, "decision": "pass"},
                        {"index": 2, "decision": "pass"},
                    ],
                },
            )
        self.assertEqual(decision["decision"], "publish")
        self.assertEqual(decision["story_count"], 2)
        self.assertEqual(decision["excluded_story_ids"], [0])

    def test_editor_two_rejects_below_min(self) -> None:
        stories = [
            _ko_story(),
            _ko_story(headline="두", source_url="https://example.com/2"),
            _ko_story(headline="세", source_url="https://example.com/3"),
        ]
        with patch.dict("os.environ", {"QUALITY_MINIMUM_STORY_COUNT": "2"}, clear=False):
            decision = editor_decide(
                briefing={"stories": stories},
                validation={"ok": True, "hard_fail_indices": []},
                review={
                    "overall": "reject",
                    "stories": [
                        {"index": 0, "decision": "reject"},
                        {"index": 1, "decision": "reject"},
                        {"index": 2, "decision": "pass"},
                    ],
                },
            )
        self.assertEqual(decision["decision"], "reject")


if __name__ == "__main__":
    unittest.main()
