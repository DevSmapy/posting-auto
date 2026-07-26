"""Card news data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SlideType(str, Enum):
    COVER = "cover"
    STORY = "story"
    DISCLAIMER = "disclaimer"
    HOOK = "hook"
    CTA = "cta"
    NUMBER = "number"


@dataclass(frozen=True)
class Slide:
    type: SlideType
    headline: str
    body: str
    index: str | None = None
    role: str | None = None
    label: str | None = None

    def to_dict(self) -> dict[str, str]:
        data = {
            "type": self.type.value,
            "headline": self.headline,
            "body": self.body,
        }
        if self.index:
            data["index"] = self.index
        if self.role:
            data["role"] = self.role
        if self.label:
            data["label"] = self.label
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Slide:
        stype = str(raw.get("type") or "story").lower()
        try:
            slide_type = SlideType(stype)
        except ValueError:
            slide_type = SlideType.STORY
        return cls(
            type=slide_type,
            headline=str(raw.get("headline") or ""),
            body=str(raw.get("body") or ""),
            index=str(raw["index"]) if raw.get("index") else None,
            role=str(raw["role"]) if raw.get("role") else None,
            label=str(raw["label"]) if raw.get("label") else None,
        )


@dataclass(frozen=True)
class InstagramPost:
    """Instagram carousel caption body + hashtags."""

    body: str
    hashtags: tuple[str, ...] = ()
    full_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "body": self.body,
            "hashtags": list(self.hashtags),
            "full_text": self.full_text,
        }


@dataclass(frozen=True)
class CardBundle:
    slides: tuple[Slide, ...]
    post: InstagramPost
    related_keywords: tuple[str, ...] = field(default_factory=tuple)
    template_id: str | None = None

    def slides_as_dicts(self) -> list[dict[str, str]]:
        return [s.to_dict() for s in self.slides]
