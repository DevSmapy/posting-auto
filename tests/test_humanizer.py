"""Tests for the conditional Korean post-edit and its fidelity gate."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from editorial.humanizer import (  # noqa: E402
    MAX_CHANGE_RATE,
    bigram_change_rate,
    diagnose_story,
    fidelity_issues,
    gate_rewrite,
    humanize_stories,
    rule_ids,
)

CLEAN = {
    "headline": "한국은행이 기준금리를 동결했습니다",
    "what_happened": "한국은행 금융통화위원회가 기준금리를 3.50%로 유지했습니다.",
    "why_important": "대출 이자 부담과 환율 흐름이 함께 걸린 결정입니다.",
    "watch_next": "다음 금통위에서 소수의견이 나오는지 보세요.",
    "one_liner": "금리는 묶였지만 물가 경로가 여전히 변수입니다.",
    "source_name": "연합뉴스",
    "source_url": "https://example.com/a",
}


def story(**fields: str) -> dict[str, str]:
    return {**CLEAN, **fields}


class DiagnosisTest(unittest.TestCase):
    def test_clean_korean_copy_fires_no_rule(self) -> None:
        self.assertEqual([], diagnose_story(CLEAN))

    def test_every_rule_has_a_case_that_fires_it(self) -> None:
        cases = {
            "double_passive": story(why_important="영향이 크게 보여지고 있습니다."),
            "agent_by_phrase": story(why_important="금리는 시장에 의해 결정됩니다."),
            "have_translationese": story(why_important="정부는 대응 수단을 가지고 있습니다."),
            "possessive_chain": story(why_important="시장의 금리의 방향의 변화가 큽니다."),
            "about_overuse": story(
                why_important="금리에 대한 우려와 물가에 대한 부담, 환율에 대해 설명합니다."
            ),
            "plural_overuse": story(
                why_important="기업들이 투자자들의 눈치를 보며 은행들과 협의했습니다."
            ),
            "progressive_overuse": story(
                why_important="우려가 제기되고 있고 격차가 확대되고 있으며 부담이 지속되고 있습니다."
            ),
            "double_hedge": story(watch_next="금리는 내려갈 수 있을 것으로 보입니다."),
            "significance_cliche": story(why_important="이번 결정은 큰 의미를 갖습니다."),
            "closing_cliche": story(watch_next="향후 귀추가 주목됩니다."),
            "intensifier_overuse": story(
                why_important="매우 중요하고 굉장히 빠른 변화입니다."
            ),
            "repeated_connective": story(
                why_important="또한 물가가 올랐습니다.",
                watch_next="또한 환율도 흔들립니다.",
            ),
            "monotone_ending": story(
                headline="금리가 동결되었습니다",
                what_happened="물가가 상승되었습니다",
                why_important="부담이 확대되었습니다",
            ),
        }
        self.assertEqual(sorted(cases), rule_ids())
        for rule, sample in cases.items():
            self.assertIn(rule, diagnose_story(sample), rule)

    def test_markdown_structure_is_out_of_scope(self) -> None:
        # briefing.md headings/bullets live outside STORY_FIELDS, so they are never read.
        noisy = story(section="## 오늘의 이슈\n- 첫째\n- 둘째", blog_html="<h2>또한</h2>")
        self.assertEqual([], diagnose_story(noisy))


class FidelityGateTest(unittest.TestCase):
    def test_identical_text_has_zero_change_rate(self) -> None:
        self.assertEqual(0.0, bigram_change_rate("금리 동결", "금리 동결"))

    def test_change_rate_grows_with_rewriting(self) -> None:
        light = bigram_change_rate("금리를 동결했습니다", "금리를 동결했어요")
        heavy = bigram_change_rate("금리를 동결했습니다", "환율이 크게 흔들렸습니다")
        self.assertLess(light, heavy)
        self.assertLessEqual(heavy, 1.0)

    def test_changed_numbers_and_quotes_and_anchors_are_caught(self) -> None:
        self.assertIn(
            "numbers:changed",
            fidelity_issues(CLEAN, story(what_happened="기준금리를 3.75%로 유지했습니다.")),
        )
        self.assertIn(
            "source_url:changed", fidelity_issues(CLEAN, story(source_url="https://evil"))
        )
        quoted = story(what_happened='총재는 "인내가 필요하다"고 말했습니다.')
        reworded = story(what_happened='총재는 "속도가 필요하다"고 말했습니다.')
        self.assertIn("quotes:changed", fidelity_issues(quoted, reworded))

    def test_emptied_field_is_caught(self) -> None:
        self.assertIn("fields:emptied", fidelity_issues(CLEAN, story(watch_next="")))

    def test_gate_rejects_a_rewrite_past_the_change_budget(self) -> None:
        rewritten = story(
            headline="완전히 다른 문장",
            what_happened="전혀 무관한 내용을 새로 씁니다.",
            why_important="근거 없는 새 주장을 덧붙입니다.",
            watch_next="아무 관련 없는 관전 포인트입니다.",
            one_liner="원문과 겹치지 않는 요약입니다.",
        )
        ok, issues, rate = gate_rewrite(CLEAN, rewritten)
        self.assertFalse(ok)
        self.assertGreater(rate, MAX_CHANGE_RATE)
        self.assertTrue(any(i.startswith("change_rate:") for i in issues))

    def test_gate_accepts_a_light_polish(self) -> None:
        ok, issues, rate = gate_rewrite(
            CLEAN, story(why_important="대출 이자 부담과 환율 흐름이 걸린 결정입니다.")
        )
        self.assertTrue(ok, issues)
        self.assertLess(rate, MAX_CHANGE_RATE)


class OrchestrationTest(unittest.TestCase):
    def test_clean_stories_never_call_the_polish_llm(self) -> None:
        calls: list[str] = []

        def polish(story_in, issues):  # noqa: ANN001
            calls.append(story_in["headline"])
            return story_in

        out, result = humanize_stories([CLEAN], polish=polish)
        self.assertEqual([], calls)
        self.assertEqual(0, result["flagged"])
        self.assertEqual([CLEAN], out)

    def test_flagged_story_is_polished_once_and_kept(self) -> None:
        flagged = story(why_important="이번 결정은 큰 의미를 갖습니다.")
        fixed = story(why_important="이번 결정은 가계 이자 부담을 좌우합니다.")
        calls: list[list[str]] = []

        def polish(story_in, issues):  # noqa: ANN001
            calls.append(issues)
            return fixed

        out, result = humanize_stories([flagged], polish=polish)
        self.assertEqual(1, len(calls))
        self.assertIn("significance_cliche", calls[0])
        self.assertEqual(fixed["why_important"], out[0]["why_important"])
        self.assertEqual(1, result["applied"])
        self.assertEqual(0, result["rolled_back"])

    def test_drifting_rewrite_rolls_back_to_the_original(self) -> None:
        flagged = story(why_important="이번 결정은 큰 의미를 갖습니다.")

        def polish(story_in, issues):  # noqa: ANN001
            return story(
                headline="전혀 다른 제목입니다",
                what_happened="관련 없는 사실을 새로 지어냈습니다.",
                why_important="근거 없는 해석을 덧붙였습니다.",
                watch_next="엉뚱한 관전 포인트입니다.",
                one_liner="원문과 무관한 한 줄입니다.",
            )

        out, result = humanize_stories([flagged], polish=polish)
        self.assertEqual(flagged, out[0])
        self.assertEqual(1, result["rolled_back"])
        self.assertTrue(result["stories"][0]["rollback_reason"])

    def test_polish_failure_keeps_the_original_story(self) -> None:
        flagged = story(watch_next="향후 귀추가 주목됩니다.")

        def polish(story_in, issues):  # noqa: ANN001
            raise RuntimeError("ollama down")

        out, result = humanize_stories([flagged], polish=polish)
        self.assertEqual(flagged, out[0])
        self.assertEqual(["polish:failed:ollama down"], result["stories"][0]["rollback_reason"])

    def test_heuristic_mode_diagnoses_without_an_llm_call(self) -> None:
        flagged = story(watch_next="향후 귀추가 주목됩니다.")
        out, result = humanize_stories([flagged], polish=None)
        self.assertEqual(flagged, out[0])
        self.assertFalse(result["polish_enabled"])
        self.assertEqual(1, result["flagged"])
        self.assertEqual(["polish:disabled"], result["stories"][0]["rollback_reason"])

    def test_result_json_records_rules_rate_and_rollback(self) -> None:
        flagged = story(why_important="이번 결정은 큰 의미를 갖습니다.")
        fixed = story(why_important="이번 결정은 가계 이자 부담을 좌우합니다.")
        with tempfile.TemporaryDirectory() as tmp:
            _out, result = humanize_stories(
                [flagged, CLEAN], polish=lambda s, i: fixed, run_dir=Path(tmp)
            )
            saved = json.loads(
                (Path(tmp) / "humanize_result.json").read_text(encoding="utf-8")
            )
        self.assertEqual(result, saved)
        self.assertEqual(2, len(saved["stories"]))
        self.assertIn("significance_cliche", saved["stories"][0]["issues"])
        self.assertGreater(saved["stories"][0]["change_rate"], 0.0)
        self.assertEqual([], saved["stories"][1]["issues"])


class PipelineWiringTest(unittest.TestCase):
    def test_flagged_story_is_polished_with_its_own_source_article(self) -> None:
        from datetime import datetime, timezone
        from unittest.mock import patch

        import mvp_pipeline

        flagged = story(why_important="이번 결정은 큰 의미를 갖습니다.")
        articles = [
            {"link": "https://example.com/other", "source": "다른 매체"},
            {"link": "https://example.com/a", "source": "연합뉴스"},
        ]
        seen: list[dict] = []

        def fake_polish(story_in, issues, article, _now):  # noqa: ANN001
            seen.append(article)
            return story(why_important="이번 결정은 가계 이자 부담을 좌우합니다."), "raw"

        with tempfile.TemporaryDirectory() as tmp:
            with patch("mvp_pipeline.polish_story_llm", side_effect=fake_polish):
                out = mvp_pipeline.humanize_story_language(
                    [flagged], articles, datetime(2026, 8, 22, tzinfo=timezone.utc), Path(tmp)
                )
            self.assertTrue((Path(tmp) / "humanize_result.json").exists())
        self.assertEqual([articles[1]], seen)
        self.assertIn("가계 이자 부담", out[0]["why_important"])


if __name__ == "__main__":
    unittest.main()
