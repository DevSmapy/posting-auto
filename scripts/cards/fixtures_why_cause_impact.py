"""Example fill for template bundle `why_cause_impact` (economy/society news)."""

from __future__ import annotations

from typing import Any


def why_cause_impact_example() -> list[dict[str, Any]]:
    """US rate-cut → Korea tremor narrative (8 cards)."""
    return [
        {
            "role": "hook",
            "label": "Hook",
            "headline": "미국이 금리를 내렸는데\n왜 한국이 흔들릴까?",
            "body": "해외 뉴스 한 줄이\n우리 지갑까지 건드리는 이유",
        },
        {
            "role": "event",
            "label": "무슨 일?",
            "headline": "연준, 기준금리 인하",
            "body": "미국 중앙은행이 기준금리를 내렸습니다.\n글로벌 자금 흐름이 다시 움직이기 시작했습니다.",
        },
        {
            "role": "cause",
            "label": "왜?",
            "headline": "경기 둔화 우려가 커졌기 때문",
            "body": "물가는 한풀 꺾였지만\n고용·소비 지표는 힘이 빠지고 있습니다.\n그래서 ‘너무 늦기 전’ 대응에 나선 겁니다.",
        },
        {
            "role": "analysis",
            "label": "핵심",
            "headline": "금리보다 중요한 건 ‘돈의 방향’",
            "body": "금리 인하는 곧 달러 매력 변화입니다.\n돈이 어디로 흐르느냐가\n환율·주가·채권을 동시에 흔듭니다.",
        },
        {
            "role": "impact",
            "label": "영향",
            "headline": "한국에선 환율·수출·대출이 먼저",
            "body": "원·달러 환율과 외국인 수급이 출렁이고,\n수출 기업과 대출 금리 기대도 함께 움직입니다.\n결국 투자자·자영업자·직장인 모두에게 닿습니다.",
        },
        {
            "role": "outlook",
            "label": "전망",
            "headline": "두 갈래 시나리오",
            "body": "A: 연성 착륙 → 위험자산 선호 이어짐\nB: 경기 침체 심화 → 안전자산·변동성 확대\n다음 고용·물가 숫자가 갈림길입니다.",
        },
        {
            "role": "summary",
            "label": "한 줄",
            "headline": "미국 금리는 ‘남의 일’이 아닙니다",
            "body": "해외 금리 한 방이\n국내 환율·투자·생활물가 체감으로 이어집니다.",
        },
        {
            "role": "cta",
            "label": "CTA",
            "headline": "저장해 두고\n내일 숫자와 함께 보세요",
            "body": "팔로우하면 경제·사회 이슈를\n짧게 이어서 전해 드립니다.\n※ 정보 안내용이며 투자 권유가 아닙니다.",
        },
    ]


def why_cause_impact_keywords() -> list[str]:
    return ["금리", "연준", "환율", "경제뉴스", "증시"]


CAPTION_HOOK = "미국 금리 인하, 왜 한국 시장까지 흔들릴까?"
