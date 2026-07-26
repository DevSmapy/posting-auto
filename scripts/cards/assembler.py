"""Assemble card slides + Instagram post from briefing stories."""

from __future__ import annotations

from datetime import datetime

from .caption import InstagramCaptionBuilder
from .config import CardFormatConfig
from .copy import CardCopyRules
from .models import CardBundle, Slide, SlideType


class CardAssembler:
    """Build a CardBundle (slides + InstagramPost) from story dicts."""

    def __init__(
        self,
        config: CardFormatConfig | None = None,
        copy_rules: CardCopyRules | None = None,
        caption_builder: InstagramCaptionBuilder | None = None,
    ) -> None:
        self.config = config or CardFormatConfig.from_env()
        self.copy = copy_rules or CardCopyRules(self.config)
        self.captions = caption_builder or InstagramCaptionBuilder(
            self.config, self.copy
        )

    def assemble(
        self,
        stories: list[dict],
        now: datetime,
        related_keywords: list[str] | None = None,
    ) -> CardBundle:
        # Contract: upstream should pass 3–5 stories so the deck is 5–7 slides.
        # Clamp overflow; allow fewer than 3 for thin news days / tests.
        stories = list(stories[:5])
        keywords = related_keywords
        if keywords is None:
            keywords = ["경제", "증시", "브리핑", "시장", "뉴스"]

        slides = self._build_slides(stories, now)
        post = self.captions.build(stories, now, related_keywords=keywords)
        return CardBundle(
            slides=tuple(slides),
            post=post,
            related_keywords=tuple(keywords),
        )

    def _build_slides(self, stories: list[dict], now: datetime) -> list[Slide]:
        date_dot = now.strftime("%Y.%m.%d")
        theme = self.copy.cover_theme(stories)
        slides: list[Slide] = [
            Slide(
                type=SlideType.COVER,
                headline=self.config.brand,
                body=f"{date_dot}\n{theme}",
            )
        ]
        for i, story in enumerate(stories, start=1):
            slides.append(
                Slide(
                    type=SlideType.STORY,
                    headline=self.copy.story_headline(story),
                    body=self.copy.story_body(story),
                    index=f"{i:02d}",
                )
            )
        slides.append(
            Slide(
                type=SlideType.DISCLAIMER,
                headline="참고하세요",
                body=self.config.disclaimer.lstrip("※ ").strip(),
            )
        )
        return slides
