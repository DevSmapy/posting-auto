"""One-page 1080×1080 blog infographic: pictogram choice, slot fill, PNG export.

The fact-layer LLM may only propose catalog IDs; every decision below happens in
code so the same briefing always renders the same image.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import CardFormatConfig
from .renderer import CardRenderer

ROOT = Path(__file__).resolve().parents[2]
INFOGRAPHIC_DIR = ROOT / "templates" / "cards" / "infographic"
CATALOG_PATH = INFOGRAPHIC_DIR / "pictograms.json"
SPRITE_PATH = INFOGRAPHIC_DIR / "pictograms.svg"
TEMPLATE_PATH = INFOGRAPHIC_DIR / "onepager.html"
CSS_PATH = INFOGRAPHIC_DIR / "design-system.css"

CANVAS = (1080, 1080)
SIGNAL_SLOTS = 3

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


# --- briefing -> slots -------------------------------------------------------

KICKER = "MORNING BRIEF"
LEAD_LABEL = "TODAY'S BRIEFING"
INSIGHT_LABEL = "ONE-LINE INSIGHT"
SIGNALS_LABEL = "KEY SIGNALS"

#: Character budgets picked so the 1080×1080 canvas never overflows.
LIMITS: dict[str, int] = {
    "title": 40,
    "intro": 62,
    "insight": 58,
    "story_title": 22,
    "story_body": 46,
    "impact_body": 32,
}

#: Impact strip: (label, catalog id, market_impact bucket).
IMPACT_CELLS: tuple[tuple[str, str, str], ...] = (
    ("POSITIVE", "trend-up", "positive"),
    ("WATCH", "volatility", "neutral"),
    ("PRESSURE", "trend-down", "negative"),
    ("NEXT", "economic-indicator", ""),
)

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?。])\s+")


def _first_sentence(text: Any) -> str:
    """Infographic copy is one line per slot; drop everything after sentence 1."""
    flat = _WS_RE.sub(" ", str(text or "")).strip()
    return _SENTENCE_END_RE.split(flat, maxsplit=1)[0].strip() if flat else ""


def _trim(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _short(text: Any, limit: int) -> str:
    return _trim(_first_sentence(text), limit)


def _headline_part(title: Any) -> str:
    """briefing.title is "본문 제목 | 브랜드 (날짜)"; only the first part fits."""
    return str(title or "").split("|", 1)[0].strip()


def _first_line(values: Any) -> str:
    if isinstance(values, str):
        return values
    for value in values or []:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _next_watch(briefing: Mapping[str, Any]) -> str:
    for event in briefing.get("upcoming_events") or []:
        # Markdown/HTML assembly accepts bare strings here too; stay in step.
        title = str(
            (event.get("title") if isinstance(event, Mapping) else event) or ""
        ).strip()
        if title:
            return title
    for story in briefing.get("stories") or []:
        watch = str((story or {}).get("watch_next") or "").strip()
        if watch:
            return watch
    return ""


def build_infographic_fields(
    briefing: Mapping[str, Any],
    *,
    brand: str = "경제 브리핑",
    date: str = "",
    catalog: Mapping[str, Pictogram] | None = None,
) -> tuple[dict[str, str], list[PictogramMatch]]:
    """Map briefing.json onto the template slots, one icon decision per story."""
    catalog = catalog if catalog is not None else load_catalog()
    stories = [s for s in (briefing.get("stories") or []) if isinstance(s, Mapping)]
    matches = resolve_pictograms(stories[:SIGNAL_SLOTS], catalog=catalog)

    insight = _short(briefing.get("insight"), LIMITS["insight"])
    fields: dict[str, str] = {
        "brand": brand,
        "date": date,
        "kicker": KICKER,
        "lead_label": LEAD_LABEL,
        "signals_label": SIGNALS_LABEL,
        "insight_label": INSIGHT_LABEL,
        "insight": insight,
        "insight_state": "" if insight else "is-empty",
        "title": _trim(_headline_part(briefing.get("title")), LIMITS["title"]),
        "intro": _short(briefing.get("intro"), LIMITS["intro"]),
    }

    for slot in range(1, SIGNAL_SLOTS + 1):
        story = stories[slot - 1] if slot <= len(stories) else {}
        match = matches[slot - 1] if slot <= len(matches) else None
        title = _short(story.get("headline") or story.get("title"), LIMITS["story_title"])
        body = _short(
            story.get("one_liner") or story.get("what_happened") or story.get("summary"),
            LIMITS["story_body"],
        )
        fields[f"story_{slot}_index"] = f"{slot:02d}"
        fields[f"story_{slot}_title"] = title
        fields[f"story_{slot}_body"] = body
        fields[f"story_{slot}_icon"] = (
            match.symbol_id if match else f"{SYMBOL_PREFIX}{GENERIC_ID}"
        )
        fields[f"story_{slot}_state"] = "" if title else "is-empty"

    impact = briefing.get("market_impact")
    impact = impact if isinstance(impact, Mapping) else {}
    for slot, (label, icon, bucket) in enumerate(IMPACT_CELLS, start=1):
        raw = _first_line(impact.get(bucket)) if bucket else _next_watch(briefing)
        body = _short(raw, LIMITS["impact_body"])
        fields[f"impact_{slot}_label"] = label
        fields[f"impact_{slot}_icon"] = f"{SYMBOL_PREFIX}{icon}"
        fields[f"impact_{slot}_body"] = body
        fields[f"impact_{slot}_state"] = "" if body else "is-empty"

    return fields, matches


def render_infographic_html(
    briefing: Mapping[str, Any],
    *,
    brand: str = "경제 브리핑",
    date: str = "",
    catalog: Mapping[str, Pictogram] | None = None,
) -> tuple[str, dict[str, str], list[PictogramMatch]]:
    fields, matches = build_infographic_fields(
        briefing, brand=brand, date=date, catalog=catalog
    )
    document = TEMPLATE_PATH.read_text(encoding="utf-8")
    document = document.replace(
        "{{DESIGN_SYSTEM_CSS}}", CSS_PATH.read_text(encoding="utf-8")
    ).replace("{{PICTOGRAM_SPRITE}}", load_sprite())

    def fill(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in fields:
            return match.group(0)
        return html.escape(fields[key])

    document = _PLACEHOLDER_RE.sub(fill, document)
    leftover = sorted({m.group(1) for m in _PLACEHOLDER_RE.finditer(document)})
    if leftover:
        raise ValueError(f"infographic template has unfilled slots: {leftover}")
    return document, fields, matches


def export_infographic(
    briefing: Mapping[str, Any],
    out_dir: Path,
    *,
    brand: str = "경제 브리핑",
    date: str = "",
    render_png: bool = True,
    renderer: CardRenderer | None = None,
) -> dict[str, Any]:
    """Write infographic.html / .png / .json. A PNG failure is reported, not raised."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    document, fields, matches = render_infographic_html(briefing, brand=brand, date=date)

    html_path = out_dir / "infographic.html"
    html_path.write_text(document, encoding="utf-8")

    png_path: Path | None = None
    error = ""
    if render_png:
        target = out_dir / "infographic.png"
        renderer = renderer or CardRenderer(
            replace(CardFormatConfig.from_env(), width=CANVAS[0], height=CANVAS[1])
        )
        try:
            renderer.screenshot_html(document, target)
            png_path = target
            print(f"  infographic rendered: {target.name}")
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            print(f"  !! infographic PNG skip: {exc}")

    meta = {
        "canvas": {"width": CANVAS[0], "height": CANVAS[1]},
        "date": date,
        "brand": brand,
        "fields": fields,
        "pictograms": [m.as_dict() for m in matches],
        "png": png_path.name if png_path else "",
        "error": error,
    }
    meta_path = out_dir / "infographic.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"html": html_path, "png": png_path, "meta": meta_path, "error": error}
