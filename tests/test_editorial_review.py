"""Tests for deterministic quality gate + fixture-based reviewer."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from editorial.editor import editor_decide  # noqa: E402
from editorial.loop import run_editorial_loop  # noqa: E402
from editorial.reviewer import review_story  # noqa: E402
from editorial.validator import quality_gate_story  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "review"


class QualityGateTest(unittest.TestCase):
    def test_detects_heuristic_fallback_phrase(self) -> None:
        issues = quality_gate_story(
            {
                "headline": "이슈",
                "what_happened": "이슈가 있었습니다.",
                "why_important": "시장·정책 흐름에 영향을 줄 수 있는 이슈입니다.",
                "watch_next": "후속 보도와 시장 반응을 지켜볼 필요가 있습니다.",
                "one_liner": "이슈 요약입니다.",
                "source_url": "https://example.com/a",
                "_fallback": "heuristic",
            }
        )
        self.assertTrue(any("fallback" in i for i in issues), issues)

    def test_detects_shallow_why(self) -> None:
        issues = quality_gate_story(
            {
                "headline": "추경 논의",
                "what_happened": "국회에서 추경 이야기가 나왔습니다.",
                "why_important": "예산 이슈입니다.",
                "watch_next": "추이를 봅니다.",
                "one_liner": "추경 이야기가 다시 나왔습니다.",
                "source_url": "https://example.com/b",
            }
        )
        self.assertIn("why_important:too_shallow", issues)


class ReviewerFixtureTest(unittest.TestCase):
    def test_fixtures_match_expected_decision(self) -> None:
        self.assertTrue(FIXTURES.is_dir(), FIXTURES)
        for path in sorted(FIXTURES.glob("*.json")):
            with self.subTest(path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                review = review_story(
                    data["story"],
                    sources=data.get("sources") or [],
                    use_llm=False,
                )
                self.assertEqual(
                    review.get("decision"),
                    data.get("expect_decision"),
                    msg=f"{path.name}: {review}",
                )


class EditorLoopTest(unittest.TestCase):
    def test_editor_rejects_below_minimum(self) -> None:
        briefing = {
            "stories": [
                {
                    "headline": "원·달러 환율 하루 만에 10원 하락",
                    "what_happened": "서울 외환시장에서 원·달러 환율이 전일 대비 10원 가까이 떨어졌습니다.",
                    "why_important": "환율 하락은 수입 물가와 수출 기업 채산성에 동시에 영향을 줍니다.",
                    "watch_next": "미국 고용지표 발표와 당국의 구두 개입 여부를 확인해야 합니다.",
                    "one_liner": "환율이 빠르게 내려 수입·수출 셈법이 바뀌고 있습니다.",
                    "source_url": "https://example.com/1",
                }
            ]
        }
        decision = editor_decide(
            briefing=briefing,
            validation={"ok": True, "hard_fail_indices": []},
            review={"overall": "pass", "stories": [{"index": 0, "decision": "pass"}]},
        )
        self.assertEqual(decision["decision"], "reject")
        self.assertIn("minimum_story_count", decision["reason"])

    def test_loop_stops_without_rewrite(self) -> None:
        bad = {
            "stories": [
                {
                    "headline": "A",
                    "what_happened": "A",
                    "why_important": "짧음",
                    "watch_next": "짧음",
                    "one_liner": "A 요약",
                    "source_url": "https://example.com/x",
                    "_fallback": "heuristic",
                }
            ]
            * 3
        }
        # expand to 3 distinct shallow stories
        bad["stories"] = [
            {
                "headline": f"이슈 {i}",
                "what_happened": f"이슈 {i}가 있었습니다.",
                "why_important": "짧음",
                "watch_next": "짧음",
                "one_liner": f"이슈 {i} 요약입니다.",
                "source_url": f"https://example.com/{i}",
                "_fallback": "heuristic",
            }
            for i in range(3)
        ]
        result = run_editorial_loop(bad, rewrite_story=None, use_llm_reviewer=False)
        self.assertGreaterEqual(result["revision_count"], 0)
        self.assertEqual(result["editor_decision"]["decision"], "reject")


if __name__ == "__main__":
    unittest.main()
