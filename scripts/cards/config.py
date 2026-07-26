"""Card news format configuration (env-backed)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _split_csv(raw: str) -> list[str]:
    return [p.strip().lstrip("#") for p in raw.split(",") if p.strip()]


@dataclass(frozen=True)
class CardFormatConfig:
    brand: str = "경제 브리핑"
    width: int = 1080
    height: int = 1080
    caption_max_chars: int = 2100
    max_hashtags: int = 12
    base_hashtags: tuple[str, ...] = (
        "경제뉴스",
        "증시",
        "주식",
        "경제브리핑",
    )
    disclaimer: str = "※ 정보 안내용이며 투자 권유가 아닙니다."
    cta: str = "자세한 해설은 프로필 링크·블로그 브리핑에서 이어갑니다."
    story_body_max_chars: int = 90
    headline_max_chars: int = 40
    browserless_url: str = "http://localhost:3000"
    # Matches ghcr.io/browserless/chromium (compose default). Override for chrome/multi.
    browserless_screenshot_path: str = "/chromium/screenshot"
    browserless_token: str = ""
    screenshot_bin: str = ""
    templates_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "templates" / "cards"
    )

    @classmethod
    def from_env(cls) -> CardFormatConfig:
        base = _split_csv(_env("CARD_BASE_HASHTAGS"))
        screenshot = _env("CARD_SCREENSHOT_BIN")
        path = _env("BROWSERLESS_SCREENSHOT_PATH", "/chromium/screenshot")
        if path and not path.startswith("/"):
            path = f"/{path}"
        return cls(
            brand=_env("CARD_BRAND") or "경제 브리핑",
            width=int(_env("CARD_WIDTH", "1080") or "1080"),
            height=int(_env("CARD_HEIGHT", "1080") or "1080"),
            caption_max_chars=int(_env("CARD_CAPTION_MAX_CHARS", "2100") or "2100"),
            max_hashtags=int(_env("CARD_MAX_HASHTAGS", "12") or "12"),
            base_hashtags=tuple(base)
            if base
            else ("경제뉴스", "증시", "주식", "경제브리핑"),
            disclaimer=_env("CARD_DISCLAIMER")
            or "※ 정보 안내용이며 투자 권유가 아닙니다.",
            cta=_env("CARD_CTA")
            or "자세한 해설은 프로필 링크·블로그 브리핑에서 이어갑니다.",
            story_body_max_chars=int(_env("CARD_STORY_BODY_MAX", "90") or "90"),
            headline_max_chars=int(_env("CARD_HEADLINE_MAX", "40") or "40"),
            browserless_url=_env("BROWSERLESS_URL", "http://localhost:3000").rstrip("/")
            or "http://localhost:3000",
            browserless_screenshot_path=path or "/chromium/screenshot",
            browserless_token=_env("BROWSERLESS_TOKEN"),
            screenshot_bin=screenshot,
        )
