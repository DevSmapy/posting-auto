"""Deterministic editorial quality helpers (extends story_quality)."""

from __future__ import annotations

import re
from typing import Any

from story_quality import FIELD_ORDER, validate_story_fields

# Phrases produced by heuristic_story_fields / generic LLM collapse.
FALLBACK_PHRASES = (
    "시장·정책 흐름에 영향을 줄 수 있는 이슈입니다",
    "후속 보도와 시장 반응을 지켜볼 필요가 있습니다",
    "오늘 주요 경제 뉴스를 정리했습니다",
    "영향을 줄 수 있는 이슈",
    "지켜볼 필요가 있습니다",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.。!?？])\s+")


def quality_gate_story(story: dict[str, Any], *, require_source: bool = True) -> list[str]:
    """Hard deterministic checks before / instead of LLM Reviewer."""
    issues = list(validate_story_fields(story))
    norm = {k: str(story.get(k) or "").strip() for k in FIELD_ORDER}

    if norm["headline"] and norm["what_happened"] and norm["headline"] == norm["what_happened"]:
        issues.append("headline:equals_what_happened")

    why = norm["why_important"]
    watch = norm["watch_next"]
    if why and len(why) < 24:
        issues.append("why_important:too_shallow")
    if watch and len(watch) < 20:
        issues.append("watch_next:too_shallow")

    blob = " ".join(norm.values())
    for phrase in FALLBACK_PHRASES:
        if phrase in blob:
            issues.append(f"fallback_phrase:{phrase[:32]}")
            break

    if story.get("_fallback") == "heuristic" or story.get("fallback") == "heuristic":
        issues.append("heuristic_fallback")

    # Repeated sentences across fields
    sentences: list[str] = []
    for key in FIELD_ORDER:
        text = norm[key]
        if not text:
            continue
        parts = _SENTENCE_SPLIT.split(text) if _SENTENCE_SPLIT.search(text) else [text]
        for part in parts:
            cleaned = part.strip().casefold()
            if len(cleaned) < 12:
                continue
            if cleaned in sentences:
                issues.append(f"{key}:duplicate_sentence")
            else:
                sentences.append(cleaned)

    if require_source:
        url = str(story.get("source_url") or "").strip()
        if not url:
            issues.append("source_url:missing")

    return sorted(set(issues))


def quality_gate_briefing(briefing: dict[str, Any]) -> dict[str, Any]:
    stories = list(briefing.get("stories") or [])
    per_story: list[dict[str, Any]] = []
    hard_fail_ids: list[int] = []
    for i, story in enumerate(stories):
        issues = quality_gate_story(story if isinstance(story, dict) else {})
        entry = {"index": i, "issues": issues}
        per_story.append(entry)
        hard = [
            x
            for x in issues
            if x.endswith(":empty")
            or x.startswith("fallback_phrase:")
            or x == "heuristic_fallback"
            or x.endswith(":too_shallow")
            or x == "headline:equals_what_happened"
            or x == "source_url:missing"
        ]
        if hard:
            hard_fail_ids.append(i)
    return {
        "story_results": per_story,
        "hard_fail_indices": hard_fail_ids,
        "ok": not hard_fail_ids,
    }
