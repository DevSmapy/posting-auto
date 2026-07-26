"""Reusable editorial Instagram carousel UI (1080×1350, placeholder-only)."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CardFormatConfig
from .models import CardBundle, InstagramPost, Slide, SlideType
from .renderer import CardRenderer

ROOT = Path(__file__).resolve().parents[2]
EDITORIAL_DIR = ROOT / "templates" / "cards" / "editorial"

SLIDE_FILES: tuple[str, ...] = (
    "01-hook.html",
    "02-what-happened.html",
    "03-background.html",
    "04-analysis.html",
    "05-impact.html",
    "06-outlook.html",
    "07-summary.html",
    "08-cta.html",
)


def placeholder_content(brand: str = "BRAND") -> dict[str, dict[str, str]]:
    """Placeholder-only copy for the 8-slide editorial system."""
    return {
        "01-hook.html": {
            "category_label": "CATEGORY LABEL",
            "headline": "헤드라인 플레이스홀더가\n들어갑니다",
            "subheadline": "호기심을 유발하는 한 줄 서브헤드라인 플레이스홀더",
            "brand": brand,
        },
        "02-what-happened.html": {
            "title": "무슨 일이\n있었나요?",
            "bullet_1": "핵심 사실 요약 플레이스홀더 첫째 줄",
            "bullet_2": "핵심 사실 요약 플레이스홀더 둘째 줄",
            "bullet_3": "핵심 사실 요약 플레이스홀더 셋째 줄",
            "brand": brand,
        },
        "03-background.html": {
            "title": "왜 이런 일이\n생겼을까요?",
            "subtitle": "배경을 설명하는 짧은 도입 플레이스홀더",
            "card_1_title": "원인 카드 제목 01",
            "card_1_body": "한 줄 설명 플레이스홀더",
            "card_2_title": "원인 카드 제목 02",
            "card_2_body": "한 줄 설명 플레이스홀더",
            "card_3_title": "원인 카드 제목 03",
            "card_3_body": "한 줄 설명 플레이스홀더",
            "brand": brand,
        },
        "04-analysis.html": {
            "title": "핵심 포인트는\n무엇인가요?",
            "key_takeaway": "하이라이트 박스에 들어갈\n핵심 인사이트 플레이스홀더",
            "key_support": "보조 설명 한 줄 플레이스홀더",
            "bullet_1": "근거 또는 세부 포인트 01",
            "bullet_2": "근거 또는 세부 포인트 02",
            "bullet_3": "근거 또는 세부 포인트 03",
            "chart_label": "STAT / TREND",
            "brand": brand,
        },
        "05-impact.html": {
            "title": "누구에게\n영향을 주나요?",
            "subtitle": "영향 대상 그룹 플레이스홀더",
            "card_1_group": "Consumers",
            "card_1_body": "소비자 영향 한 줄 플레이스홀더",
            "card_2_group": "Companies",
            "card_2_body": "기업 영향 한 줄 플레이스홀더",
            "card_3_group": "Investors",
            "card_3_body": "투자자 영향 한 줄 플레이스홀더",
            "card_4_group": "Government",
            "card_4_body": "정책·공공 영향 한 줄 플레이스홀더",
            "brand": brand,
        },
        "06-outlook.html": {
            "title": "앞으로\n무엇이 달라질까요?",
            "tl_1": "Now",
            "tl_2": "Near",
            "tl_3": "Next",
            "scenario_a_title": "시나리오 A 제목",
            "scenario_a_body": "낙관·기본 시나리오 설명 플레이스홀더",
            "scenario_b_title": "시나리오 B 제목",
            "scenario_b_body": "보수·리스크 시나리오 설명 플레이스홀더",
            "flow_1": "신호",
            "flow_2": "반응",
            "flow_3": "결과",
            "expert_expectation": "전문가 기대 / 관측 포인트 플레이스홀더",
            "brand": brand,
        },
        "07-summary.html": {
            "summary_quote": "기억에 남을\n한 문장 요약\n플레이스홀더",
            "summary_note": "짧은 보조 메모 플레이스홀더",
            "brand": brand,
        },
        "08-cta.html": {
            "logo_mark": "EB",
            "cta_title": "이 템플릿으로\n브리핑을 이어가세요",
            "cta_subtitle": "저장 · 공유 · 팔로우 플레이스홀더",
            "action_save": "Save this post",
            "action_share": "Share with friends",
            "action_follow": "Follow for more",
            "follow_button": "Follow",
            "disclaimer": "※ 정보 안내용이며 투자 권유가 아닙니다.",
            "brand": brand,
        },
    }


@dataclass(frozen=True)
class EditorialSlide:
    filename: str
    html: str
    fields: dict[str, str]


class EditorialCarouselTemplate:
    """UI/UX template pack: placeholder content, reusable components."""

    def __init__(
        self,
        brand: str = "BRAND",
        content: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.brand = brand
        self.content = content or placeholder_content(brand)
        self.css = (EDITORIAL_DIR / "design-system.css").read_text(encoding="utf-8")
        self.width = 1080
        self.height = 1350

    def render_all(self) -> list[EditorialSlide]:
        slides: list[EditorialSlide] = []
        for name in SLIDE_FILES:
            fields = dict(self.content.get(name) or {})
            fields.setdefault("brand", self.brand)
            raw = (EDITORIAL_DIR / name).read_text(encoding="utf-8")
            html_doc = raw.replace("{{DESIGN_SYSTEM_CSS}}", self.css)
            for key, value in fields.items():
                safe = "<br />".join(html.escape(p) for p in str(value).split("\n"))
                html_doc = html_doc.replace("{{" + key + "}}", safe)
            if "{{" in html_doc:
                missing = [
                    part.split("}}", 1)[0]
                    for part in html_doc.split("{{")[1:]
                ]
                raise ValueError(f"{name} missing placeholders: {missing}")
            slides.append(EditorialSlide(filename=name, html=html_doc, fields=fields))
        return slides

    def export(
        self,
        out_dir: Path,
        *,
        render_png: bool = True,
    ) -> dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        slides = self.render_all()
        config = CardFormatConfig(
            brand=self.brand,
            width=self.width,
            height=self.height,
            templates_dir=EDITORIAL_DIR,
        )
        renderer = CardRenderer(config)
        html_paths: list[Path] = []
        png_paths: list[Path] = []

        meta = {
            "template_id": "editorial_carousel",
            "canvas": {"width": self.width, "height": self.height},
            "palette": {
                "primary": "#163A70",
                "accent": "#F59E0B",
                "background": "#F7F8FA",
                "card": "#FFFFFF",
                "text": "#1F2937",
                "secondary_text": "#6B7280",
            },
            "components": [
                "Info Card",
                "Number Card",
                "Quote Card",
                "Timeline",
                "Flow Diagram",
                "Statistic Card",
                "Impact Card",
                "CTA Footer",
                "Highlight Box",
            ],
            "slides": [
                {"file": s.filename, "fields": list(s.fields.keys())} for s in slides
            ],
        }
        (out_dir / "template_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "placeholders.json").write_text(
            json.dumps(self.content, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Caption template (placeholder Instagram body)
        caption_body = (
            f"{self.brand} · DATE_PLACEHOLDER\n"
            "헤드라인 플레이스홀더\n\n"
            "오늘의 포인트\n"
            "1) 포인트 플레이스홀더 01\n"
            "2) 포인트 플레이스홀더 02\n"
            "3) 포인트 플레이스홀더 03\n\n"
            "자세한 해설은 프로필 링크·블로그 브리핑에서 이어갑니다.\n\n"
            "※ 정보 안내용이며 투자 권유가 아닙니다."
        )
        tags = "#경제뉴스 #사회뉴스 #브리핑 #플레이스홀더"
        full = f"{caption_body}\n\n{tags}"
        (out_dir / "caption.txt").write_text(caption_body + "\n", encoding="utf-8")
        (out_dir / "hashtags.txt").write_text(tags + "\n", encoding="utf-8")
        (out_dir / "instagram_post.txt").write_text(full + "\n", encoding="utf-8")

        for i, slide in enumerate(slides, start=1):
            html_path = out_dir / f"slide-{i:02d}.html"
            html_path.write_text(slide.html, encoding="utf-8")
            html_paths.append(html_path)
            if render_png:
                png_path = out_dir / f"slide-{i:02d}.png"
                try:
                    renderer.screenshot_html(slide.html, png_path)
                    png_paths.append(png_path)
                    print(f"  editorial rendered: {png_path.name}")
                except Exception as exc:  # noqa: BLE001
                    print(f"  !! PNG skip {html_path.name}: {exc}")

        # Lightweight CardBundle for downstream compatibility
        bundle = CardBundle(
            slides=tuple(
                Slide(
                    type=SlideType.STORY,
                    headline=s.fields.get("headline")
                    or s.fields.get("title")
                    or s.fields.get("summary_quote")
                    or s.filename,
                    body="",
                    index=f"{i:02d}",
                    role=s.filename.split("-", 1)[-1].replace(".html", ""),
                    label=s.filename,
                )
                for i, s in enumerate(slides, start=1)
            ),
            post=InstagramPost(
                body=caption_body,
                hashtags=("경제뉴스", "사회뉴스", "브리핑", "플레이스홀더"),
                full_text=full,
            ),
            template_id="editorial_carousel",
        )
        (out_dir / "slides.json").write_text(
            json.dumps(
                {
                    "template_id": bundle.template_id,
                    "slides": bundle.slides_as_dicts(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "html": html_paths,
            "png": png_paths,
            "bundle": bundle,
            "meta": out_dir / "template_meta.json",
        }
