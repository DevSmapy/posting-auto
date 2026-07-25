"""Instagram post body (caption + hashtags) builder."""

from __future__ import annotations

from datetime import datetime

from .config import CardFormatConfig
from .copy import CardCopyRules
from .models import InstagramPost


class InstagramCaptionBuilder:
    """Assemble Instagram carousel caption from stories (rule-based)."""

    def __init__(
        self,
        config: CardFormatConfig | None = None,
        copy_rules: CardCopyRules | None = None,
    ) -> None:
        self.config = config or CardFormatConfig.from_env()
        self.copy = copy_rules or CardCopyRules(self.config)

    def build(
        self,
        stories: list[dict],
        now: datetime,
        related_keywords: list[str] | None = None,
    ) -> InstagramPost:
        date_dot = now.strftime("%Y.%m.%d")
        brand = self.config.brand
        hook = self.copy.cover_theme(stories)

        lines = [
            f"{brand} · {date_dot}",
            hook,
            "",
            "오늘의 포인트",
        ]
        if stories:
            for i, story in enumerate(stories, start=1):
                point = self.copy.story_body(story) or self.copy.story_headline(story)
                if point:
                    lines.append(f"{i}) {point}")
        else:
            lines.append("1) 오늘 선정된 경제 이슈를 정리했습니다.")

        lines.extend(
            [
                "",
                self.config.cta,
                "",
                self.config.disclaimer,
            ]
        )
        body = "\n".join(lines).strip()
        hashtags = self._merge_hashtags(related_keywords or [])
        tags_line = " ".join(f"#{t}" for t in hashtags)
        full = f"{body}\n\n{tags_line}".strip() if tags_line else body
        full = self._truncate(full, self.config.caption_max_chars)
        # Keep body in sync if truncate cut into tags (prefer keeping body intact)
        if len(full) < len(body):
            body = full
        return InstagramPost(body=body, hashtags=tuple(hashtags), full_text=full)

    def _merge_hashtags(self, related: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for tag in (*self.config.base_hashtags, *related):
            cleaned = str(tag or "").strip().lstrip("#").replace(" ", "")
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(cleaned)
            if len(out) >= self.config.max_hashtags:
                break
        return out

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"
