"""Deterministic pictogram selection for the blog infographic.

The fact-layer LLM may only propose catalog IDs; every decision below happens in
code so the same briefing always renders the same icons.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
INFOGRAPHIC_DIR = ROOT / "templates" / "cards" / "infographic"
CATALOG_PATH = INFOGRAPHIC_DIR / "pictograms.json"
SPRITE_PATH = INFOGRAPHIC_DIR / "pictograms.svg"

GENERIC_ID = "generic"
SYMBOL_PREFIX = "pg-"

#: Fields read for the headline stage (stronger signal than body copy).
HEADLINE_FIELDS: tuple[str, ...] = ("headline", "title", "topic", "source_topic", "category")
#: Fields read for the body stage.
BODY_FIELDS: tuple[str, ...] = (
    "one_liner",
    "what_happened",
    "summary",
    "why_important",
    "why_it_matters",
    "impact",
    "watch_next",
)

_WS_RE = re.compile(r"\s+")
_ASCII_TAG_RE = re.compile(r"\A[a-z0-9][a-z0-9 .+-]*\Z")
_SYMBOL_ID_RE = re.compile(r"<symbol\s[^>]*\bid=\"([^\"]+)\"")


@dataclass(frozen=True)
class Pictogram:
    id: str
    group: str
    priority: int
    order: int
    directional: bool
    tags: tuple[str, ...]

    @property
    def symbol_id(self) -> str:
        return f"{SYMBOL_PREFIX}{self.id}"


@dataclass(frozen=True)
class PictogramMatch:
    """Resolved icon plus the audit trail written to ``infographic.json``."""

    id: str
    source: str
    matched_tag: str = ""
    dropped_tags: tuple[str, ...] = ()

    @property
    def symbol_id(self) -> str:
        return f"{SYMBOL_PREFIX}{self.id}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol_id": self.symbol_id,
            "source": self.source,
            "matched_tag": self.matched_tag,
            "dropped_tags": list(self.dropped_tags),
        }


@lru_cache(maxsize=4)
def load_catalog(path: Path | None = None) -> dict[str, Pictogram]:
    """Read ``pictograms.json`` into an ordered id → Pictogram mapping."""
    raw = json.loads((path or CATALOG_PATH).read_text(encoding="utf-8"))
    if raw.get("generic_id") != GENERIC_ID:
        raise ValueError(f"catalog generic_id must be {GENERIC_ID!r}")

    catalog: dict[str, Pictogram] = {}
    for order, entry in enumerate(raw.get("pictograms") or []):
        pid = str(entry.get("id") or "").strip()
        if not pid:
            raise ValueError("catalog entry without id")
        if pid in catalog:
            raise ValueError(f"duplicate pictogram id: {pid}")
        tags = tuple(
            dict.fromkeys(
                _normalize(tag)
                for tag in (*(entry.get("tags_ko") or []), *(entry.get("tags_en") or []))
                if _normalize(tag)
            )
        )
        catalog[pid] = Pictogram(
            id=pid,
            group=str(entry.get("group") or ""),
            priority=int(entry.get("priority", 50)),
            order=order,
            directional=bool(entry.get("directional", False)),
            tags=tags,
        )
    if GENERIC_ID not in catalog:
        raise ValueError(f"catalog is missing the {GENERIC_ID!r} fallback")
    return catalog


@lru_cache(maxsize=4)
def load_sprite(path: Path | None = None) -> str:
    """Inline SVG sprite; embedded directly in the infographic HTML."""
    return (path or SPRITE_PATH).read_text(encoding="utf-8").strip()


@lru_cache(maxsize=4)
def sprite_symbol_ids(path: Path | None = None) -> frozenset[str]:
    return frozenset(_SYMBOL_ID_RE.findall(load_sprite(path)))


def _normalize(text: Any) -> str:
    return _WS_RE.sub(" ", str(text or "")).strip().casefold()


def _tag_in_text(tag: str, text: str) -> bool:
    if not tag or not text:
        return False
    if _ASCII_TAG_RE.match(tag):
        # Latin tags need boundaries so "ai" does not fire inside "said".
        return re.search(rf"(?<![a-z0-9]){re.escape(tag)}(?![a-z0-9])", text) is not None
    return tag in text


def _story_text(story: Mapping[str, Any], fields: Iterable[str]) -> str:
    return _normalize(" ".join(str(story.get(f) or "") for f in fields))


def _pick(candidates: Sequence[tuple[Pictogram, str]]) -> tuple[Pictogram, str]:
    return min(candidates, key=lambda c: (c[0].priority, c[0].order))


def _keyword_candidates(
    catalog: Mapping[str, Pictogram], text: str
) -> list[tuple[Pictogram, str]]:
    found: list[tuple[Pictogram, str]] = []
    for pictogram in catalog.values():
        matched = [tag for tag in pictogram.tags if _tag_in_text(tag, text)]
        if matched:
            found.append((pictogram, max(matched, key=len)))
    return found


def validate_visual_tags(
    raw: Any, catalog: Mapping[str, Pictogram] | None = None
) -> tuple[list[str], list[str]]:
    """Split LLM-proposed tags into known catalog IDs and rejected values."""
    catalog = catalog if catalog is not None else load_catalog()
    if isinstance(raw, str):
        raw = [raw]
    valid: list[str] = []
    invalid: list[str] = []
    for item in raw or []:
        original = str(item or "").strip()
        if not original:
            continue
        tag = original.casefold()
        if tag not in catalog:
            invalid.append(original)
        elif tag not in valid:
            valid.append(tag)
    return valid, invalid


def resolve_pictogram(
    story: Mapping[str, Any], *, catalog: Mapping[str, Pictogram] | None = None
) -> PictogramMatch:
    """Pick one icon per story: LLM tags → headline → body → generic."""
    catalog = catalog if catalog is not None else load_catalog()
    full_text = _story_text(story, (*HEADLINE_FIELDS, *BODY_FIELDS))

    valid, dropped = validate_visual_tags(story.get("visual_tags"), catalog)
    candidates: list[tuple[Pictogram, str]] = []
    for pid in valid:
        pictogram = catalog[pid]
        # Direction icons imply a claim, so they need an explicit keyword in the copy.
        if pictogram.directional and not any(
            _tag_in_text(tag, full_text) for tag in pictogram.tags
        ):
            dropped.append(pid)
            continue
        candidates.append((pictogram, pid))
    if candidates:
        best, tag = _pick(candidates)
        return PictogramMatch(best.id, "visual_tags", tag, tuple(dropped))

    for source, fields in (("headline", HEADLINE_FIELDS), ("body", BODY_FIELDS)):
        found = _keyword_candidates(catalog, _story_text(story, fields))
        if found:
            best, tag = _pick(found)
            return PictogramMatch(best.id, source, tag, tuple(dropped))

    return PictogramMatch(GENERIC_ID, "fallback", "", tuple(dropped))


def visual_tag_options(catalog: Mapping[str, Pictogram] | None = None) -> list[str]:
    """Catalog IDs offered to the fact-layer LLM (``generic`` stays code-side)."""
    catalog = catalog if catalog is not None else load_catalog()
    return [p.id for p in catalog.values() if p.id != GENERIC_ID]


def resolve_pictograms(
    stories: Iterable[Mapping[str, Any]],
    *,
    catalog: Mapping[str, Pictogram] | None = None,
) -> list[PictogramMatch]:
    catalog = catalog if catalog is not None else load_catalog()
    return [resolve_pictogram(story, catalog=catalog) for story in stories]
