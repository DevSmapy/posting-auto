"""Slide copy normalization rules for card news."""

from __future__ import annotations

import re

from .config import CardFormatConfig


class CardCopyRules:
    """Normalize headlines and story bodies for 1080×1080 slides."""

    def __init__(self, config: CardFormatConfig | None = None) -> None:
        self.config = config or CardFormatConfig.from_env()

    def story_headline(self, story: dict) -> str:
        raw = str(story.get("headline") or "").strip()
        return self._clip(raw, self.config.headline_max_chars)

    def story_body(self, story: dict) -> str:
        """Prefer one_liner; fall back to a short what_happened sentence."""
        one = str(story.get("one_liner") or "").strip()
        if one:
            return self._clip(one, self.config.story_body_max_chars)
        what = str(story.get("what_happened") or story.get("summary") or "").strip()
        if not what:
            return ""
        # First sentence-ish chunk before hard clip
        parts = re.split(r"(?<=[.!?。…])\s+", what)
        first = parts[0].strip() if parts else what
        return self._clip(first, self.config.story_body_max_chars)

    def cover_theme(self, stories: list[dict]) -> str:
        for story in stories:
            one = str(story.get("one_liner") or "").strip()
            if one:
                return self._clip(one, self.config.story_body_max_chars)
            hl = str(story.get("headline") or "").strip()
            if hl:
                return self._clip(hl, self.config.story_body_max_chars)
        return "오늘의 주요 경제 뉴스"

    @staticmethod
    def _clip(text: str, max_chars: int) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        cut = text[: max_chars - 1].rstrip()
        # Prefer breaking on space near the end
        space = cut.rfind(" ")
        if space >= max(8, max_chars // 2):
            cut = cut[:space]
        return cut.rstrip(" ,·-/") + "…"
