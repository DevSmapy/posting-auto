"""Target-language validation and deterministic repairs for story fields."""

from __future__ import annotations

import os
import re
from typing import Any, Literal

FIELD_ORDER = (
    "headline",
    "what_happened",
    "why_important",
    "watch_next",
    "one_liner",
)

LanguageVerdict = Literal["pass", "warn", "hard_fail"]

_WS_RE = re.compile(r"\s+")
_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_HIRAGANA_RE = re.compile(r"[\u3040-\u309f]")
_KATAKANA_RE = re.compile(r"[\u30a0-\u30ff]")
_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_CN_PUNCT = set("。！？、《》【】""''：；")
_SIMPLIFIED_HINT = set("这这们为国会时经发现说对过还个将没")
_KO_PARTICLE = re.compile(
    r"(은|는|이|가|을|를|에|에서|으로|과|와|습니다|입니다|였습니다|했습니다|것입니다|다\.|요\.|니다|하는|했다|된다|했다\.|습니다\.)"
)


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
    if target_language() == "ko":
        issues.extend(language_hard_fail_issues(story))
    if norm["one_liner"] and len(norm["one_liner"]) < 8:
        issues.append("one_liner:too_short")
    if norm["headline"] and norm["headline"].endswith(("。", "，")):
        issues.append("headline:awkward_punctuation")
    return sorted(set(issues))


def issues_summary(issues: list[str]) -> str:
    if not issues:
        return "- none"
    return "\n".join(f"- {item}" for item in issues)


def _strip_urls_for_stats(text: str) -> str:
    return _URL_RE.sub(" ", text)


def assess_korean_text(text: str) -> tuple[LanguageVerdict, list[str]]:
    """Deterministic pass/warn/hard_fail for Korean target output."""
    cleaned = _normalize_text(text)
    if not cleaned:
        return "pass", []

    signals: list[str] = []
    sample = _strip_urls_for_stats(cleaned)
    stats = _char_stats(sample)

    if any(ch in _CN_PUNCT for ch in cleaned):
        signals.append("chinese_punctuation")

    han_chars = [ch for ch in cleaned if _HAN_RE.fullmatch(ch)]
    hangul_count = sum(1 for ch in cleaned if _HANGUL_RE.fullmatch(ch))
    han_count = len(han_chars)
    if han_chars:
        simplified = sum(1 for ch in han_chars if ch in _SIMPLIFIED_HINT)
        if simplified >= 2:
            signals.append("simplified_chinese")
        elif simplified >= 1 and hangul_count < 4:
            signals.append("simplified_chinese")

    has_ko_signal = bool(_KO_PARTICLE.search(cleaned)) or hangul_count >= 6

    if hangul_count == 0 and han_count >= 4:
        return "hard_fail", signals + ["no_hangul_han_dominant"]

    if stats["han_ratio"] > 0.35 and stats["hangul_ratio"] < 0.25:
        return "hard_fail", signals + ["han_dominant_low_hangul"]

    if stats["hangul_ratio"] < 0.20 and han_count >= 3 and not has_ko_signal:
        return "hard_fail", signals + ["likely_non_korean"]

    if "chinese_punctuation" in signals and stats["hangul_ratio"] < 0.40:
        return "hard_fail", signals + ["chinese_punctuation_low_hangul"]

    if stats["han_ratio"] > 0.20:
        if hangul_count >= 8 and has_ko_signal:
            return "warn", signals + ["han_in_proper_noun"]
        if stats["hangul_ratio"] < 0.35:
            return "hard_fail", signals + ["han_dominant"]

    if stats["hangul_ratio"] < 0.45:
        if hangul_count >= 4 and has_ko_signal and han_count <= 2:
            return "warn", signals + ["low_hangul_ratio"]
        if han_count >= 2 and not has_ko_signal:
            return "hard_fail", signals + ["low_hangul_non_korean"]
        if stats["hangul_ratio"] < 0.30:
            return "warn", signals + ["low_hangul_ratio"]

    return "pass", signals


def assess_story_language(story: dict[str, Any]) -> dict[str, Any]:
    if target_language() != "ko":
        return {"overall": "pass", "fields": {}}
    fields: dict[str, Any] = {}
    overall: LanguageVerdict = "pass"
    for key in FIELD_ORDER:
        text = _normalize_text(story.get(key))
        verdict, signals = assess_korean_text(text)
        fields[key] = {"verdict": verdict, "signals": signals}
        if verdict == "hard_fail":
            overall = "hard_fail"
        elif verdict == "warn" and overall == "pass":
            overall = "warn"

    headline_v = fields.get("headline", {}).get("verdict")
    body_keys = ("what_happened", "why_important", "watch_next", "one_liner")
    if headline_v == "pass":
        for key in body_keys:
            if fields.get(key, {}).get("verdict") == "hard_fail":
                overall = "hard_fail"
                fields[key]["signals"] = list(fields[key].get("signals") or []) + [
                    "mixed_ko_headline_non_ko_body"
                ]
                break
    return {"overall": overall, "fields": fields}


def language_hard_fail_issues(story: dict[str, Any]) -> list[str]:
    if target_language() != "ko":
        return []
    assessment = assess_story_language(story)
    issues: list[str] = []
    for key, meta in (assessment.get("fields") or {}).items():
        if meta.get("verdict") == "hard_fail":
            sig = ",".join((meta.get("signals") or [])[:4]) or "unknown"
            issues.append(f"{key}:language:hard_fail:{sig}")
    return sorted(set(issues))


def _language_issues(fields: dict[str, str]) -> list[str]:
    lang = target_language()
    issues: list[str] = []

    for key, value in fields.items():
        if not value:
            continue
        stats = _char_stats(value)
        if lang == "ko":
            if stats["hangul_ratio"] < 0.45:
                issues.append(f"{key}:language:not_enough_target_ko")
            if stats["han_ratio"] > 0.20:
                issues.append(f"{key}:language:disallowed_han_dominant")
        elif lang == "en":
            if stats["latin_ratio"] < 0.55:
                issues.append(f"{key}:language:not_enough_target_en")
            if stats["han_ratio"] > 0.10 or stats["hangul_ratio"] > 0.10:
                issues.append(f"{key}:language:disallowed_non_en_dominant")
        elif lang == "ja":
            if stats["jp_ratio"] < 0.35:
                issues.append(f"{key}:language:not_enough_target_ja")
            if stats["hangul_ratio"] > 0.10:
                issues.append(f"{key}:language:disallowed_hangul_dominant")
        elif lang == "zh":
            if stats["han_ratio"] < 0.45:
                issues.append(f"{key}:language:not_enough_target_zh")
            if stats["hangul_ratio"] > 0.10:
                issues.append(f"{key}:language:disallowed_hangul_dominant")
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
