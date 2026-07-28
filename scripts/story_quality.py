"""Target-language validation and deterministic repairs for story fields."""

from __future__ import annotations

import os
import re
from typing import Any

FIELD_ORDER = (
    "headline",
    "what_happened",
    "why_important",
    "watch_next",
    "one_liner",
)

_WS_RE = re.compile(r"\s+")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_HIRAGANA_RE = re.compile(r"[\u3040-\u309f]")
_KATAKANA_RE = re.compile(r"[\u30a0-\u30ff]")
_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _normalize_language_tag(value: str) -> str:
    """Return BCP-47 primary language subtag (e.g. ko-KR / ko_KR -> ko)."""
    raw = (value or "").strip().lower().replace("_", "-")
    if not raw:
        return "ko"
    primary = raw.split("-", 1)[0].strip()
    return primary or "ko"


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def target_language() -> str:
    return _normalize_language_tag(_env("TARGET_LANGUAGE", "ko") or "ko")


def target_locale() -> str:
    explicit = _env("TARGET_LOCALE")
    if explicit:
        return explicit.replace("_", "-")
    raw_lang = (_env("TARGET_LANGUAGE", "ko") or "ko").strip().replace("_", "-")
    if "-" in raw_lang:
        return raw_lang
    lang = target_language()
    return "ko-KR" if lang == "ko" else lang


def story_length_limits() -> dict[str, int]:
    return {
        "headline": _env_int("STORY_HEADLINE_MAX_CHARS", 60),
        "what_happened": _env_int("STORY_WHAT_MAX_CHARS", 320),
        "why_important": _env_int("STORY_WHY_MAX_CHARS", 260),
        "watch_next": _env_int("STORY_WATCH_MAX_CHARS", 200),
        "one_liner": _env_int("STORY_ONE_LINER_MAX_CHARS", 110),
    }


def normalize_story_fields(parsed: Any, article: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise RuntimeError(f"story JSON must be object, got {type(parsed)}")
    headline = str(parsed.get("headline") or article.get("title") or "").strip()
    what = str(parsed.get("what_happened") or "").strip()
    why = str(parsed.get("why_important") or "").strip()
    watch = str(parsed.get("watch_next") or "").strip()
    one = str(parsed.get("one_liner") or "").strip()
    if not what or not why or not watch or not one:
        raise RuntimeError("story JSON missing required fields")
    return {
        "headline": headline or str(article.get("title") or "").strip(),
        "what_happened": what,
        "why_important": why,
        "watch_next": watch,
        "one_liner": one,
        "source_name": article.get("source") or "",
        "source_url": article.get("link") or "",
    }


def deterministic_story_repair(story: dict[str, Any]) -> dict[str, Any]:
    limits = story_length_limits()
    repaired = dict(story)
    for key in FIELD_ORDER:
        value = _normalize_text(repaired.get(key))
        repaired[key] = _trim(value, limits[key])
    return repaired


def validate_story_fields(story: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    norm = {k: _normalize_text(story.get(k)) for k in FIELD_ORDER}
    limits = story_length_limits()

    for key, value in norm.items():
        if not value:
            issues.append(f"{key}:empty")
        if limits[key] > 0 and len(value) > limits[key]:
            issues.append(f"{key}:too_long")

    if norm["headline"] and norm["headline"] == norm["one_liner"]:
        issues.append("headline:duplicated_one_liner")

    values = {k: v for k, v in norm.items() if v}
    seen: dict[str, str] = {}
    for key, value in values.items():
        dedupe_key = value.casefold()
        if dedupe_key in seen and seen[dedupe_key] != key:
            issues.append(f"{key}:duplicate_of_{seen[dedupe_key]}")
        else:
            seen[dedupe_key] = key

    issues.extend(_language_issues(norm))
    if norm["one_liner"] and len(norm["one_liner"]) < 8:
        issues.append("one_liner:too_short")
    if norm["headline"] and norm["headline"].endswith(("。", "，")):
        issues.append("headline:awkward_punctuation")
    return sorted(set(issues))


def issues_summary(issues: list[str]) -> str:
    if not issues:
        return "- none"
    return "\n".join(f"- {item}" for item in issues)


def _language_issues(fields: dict[str, str]) -> list[str]:
    lang = target_language()
    joined = " ".join(v for v in fields.values() if v)
    if not joined:
        return []
    stats = _char_stats(joined)
    issues: list[str] = []

    if lang == "ko":
        if stats["hangul_ratio"] < 0.45:
            issues.append("language:not_enough_target_ko")
        if stats["han_ratio"] > 0.20:
            issues.append("language:disallowed_han_dominant")
    elif lang == "en":
        if stats["latin_ratio"] < 0.55:
            issues.append("language:not_enough_target_en")
        if stats["han_ratio"] > 0.10 or stats["hangul_ratio"] > 0.10:
            issues.append("language:disallowed_non_en_dominant")
    elif lang == "ja":
        if stats["jp_ratio"] < 0.35:
            issues.append("language:not_enough_target_ja")
        if stats["hangul_ratio"] > 0.10:
            issues.append("language:disallowed_hangul_dominant")
    elif lang == "zh":
        if stats["han_ratio"] < 0.45:
            issues.append("language:not_enough_target_zh")
        if stats["hangul_ratio"] > 0.10:
            issues.append("language:disallowed_hangul_dominant")
    return issues


def _char_stats(text: str) -> dict[str, float]:
    letters = [ch for ch in text if ch.isalpha()]
    total = len(letters) or 1
    hangul = sum(1 for ch in letters if _HANGUL_RE.fullmatch(ch))
    hiragana = sum(1 for ch in letters if _HIRAGANA_RE.fullmatch(ch))
    katakana = sum(1 for ch in letters if _KATAKANA_RE.fullmatch(ch))
    han = sum(1 for ch in letters if _HAN_RE.fullmatch(ch))
    latin = sum(1 for ch in letters if _LATIN_RE.fullmatch(ch))
    jp = hiragana + katakana + han
    return {
        "hangul_ratio": hangul / total,
        "han_ratio": han / total,
        "latin_ratio": latin / total,
        "jp_ratio": jp / total,
    }


def _normalize_text(value: Any) -> str:
    return _WS_RE.sub(" ", str(value or "")).strip()


def _trim(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rstrip()
    space = cut.rfind(" ")
    if space >= max(8, max_chars // 2):
        cut = cut[:space]
    return cut.rstrip(" ,·-/") + "…"
