"""Tests for blog markdown assembly (v1/v2 briefing JSON)."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mvp_pipeline import (  # noqa: E402
    _clean_rss_snippet,
    _safe_source_url,
    assemble_blog_markdown,
    build_briefing_heuristic,
    preview_text,
)

BRIEFING_V2 = {
    "title": "금리·반도체·AI가 동시에 흔든 하루 | 오늘의 경제 브리핑 (2026-07-20)",
    "intro": "오늘 아침 경제 이슈를 정리했습니다.",
    "core_summary": ["한은 금리 인상", "반도체 수요 확대", "AI 경쟁 심화"],
    "stories": [
        {
            "headline": "한국은행 기준금리 인상",
            "what_happened": "한국은행이 기준금리를 인상했습니다.",
            "why_important": "내수와 대출 부담에 영향을 줄 수 있습니다.",
            "watch_next": "8월 추가 인상 여부를 주목해야 합니다.",
            "one_liner": "금리 인상이 시장 변수로 부상했습니다.",
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
        self.assertIn("### 📰 무슨 일이 있었나?", md)
        self.assertIn("### 💡 왜 중요한가?", md)
        self.assertIn("### 🔭 앞으로 주목할 점", md)
        self.assertIn("### ✍️ 한 줄 요약", md)
        self.assertIn("- 한국은행이 기준금리를 인상했습니다.", md)
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
        self.assertIn("### 📰 무슨 일이 있었나?", md)

    def test_heuristic_fallback_hides_internal_meta(self) -> None:
        articles = [
            {
                "title": "테스트 뉴스",
                "snippet": "스니펫 내용입니다.  Google 뉴스에서 헤드라인 및 의견 더보기",
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
        self.assertNotIn("Google 뉴스에서", md)
        self.assertIn("오늘 주요 경제·시장 이슈를 정리합니다 | 오늘의 경제 브리핑 (2026-07-20)", md)
        self.assertTrue(briefing["stories"][0]["one_liner"].endswith("점검합니다."))
        self.assertNotEqual(briefing["stories"][0]["one_liner"], articles[0]["title"][:20])

    def test_heuristic_title_not_joined_headlines(self) -> None:
        articles = [
            {"title": f"아주 긴 기사 제목 알파 {i}", "snippet": f"본문 {i}", "source": "s", "link": f"https://ex.com/{i}"}
            for i in range(3)
        ]
        briefing = build_briefing_heuristic(
            articles, datetime(2026, 7, 21, tzinfo=timezone.utc)
        )
        self.assertNotIn("아주 긴 기사 제목 알파 0, 아주 긴 기사 제목 알파 1", briefing["title"])
        self.assertTrue(briefing["title"].startswith("오늘 주요 경제·시장 이슈를 정리합니다 |"))

    def test_heuristic_what_happened_avoids_long_cluster(self) -> None:
        articles = [
            {
                "title": "짧은 제목",
                "snippet": (
                    "짧은 제목 매체A 관련기사1 매체B 관련기사2 매체C "
                    + ("추가내용 " * 40)
                ),
                "source": "매체A",
                "link": "https://example.com/c",
            }
        ]
        briefing = build_briefing_heuristic(
            articles, datetime(2026, 7, 21, tzinfo=timezone.utc)
        )
        self.assertEqual(briefing["stories"][0]["what_happened"], "짧은 제목")
        md = assemble_blog_markdown(briefing)
        self.assertIn("- 짧은 제목", md)
        self.assertNotIn("관련기사2", md)

    def test_clean_rss_snippet_strips_google_noise(self) -> None:
        raw = "첫 문장입니다.  Google 뉴스에서 헤드라인 및 의견 더보기"
        self.assertEqual(_clean_rss_snippet(raw), "첫 문장입니다.")

    def test_preview_shows_generation_mode(self) -> None:
        preview = preview_text(BRIEFING_V2, [], generation_mode="heuristic")
        self.assertIn("생성: heuristic", preview)
        self.assertNotIn("생성: heuristic", assemble_blog_markdown(BRIEFING_V2))

    def test_source_url_allows_only_http_and_https(self) -> None:
        self.assertEqual(_safe_source_url("https://example.com"), "https://example.com")
        self.assertEqual(_safe_source_url("http://example.com"), "http://example.com")
        self.assertEqual(_safe_source_url("javascript:alert(1)"), "#")
        self.assertEqual(_safe_source_url("data:text/html,1"), "#")

    def test_markdown_source_url_falls_back_to_hash(self) -> None:
        briefing = {
            **BRIEFING_V2,
            "stories": [
                {
                    **BRIEFING_V2["stories"][0],
                    "source_url": "javascript:alert(1)",
                }
            ],
        }
        md = assemble_blog_markdown(briefing)
        self.assertIn("출처: [연합뉴스](#)", md)


if __name__ == "__main__":
    unittest.main()
