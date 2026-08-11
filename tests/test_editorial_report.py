"""Tests for editorial markdown report rendering."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from editorial.loop import run_editorial_loop  # noqa: E402
from editorial.report import render_editorial_report, write_editorial_report  # noqa: E402


class EditorialReportTest(unittest.TestCase):
    def test_render_includes_verdict_and_per_story(self) -> None:
        result = {
            "revision_count": 1,
            "revision_history": [
                {
                    "revision": 0,
                    "validation_ok": False,
                    "review_overall": "revise",
                    "hard_fail_indices": [0],
                }
            ],
            "validation": {"ok": True, "hard_fail_indices": []},
            "review": {
                "overall": "pass",
                "stories": [
                    {
                        "index": 0,
                        "decision": "pass",
                        "reviewer": "deterministic",
                        "risk_flags": [],
                        "revision_instructions": [],
                    }
                ],
            },
            "editor_decision": {
                "decision": "publish",
                "reason": "hard_gates_pass",
                "story_count": 3,
                "excluded_story_ids": [],
                "risk_flags": [],
            },
        }
        md = render_editorial_report(result, run_id="20260811_test")
        self.assertIn("# Editorial Report — 20260811_test", md)
        self.assertIn("## Verdict", md)
        self.assertIn("**Editor decision:** `publish`", md)
        self.assertIn("## Per-story", md)
        self.assertIn("### Story 0", md)
        self.assertIn("## Revision history", md)

    def test_loop_writes_json_and_markdown(self) -> None:
        briefing = {
            "stories": [
                {
                    "headline": f"원·달러 환율 하루 만에 {i}0원 하락",
                    "what_happened": "서울 외환시장에서 원·달러 환율이 전일 대비 빠르게 떨어졌습니다.",
                    "why_important": "환율 하락은 수입 물가와 수출 기업 채산성에 동시에 영향을 줍니다.",
                    "watch_next": "미국 고용지표 발표와 당국의 구두 개입 여부를 확인해야 합니다.",
                    "one_liner": "환율이 빠르게 내려 수입·수출 셈법이 바뀌고 있습니다.",
                    "source_url": f"https://example.com/{i}",
                }
                for i in range(1, 4)
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "attempt"
            result = run_editorial_loop(
                briefing,
                rewrite_story=None,
                use_llm_reviewer=False,
                run_dir=run_dir,
            )
            self.assertTrue((run_dir / "editorial_result.json").is_file())
            report = run_dir / "editorial_report.md"
            self.assertTrue(report.is_file())
            text = report.read_text(encoding="utf-8")
            self.assertIn("## Verdict", text)
            self.assertIn(str(result["editor_decision"]["decision"]), text)
            # write_editorial_report is also callable alone
            p2 = write_editorial_report(result, run_dir, run_id="x")
            self.assertEqual(p2, report)


if __name__ == "__main__":
    unittest.main()
