"""Conditional Korean post-edit for economy briefing stories.

Only story text fields are inspected, so the intentional headings, bullets and
section icons of ``briefing.md`` are structurally out of scope. A story is sent
to the existing polish LLM at most once, and only when a rule fires; a fidelity
gate rolls the story back if the rewrite drifted.

The rule set is inspired by the im-not-ai project (MIT,
https://github.com/epoko77-ai/im-not-ai). No code or rule text was copied.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

#: Story fields the post-edit is allowed to read and rewrite.
STORY_FIELDS: tuple[str, ...] = (
    "headline",
    "what_happened",
    "why_important",
    "watch_next",
    "one_liner",
)

#: Never rewritten, and compared verbatim before/after.
ANCHOR_FIELDS: tuple[str, ...] = ("source_name", "source_url")

#: A rewrite past this character-bigram change rate is a rewrite, not a polish.
MAX_CHANGE_RATE = 0.30

_WS_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_QUOTE_RE = re.compile(r"[\"“”'‘’]([^\"“”'‘’]{2,})[\"“”'‘’]")
_DIRECTION_RE = re.compile(
    r"(급등|급락|상승|하락|인상|인하|동결|증가|감소|확대|축소|강세|약세)"
)
_PROPER_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9.&'-]*"
    r"|금통위|한은|연준|코스피|코스닥|나스닥"
    r"|[가-힣]{2,}(?:은행|공사|위원회|전자|자동차|증권|거래소)"
)
_FACT_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?%?[가-힣]{0,4}\s*"
    r"(?:인상|인하|동결|유지|상승|하락|증가|감소|확대|축소)"
)
_CONNECTIVES = ("또한", "그러나", "하지만", "따라서", "이에 따라", "한편", "그리고")


def _text(story: Mapping[str, Any]) -> str:
    return _WS_RE.sub(" ", " ".join(str(story.get(f) or "") for f in STORY_FIELDS)).strip()


def _count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text))


# --- diagnosis ---------------------------------------------------------------


def _monotone_ending(story: Mapping[str, Any]) -> bool:
    """Same 5-character ending in 3+ fields: 합니다체가 아니라 단조로움 신호."""
    endings = [
        str(story.get(f) or "").strip().rstrip(".")[-5:]
        for f in STORY_FIELDS
        if len(str(story.get(f) or "").strip()) >= 6
    ]
    counts = Counter(e for e in endings if e)
    return any(n >= 3 for n in counts.values())


def _repeated_connective(text: str) -> bool:
    return any(text.count(word) >= 2 for word in _CONNECTIVES)


#: rule id -> predicate over the joined story text.
_TEXT_RULES: dict[str, Callable[[str], bool]] = {
    # 이중 피동
    "double_passive": lambda t: bool(
        re.search(r"(되어지|되어졌|보여지|불려지|쓰여지|나뉘어지|모아지)", t)
    ),
    # 번역투: 행위자 "에 의해 ~되다" (되다 활용형은 되/된/됩/됐로 갈린다)
    "agent_by_phrase": lambda t: bool(re.search(r"에 의해\s*\S*?(되|된|됩|됐|받)", t)),
    # 번역투: have -> 가지고 있다
    "have_translationese": lambda t: bool(re.search(r"(가지고|갖고)\s*있", t)),
    # 번역투: "A의 B의 C" 소유격 연쇄
    "possessive_chain": lambda t: bool(re.search(r"\S+의\s*\S+의\s*\S+의", t)),
    "about_overuse": lambda t: _count(r"에 대(한|해|하여)", t) >= 3,
    "plural_overuse": lambda t: _count(r"들[이은을를의과와]", t) >= 3,
    "progressive_overuse": lambda t: _count(r"되고\s*있", t) >= 3,
    # 이중 완곡: 추측 어미 두 겹
    "double_hedge": lambda t: bool(
        re.search(r"(수\s*있을\s*것으로|것으로\s*예상될|가능성이\s*있을\s*수|것으로\s*보일\s*수)", t)
    ),
    # 상투적 의의 과장
    "significance_cliche": lambda t: bool(
        re.search(r"(큰\s*의미를\s*(갖|가지)|의미가\s*크|시사하는\s*바가\s*크|주목할\s*만한\s*대목)", t)
    ),
    # 상투적 마무리
    "closing_cliche": lambda t: bool(
        re.search(r"(귀추가\s*주목|이목이\s*집중|관심이\s*모아지)", t)
    ),
    "intensifier_overuse": lambda t: _count(r"(매우|굉장히|정말|실로|그야말로)", t) >= 2,
    "repeated_connective": _repeated_connective,
}


def diagnose_story(story: Mapping[str, Any]) -> list[str]:
    """Return the rule ids that fired for one story. Empty means leave it alone."""
    text = _text(story)
    fired = [rule for rule, predicate in _TEXT_RULES.items() if predicate(text)]
    if _monotone_ending(story):
        fired.append("monotone_ending")
    return sorted(fired)


# --- fidelity gate -----------------------------------------------------------


def _bigrams(text: str) -> list[str]:
    flat = _WS_RE.sub("", text)
    return [flat[i : i + 2] for i in range(len(flat) - 1)]


def bigram_change_rate(before: str, after: str) -> float:
    """0.0 = identical, 1.0 = nothing in common (character bigram multisets)."""
    left, right = Counter(_bigrams(before)), Counter(_bigrams(after))
    total = max(sum(left.values()), sum(right.values()))
    if not total:
        return 0.0
    return 1.0 - sum((left & right).values()) / total


def fidelity_issues(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Protected content that the polish LLM was not allowed to touch."""
    issues: list[str] = []
    for field in ANCHOR_FIELDS:
        if str(before.get(field) or "") != str(after.get(field) or ""):
            issues.append(f"{field}:changed")

    before_text, after_text = _text(before), _text(after)
    if Counter(_NUMBER_RE.findall(before_text)) != Counter(_NUMBER_RE.findall(after_text)):
        issues.append("numbers:changed")
    if Counter(_QUOTE_RE.findall(before_text)) != Counter(_QUOTE_RE.findall(after_text)):
        issues.append("quotes:changed")
    if Counter(_DIRECTION_RE.findall(before_text)) != Counter(
        _DIRECTION_RE.findall(after_text)
    ):
        issues.append("direction:changed")
    if Counter(_PROPER_RE.findall(before_text)) != Counter(_PROPER_RE.findall(after_text)):
        issues.append("proper_nouns:changed")
    if Counter(_FACT_RE.findall(before_text)) != Counter(_FACT_RE.findall(after_text)):
        issues.append("facts:changed")
    if any(not str(after.get(field) or "").strip() for field in STORY_FIELDS):
        issues.append("fields:emptied")
    return issues


def gate_rewrite(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    max_change_rate: float = MAX_CHANGE_RATE,
) -> tuple[bool, list[str], float]:
    """Accept or reject a rewrite. The gate never edits text itself."""
    rate = bigram_change_rate(_text(before), _text(after))
    issues = fidelity_issues(before, after)
    if rate > max_change_rate:
        issues.append(f"change_rate:{rate:.2f}")
    return (not issues), issues, rate


# --- orchestration -----------------------------------------------------------

PolishFn = Callable[[dict[str, Any], list[str]], Mapping[str, Any]]


def _merge_polished(
    original: Mapping[str, Any], polished: Mapping[str, Any]
) -> dict[str, Any]:
    """Take only the text fields from the rewrite; anchors stay as generated."""
    merged = dict(original)
    for field in STORY_FIELDS:
        value = str(polished.get(field) or "").strip()
        if value:
            merged[field] = value
    return merged


def humanize_stories(
    stories: Sequence[Mapping[str, Any]],
    *,
    polish: PolishFn | None = None,
    run_dir: Path | None = None,
    max_change_rate: float = MAX_CHANGE_RATE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Diagnose every story, polish only the flagged ones, roll back on drift.

    ``polish=None`` (heuristic mode) diagnoses without spending an LLM call.
    """
    out: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    for index, story in enumerate(stories):
        issues = diagnose_story(story)
        record: dict[str, Any] = {
            "index": index,
            "headline": str(story.get("headline") or ""),
            "issues": issues,
            "applied": False,
            "change_rate": 0.0,
            "rollback_reason": [],
        }
        if not issues or polish is None:
            if issues and polish is None:
                record["rollback_reason"] = ["polish:disabled"]
            out.append(dict(story))
            records.append(record)
            continue

        try:
            rewritten = _merge_polished(story, polish(dict(story), list(issues)))
        except Exception as exc:  # noqa: BLE001
            record["rollback_reason"] = [f"polish:failed:{exc}"]
            out.append(dict(story))
            records.append(record)
            continue

        ok, gate_issues, rate = gate_rewrite(
            story, rewritten, max_change_rate=max_change_rate
        )
        record["change_rate"] = round(rate, 4)
        if ok:
            record["applied"] = True
            record["remaining_issues"] = diagnose_story(rewritten)
            out.append(rewritten)
        else:
            record["rollback_reason"] = gate_issues
            out.append(dict(story))
        records.append(record)

    result = {
        "max_change_rate": max_change_rate,
        "polish_enabled": polish is not None,
        "flagged": sum(1 for r in records if r["issues"]),
        "applied": sum(1 for r in records if r["applied"]),
        "rolled_back": sum(1 for r in records if r["rollback_reason"]),
        "stories": records,
    }
    if run_dir is not None:
        (Path(run_dir) / "humanize_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return out, result


def rule_ids() -> list[str]:
    return sorted([*_TEXT_RULES, "monotone_ending"])
