"""Card-news template bundles catalog (economy/society sets)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

BUNDLES_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class BundleSlideSpec:
    role: str
    label: str
    title_hint: str
    purpose: str
    repeatable: bool = False
    min_count: int | None = None
    max_count: int | None = None


@dataclass(frozen=True)
class TemplateBundle:
    id: str
    index: int
    name_ko: str
    name_en: str
    purpose: str
    card_count: int | str
    recommended_topics: tuple[str, ...]
    fit_score_economy_society: int
    slides: tuple[BundleSlideSpec, ...]
    badge: str | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TemplateBundle:
        slides = tuple(
            BundleSlideSpec(
                role=str(s["role"]),
                label=str(s["label"]),
                title_hint=str(s["title_hint"]),
                purpose=str(s["purpose"]),
                repeatable=bool(s.get("repeatable", False)),
                min_count=int(s["min_count"]) if s.get("min_count") is not None else None,
                max_count=int(s["max_count"]) if s.get("max_count") is not None else None,
            )
            for s in raw.get("slides") or []
        )
        return cls(
            id=str(raw["id"]),
            index=int(raw["index"]),
            name_ko=str(raw["name_ko"]),
            name_en=str(raw["name_en"]),
            purpose=str(raw.get("purpose") or ""),
            card_count=raw.get("card_count") or len(slides),
            recommended_topics=tuple(raw.get("recommended_topics") or ()),
            fit_score_economy_society=int(raw.get("fit_score_economy_society") or 0),
            slides=slides,
            badge=raw.get("badge"),
            notes=raw.get("notes"),
        )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_design_guide() -> dict[str, Any]:
    return _load_json(BUNDLES_DIR / "design_guide.json")


@lru_cache(maxsize=1)
def list_bundles() -> tuple[TemplateBundle, ...]:
    paths = sorted(BUNDLES_DIR.glob("[0-9][0-9]_*.json"))
    return tuple(TemplateBundle.from_dict(_load_json(p)) for p in paths)


def get_bundle(bundle_id: str) -> TemplateBundle:
    for bundle in list_bundles():
        if bundle.id == bundle_id:
            return bundle
    known = ", ".join(b.id for b in list_bundles())
    raise KeyError(f"unknown bundle {bundle_id!r}; known: {known}")


def recommend_for_economy_society() -> TemplateBundle:
    """Pick the best-fitting template for general economy/society news."""
    bundles = list_bundles()
    return max(bundles, key=lambda b: (b.fit_score_economy_society, -b.index))
