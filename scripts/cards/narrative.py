"""Assemble a CardBundle from a named template bundle + filled slide copy."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .bundles import BundleSlideSpec, TemplateBundle, get_bundle, recommend_for_economy_society
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

        paired = self._expand_with_repeatable(template, filled_slides)
        slides: list[Slide] = []
        for i, (spec, filled) in enumerate(paired, start=1):
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
            lines = post.body.split("\n")
            if len(lines) >= 2:
                lines[1] = caption_hook
                body = "\n".join(lines)
                max_chars = self.config.caption_max_chars
                # Truncate plain body first so full_text never keeps partial tags.
                if 0 < max_chars < len(body):
                    body = InstagramCaptionBuilder._truncate(body, max_chars)
                    post = InstagramPost(body=body, hashtags=(), full_text=body)
                else:
                    retained: list[str] = []
                    tags_line = ""
                    for tag in post.hashtags:
                        trial = retained + [tag]
                        trial_line = " ".join(f"#{t}" for t in trial)
                        full_trial = f"{body}\n\n{trial_line}"
                        if 0 < max_chars < len(full_trial):
                            break
                        retained = trial
                        tags_line = trial_line
                    full = f"{body}\n\n{tags_line}".strip() if tags_line else body
                    post = InstagramPost(
                        body=body, hashtags=tuple(retained), full_text=full
                    )

        return CardBundle(
            slides=tuple(slides),
            post=post,
            related_keywords=tuple(keywords),
            template_id=template.id,
        )

    def _expand_with_repeatable(
        self,
        template: TemplateBundle,
        filled_slides: list[dict[str, Any]],
    ) -> list[tuple[BundleSlideSpec, dict[str, Any]]]:
        """Match filled slides to specs, expanding repeatable slots via min/max."""
        if not any(s.repeatable for s in template.slides):
            if len(filled_slides) != len(template.slides):
                raise ValueError(
                    f"bundle {template.id} expects {len(template.slides)} slides, "
                    f"got {len(filled_slides)}"
                )
            return list(zip(template.slides, filled_slides, strict=True))

        paired: list[tuple[BundleSlideSpec, dict[str, Any]]] = []
        fi = 0
        specs = template.slides
        for si, spec in enumerate(specs):
            if not spec.repeatable:
                if fi >= len(filled_slides):
                    raise ValueError(
                        f"bundle {template.id}: missing filled slide for role={spec.role!r}"
                    )
                paired.append((spec, filled_slides[fi]))
                fi += 1
                continue

            remaining_fixed = sum(1 for s in specs[si + 1 :] if not s.repeatable)
            available = len(filled_slides) - fi - remaining_fixed
            min_c = spec.min_count if spec.min_count is not None else 1
            max_c = spec.max_count if spec.max_count is not None else available
            if available < min_c or available > max_c:
                raise ValueError(
                    f"bundle {template.id}: repeatable role={spec.role!r} "
                    f"expects {min_c}–{max_c} items, got {available} "
                    f"(total filled={len(filled_slides)})"
                )
            for _ in range(available):
                paired.append((spec, filled_slides[fi]))
                fi += 1

        if fi != len(filled_slides):
            raise ValueError(
                f"bundle {template.id}: {len(filled_slides) - fi} unused filled slides"
            )

        total = len(paired)
        if template.id == "daily_briefing" and not (5 <= total <= 7):
            raise ValueError(
                f"bundle daily_briefing must emit 5–7 cards, got {total}"
            )
        return paired
