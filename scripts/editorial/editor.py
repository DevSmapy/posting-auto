"""Final editorial publish decision: hard gates + reviewer + optional editor LLM."""

from __future__ import annotations

from typing import Any

from editorial.config import minimum_story_count


def _story_issues(validation: dict[str, Any] | None, index: int) -> list[str]:
    if not validation:
        return []
    for row in validation.get("story_results") or []:
        if int(row.get("index", -1)) == index:
            return list(row.get("issues") or [])
    return []


def editor_decide(
    *,
    briefing: dict[str, Any],
    validation: dict[str, Any] | None,
    review: dict[str, Any] | None,
    revision_count: int = 0,
) -> dict[str, Any]:
    # Keep validator/reviewer indices aligned with the original stories list
    # (including non-dict slots), then compact only valid remaining dicts.
    raw_stories = list(briefing.get("stories") or [])
    excluded: list[int] = []
    excluded_reasons: list[dict[str, Any]] = []
    risk: list[str] = []

    if validation and not validation.get("ok", True):
        for i in validation.get("hard_fail_indices") or []:
            idx = int(i)
            if idx not in excluded:
                excluded.append(idx)
                excluded_reasons.append(
                    {
                        "index": idx,
                        "reason": "validator_hard_fail",
                        "details": _story_issues(validation, idx),
                    }
                )
        risk.append("validator_hard_fail")

    if review:
        for item in review.get("stories") or []:
            if item.get("decision") == "reject":
                idx = int(item.get("index", -1))
                if idx >= 0 and idx not in excluded:
                    excluded.append(idx)
                    excluded_reasons.append(
                        {
                            "index": idx,
                            "reason": "reviewer_reject",
                            "details": list(item.get("risk_flags") or []),
                        }
                    )
                    risk.append(f"story_{idx}_reject")
            if item.get("llm_error") and item.get("decision") == "reject":
                risk.append(f"story_{item.get('index')}_llm_failed")

    excluded = sorted({i for i in excluded if i >= 0})
    remaining = [
        s
        for i, s in enumerate(raw_stories)
        if isinstance(s, dict) and i not in excluded
    ]
    min_n = minimum_story_count()
    if len(remaining) < min_n:
        return {
            "decision": "reject",
            "reason": f"minimum_story_count:{len(remaining)}<{min_n}",
            "excluded_story_ids": excluded,
            "excluded_reasons": excluded_reasons,
            "risk_flags": risk + ["below_minimum_stories"],
        }

    if not remaining:
        return {
            "decision": "reject",
            "reason": "no_stories_remaining",
            "excluded_story_ids": excluded,
            "excluded_reasons": excluded_reasons,
            "risk_flags": risk + ["empty_briefing"],
        }

    out_briefing = briefing
    if excluded:
        out_briefing = dict(briefing)
        out_briefing["stories"] = remaining
        risk.append("stories_excluded")

    return {
        "decision": "publish",
        "reason": "hard_gates_pass",
        "excluded_story_ids": excluded,
        "excluded_reasons": excluded_reasons,
        "risk_flags": risk,
        "revision_count": revision_count,
        "story_count": len(remaining),
        "briefing": out_briefing,
    }
