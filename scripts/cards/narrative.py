"""Assemble a CardBundle from a named template bundle + filled slide copy."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .bundles import TemplateBundle, get_bundle, recommend_for_economy_society
from .caption import InstagramCaptionBuilder
from .config import CardFormatConfig
from .models import CardBundle, InstagramPost, Slide, SlideType


_ROLE_TO_TYPE: dict[str, SlideType] = {
    "hook": SlideType.HOOK,
    "cta": SlideType.CTA,
    "cover": SlideType.COVER,
    "disclaimer": SlideType.DISCLAIMER,
    "number": SlideType.NUMBER,
    "summary": SlideType.STORY,
}


class NarrativeAssembler:
    """Fill a TemplateBundle slide sequence with provided copy blocks."""

    def __init__(self, config: CardFormatConfig | None = None) -> None:
        self.config = config or CardFormatConfig.from_env()
        self.captions = InstagramCaptionBuilder(self.config)

    def assemble(
        self,
        filled_slides: list[dict[str, Any]],
        now: datetime,
        *,
        bundle: TemplateBundle | None = None,
        bundle_id: str | None = None,
        related_keywords: list[str] | None = None,
        caption_hook: str | None = None,
    ) -> CardBundle:
        template = bundle
        if template is None:
            template = (
                get_bundle(bundle_id)
                if bundle_id
                else recommend_for_economy_society()
            )

        if len(filled_slides) != len(template.slides):
            raise ValueError(
                f"bundle {template.id} expects {len(template.slides)} slides, "
                f"got {len(filled_slides)}"
            )

        slides: list[Slide] = []
        for i, (spec, filled) in enumerate(
            zip(template.slides, filled_slides, strict=True), start=1
        ):
            role = str(filled.get("role") or spec.role)
            slide_type = _ROLE_TO_TYPE.get(role, SlideType.STORY)
            slides.append(
                Slide(
                    type=slide_type,
                    headline=str(filled.get("headline") or "").strip(),
                    body=str(filled.get("body") or "").strip(),
                    index=f"{i:02d}",
                    role=role,
                    label=str(filled.get("label") or spec.label),
                )
            )

        keywords = related_keywords or list(template.recommended_topics[:5])
        # Build Instagram caption from narrative points (skip hook/cta extremes optionally)
        story_like = [
            {
                "headline": s.headline,
                "one_liner": s.body.replace("\n", " "),
            }
            for s in slides
            if s.role not in {"cta", "cover", "disclaimer"}
        ]
        post = self.captions.build(story_like, now, related_keywords=keywords)
        if caption_hook:
            # Prefers explicit hook line at top of body
            lines = post.body.split("\n")
            if len(lines) >= 2:
                lines[1] = caption_hook
                body = "\n".join(lines)
                tags = " ".join(f"#{t}" for t in post.hashtags)
                full = f"{body}\n\n{tags}".strip() if tags else body
                if len(full) > self.config.caption_max_chars:
                    full = full[: self.config.caption_max_chars - 1] + "…"
                post = InstagramPost(
                    body=body, hashtags=post.hashtags, full_text=full
                )

        return CardBundle(
            slides=tuple(slides),
            post=post,
            related_keywords=tuple(keywords),
            template_id=template.id,
        )
