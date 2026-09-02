"""Render a Korean 1080×1080 infographic next to a website post."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from cards.infographic import export_infographic
from cards.renderer import CardRenderer

from .website import (
    REPO_ROOT,
    SEOUL,
    description_of,
    display_title,
    published_at_of,
)

DEFAULT_IMAGES_DIR = REPO_ROOT / "website" / "public" / "images" / "posts"
SITE_NAME = "장전 브리핑"

WEBSITE_LABELS = {
    "kicker": "장전 브리핑",
    "lead_label": "오늘의 정리",
    "signals_label": "핵심 포인트",
    "insight_label": "한 줄",
    "impact_1_label": "긍정",
    "impact_2_label": "주시",
    "impact_3_label": "부담",
    "impact_4_label": "다음",
}

WEBSITE_CSS_VARS = {
    "color-primary": "#006241",
    "color-accent": "#00754a",
    "color-bg": "#f2f0eb",
    "color-soft": "#e7eee9",
}


def graphic_relpath(slug: str) -> str:
    return f"/images/posts/{slug}-infographic.png"


def briefing_for_graphic(briefing: dict[str, Any]) -> dict[str, Any]:
    """Notes without stories still get one signal slot from the title."""
    payload = dict(briefing)
    stories = [row for row in (payload.get("stories") or []) if isinstance(row, dict)]
    if stories:
        payload["stories"] = stories
        return payload
    payload["stories"] = [
        {
            "headline": display_title(payload),
            "one_liner": description_of(payload),
            "what_happened": description_of(payload),
        }
    ]
    if not str(payload.get("intro") or "").strip():
        payload["intro"] = description_of(payload)
    return payload


def write_site_infographic(
    briefing: dict[str, Any],
    slug: str,
    images_dir: Path | None = None,
    *,
    now: datetime | None = None,
    renderer: CardRenderer | None = None,
    source_png: Path | None = None,
) -> str | None:
    """Write ``{slug}-infographic.png``. Return the public path, or None on skip.

    ``source_png`` copies an already-approved render instead of drawing again.
    """
    dest_dir = Path(images_dir) if images_dir else DEFAULT_IMAGES_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{slug}-infographic.png"
    if source_png is not None and Path(source_png).is_file():
        shutil.copyfile(source_png, target)
        return graphic_relpath(slug)
    when = published_at_of(briefing, now).astimezone(SEOUL)
    date = f"{when.month}월 {when.day}일"
    work = dest_dir / f".{slug}-infographic-work"
    result = export_infographic(
        briefing_for_graphic(briefing),
        work,
        brand=SITE_NAME,
        date=date,
        renderer=renderer,
        labels=WEBSITE_LABELS,
        css_vars=WEBSITE_CSS_VARS,
    )
    png = result.get("png")
    if not png or result.get("error"):
        shutil.rmtree(work, ignore_errors=True)
        return None
    shutil.copyfile(png, target)
    shutil.rmtree(work, ignore_errors=True)
    return graphic_relpath(slug)


FIXTURE_BRIEFINGS: list[dict[str, Any]] = [
    {
        "slug": "2026-08-24-오늘-주요-경제-시장-이슈를-정리합니다",
        "title": "오늘 주요 경제·시장 이슈를 정리합니다 | 오늘의 경제 브리핑 (2026-08-24)",
        "intro": "오늘 아침 경제·시장에서 주목할 이슈를 정리했습니다. 각 이슈의 배경과 앞으로 확인할 점을 함께 살펴봅니다.",
        "insight": "오늘 소개한 이슈들은 경제·시장 흐름을 이해하는 데 서로 연결된 맥락을 갖고 있습니다.",
        "published_at": "2026-08-24T07:00:00+09:00",
        "stories": [
            {
                "headline": "삼성전자 주주환원 전략과 AI 반도체 계획",
                "one_liner": "삼성전자는 주주환원 전략을 AI 반도체 개발로 확대하고 있습니다.",
                "what_happened": "삼성전자는 주주환원 전략을 이어가며 AI 반도체 개발에 대한 계획을 밝혔습니다.",
            },
            {
                "headline": "고가 기업 주택 임대율, 주요 주주 가족이 42%로 집계",
                "one_liner": "고가 기업 주택의 42%가 주요 주주의 가족이 차지하고 있어 윤리적 우려가 제기된다.",
            },
            {
                "headline": "연준 비관적 관리자, 금융시장 안정성 강조",
                "one_liner": "연준 비관적 관리자의 말과 달리 국채 수익률이 상승, 투자자들의 관심 필요",
            },
        ],
        "market_impact": {
            "positive": ["주요 이슈가 시장 관심을 높이고 있습니다."],
            "neutral": ["단기 변동성은 지속될 수 있습니다."],
            "negative": ["불확실성이 남아 있어 주의가 필요합니다."],
        },
        "upcoming_events": [{"title": "주요 경제 지표·기업 실적 발표"}],
        "blog_tags": ["경제", "브리핑", "뉴스"],
    },
    {
        "slug": "2026-08-27-semiconductor-fx",
        "title": "반도체와 환율이 동시에 열린 하루",
        "intro": "수출 업종은 실적 기대를 다시 반영하고, 환율은 수입 물가와 수급 이야기를 같이 연다.",
        "insight": "반도체가 상단을 받치고, 환율이 하단 해석을 흔든다.",
        "published_at": "2026-08-27T07:00:00+09:00",
        "stories": [
            {
                "headline": "반도체 실적 기대가 다시 열렸다",
                "one_liner": "해외 흐름과 실적 코멘트가 겹쳤다.",
                "what_happened": "수출 업종이 위험선호를 되돌렸다.",
            },
            {
                "headline": "원·달러는 방향이 닫히지 않았다",
                "one_liner": "수입 민감 업종의 해석 폭이 넓어졌다.",
            },
        ],
        "market_impact": {
            "positive": ["수출 업종 실적 기대"],
            "neutral": ["환율 변동성 확대"],
            "negative": ["수입 물가 부담"],
        },
        "upcoming_events": [{"title": "실적 가이던스와 환율 변동성"}],
    },
    {
        "slug": "2026-08-27-real-estate-gap",
        "title": "부동산 대기 수요와 거래 공백",
        "intro": "정책 공백기에는 가격보다 거래량과 대기 기간을 먼저 본다.",
        "insight": "거래 공백은 방향이 아니라 속도의 문제인 경우가 많다.",
        "published_at": "2026-08-27T07:30:00+09:00",
        "stories": [
            {
                "headline": "거래 건수는 얇게 유지됐다",
                "one_liner": "희망 가격과 체결가 사이 간격이 넓다.",
            },
            {
                "headline": "관망이 기본값이 됐다",
                "one_liner": "대기 수요가 사라진 것은 아니다.",
            },
        ],
        "market_impact": {
            "positive": ["대기 수요는 남아 있다"],
            "neutral": ["거래량 공백이 이어진다"],
            "negative": ["체결까지 시간이 길다"],
        },
        "upcoming_events": [{"title": "정책 일정이 다시 열리는지"}],
    },
    {
        "slug": "2026-08-26-rate-pause",
        "title": "금리는 쉬고, 해석은 쉬지 않았다",
        "intro": "동결 자체보다 메시지 온도가 시장 해석을 갈랐다.",
        "insight": "다음 달력보다 표현의 온도를 먼저 본다.",
        "published_at": "2026-08-26T07:00:00+09:00",
        "stories": [
            {
                "headline": "기준금리는 유지됐다",
                "one_liner": "쉬는 결정처럼 보여도 신호는 남는다.",
            },
            {
                "headline": "물가와 성장의 무게가 고르게 읽혔다",
                "one_liner": "경로를 한 방향으로 단정하지 않는다.",
            },
        ],
        "market_impact": {
            "positive": ["급한 인상 압력은 줄었다"],
            "neutral": ["다음 회의 표현을 본다"],
            "negative": ["대출·환율 고리는 남는다"],
        },
        "upcoming_events": [{"title": "다음 성명과 기자회견 온도"}],
    },
    {
        "slug": "2026-08-27-transit-strike",
        "title": "지하철 파업 예고, 출근길만 먼저 보면 된다",
        "intro": "노사 협상이 결렬된 뒤 내달 초 부분 파업이 예고됐다.",
        "insight": "전면 중단이 아니라 노선과 시간대가 핵심이다.",
        "published_at": "2026-08-27T15:10:00+09:00",
        "kind": "note",
        "stories": [
            {
                "headline": "부분 파업이 예고됐다",
                "one_liner": "출근 피크 구간을 먼저 보면 된다.",
            }
        ],
    },
]


def render_fixture_infographics(
    images_dir: Path | None = None,
    *,
    renderer: CardRenderer | None = None,
) -> list[str]:
    written: list[str] = []
    for row in FIXTURE_BRIEFINGS:
        slug = str(row["slug"])
        path = write_site_infographic(row, slug, images_dir, renderer=renderer)
        if path:
            written.append(path)
    return written


if __name__ == "__main__":
    paths = render_fixture_infographics()
    for path in paths:
        print(path)
    if not paths:
        raise SystemExit("infographic PNG render failed")
