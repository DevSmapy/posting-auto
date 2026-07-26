"""Sample stories for local card-news MVP preview."""

from __future__ import annotations

from typing import Any


def sample_stories() -> list[dict[str, Any]]:
    """Three fixture stories → 5-slide carousel (cover + 3 + disclaimer)."""
    return [
        {
            "headline": "한은, 기준금리 동결 속 신중 기조",
            "what_happened": (
                "한국은행이 기준금리를 동결했습니다. "
                "물가와 성장 사이의 균형을 강조했습니다."
            ),
            "why_important": "대출 금리와 원화 흐름에 영향을 줄 수 있습니다.",
            "watch_next": "다음 금통위와 물가 지표를 함께 봐야 합니다.",
            "one_liner": "금리 동결 속에서도 신중론이 이어지고 있습니다.",
            "source_name": "예시뉴스",
            "source_url": "https://example.com/rate",
        },
        {
            "headline": "반도체 수출, 회복 신호 확대",
            "what_happened": (
                "반도체 수출이 전월 대비 개선됐습니다. "
                "AI 관련 수요가 배경으로 꼽힙니다."
            ),
            "why_important": "수출 경기와 코스피 업종 흐름의 핵심 변수입니다.",
            "watch_next": "재고와 단가 추이를 확인하세요.",
            "one_liner": "반도체 수출에서 회복 신호가 뚜렷해졌습니다.",
            "source_name": "예시뉴스",
            "source_url": "https://example.com/semi",
        },
        {
            "headline": "원·달러 환율, 변동성 확대",
            "what_happened": (
                "원·달러 환율이 장중 변동폭을 키웠습니다. "
                "대외 금리와 수급이 동시에 작용했습니다."
            ),
            "why_important": "수입 물가와 기업 실적 전망에 영향을 줍니다.",
            "watch_next": "해외 금리 발표와 수급 동향을 지켜보세요.",
            "one_liner": "환율 변동성이 다시 시장 변수로 떠올랐습니다.",
            "source_name": "예시뉴스",
            "source_url": "https://example.com/fx",
        },
    ]


def sample_related_keywords() -> list[str]:
    return ["금리", "반도체", "환율", "증시", "브리핑"]
