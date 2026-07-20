"""Tests for blog markdown assembly (v1/v2 briefing JSON)."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mvp_pipeline import (  # noqa: E402
    assemble_blog_markdown,
    build_briefing_heuristic,
)

BRIEFING_V2 = {
    "title": "금리, 반도체, AI | 오늘의 경제 브리핑 (2026-07-20)",
    "intro": "오늘 아침 경제 이슈를 정리했습니다.",
    "core_summary": ["한은 금리 인상", "반도체 수요 확대", "AI 경쟁 심화"],
    "stories": [
        {
            "headline": "한국은행 기준금리 인상",
            "what_happened": "한국은행이 기준금리를 인상했습니다.",
            "why_important": "내수와 대출 부담에 영향을 줄 수 있습니다.",
            "watch_next": "8월 추가 인상 여부를 주목해야 합니다.",
            "one_liner": "금리 인상 국면 진입",
            "source_name": "연합뉴스",
            "source_url": "https://example.com/1",
        }
    ],
    "market_impact": {
        "positive": ["금융주 수익성 개선 기대"],
        "neutral": ["환율 변동성 확대"],
        "negative": ["대출 부담 증가"],
    },
    "insight": "금리와 반도체, AI 이슈가 동시에 시장 변수로 작용합니다.",
    "upcoming_events": [
        {"date": "7월 21일", "title": "금융위 회의", "description": "정책 논의"}
    ],
    "closing_remark": "내일 아침에도 핵심 흐름을 전해드리겠습니다.",
    "related_keywords": ["금리", "반도체", "AI", "증시", "브리핑"],
    "blog_tags": ["경제", "브리핑"],
}

BRIEFING_V1 = {
    "title": "오늘의 경제 브리핑 (2026-07-20)",
    "intro": "도입부입니다.",
    "market_one_liner": "시장 한 줄 요약",
    "stories": [
        {
            "headline": "이슈 제목",
            "summary": "v1 요약 본문",
            "why_it_matters": "v1 중요 이유",
            "source_name": "매체",
            "source_url": "https://example.com/v1",
        }
    ],
    "today_points": ["포인트 1", "포인트 2"],
    "blog_tags": ["경제"],
}


class AssembleBlogMarkdownTest(unittest.TestCase):
    def test_v2_sections_present(self) -> None:
        md = assemble_blog_markdown(BRIEFING_V2)
        self.assertIn("## 📌 오늘의 핵심 요약", md)
        self.assertIn("### 무슨 일이 있었나?", md)
        self.assertIn("### 왜 중요한가?", md)
        self.assertIn("### 앞으로 주목할 점", md)
        self.assertIn("### 한 줄 요약", md)
        self.assertIn("## 📈 오늘의 시장·산업 영향", md)
        self.assertIn("## 🔍 오늘의 인사이트", md)
        self.assertIn("## 📅 앞으로 주목할 일정", md)
        self.assertIn("## ✨ 오늘의 한마디", md)
        self.assertIn("### 관련 키워드", md)
        self.assertIn("투자 또는 의사결정을 위한 전문적인 조언이 아닙니다", md)

    def test_v1_backward_compat(self) -> None:
        md = assemble_blog_markdown(BRIEFING_V1)
        self.assertIn("v1 요약 본문", md)
        self.assertIn("v1 중요 이유", md)
        self.assertIn("포인트 1", md)
        self.assertIn("### 무슨 일이 있었나?", md)

    def test_heuristic_fallback_hides_internal_meta(self) -> None:
        articles = [
            {
                "title": "테스트 뉴스",
                "snippet": "스니펫 내용입니다.",
                "source": "테스트매체",
                "link": "https://example.com/t",
                "reason": "heuristic / watchlist:금리",
            }
        ]
        briefing = build_briefing_heuristic(
            articles, datetime(2026, 7, 20, tzinfo=timezone.utc)
        )
        md = assemble_blog_markdown(briefing)
        self.assertNotIn("heuristic", md.lower())
        self.assertNotIn("watchlist:", md.lower())
        self.assertIn("| 오늘의 경제 브리핑 (2026-07-20)", md)


if __name__ == "__main__":
    unittest.main()
