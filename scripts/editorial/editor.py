"""Final editorial publish decision: hard gates + reviewer + optional editor LLM."""

from __future__ import annotations

from typing import Any

from editorial.config import minimum_story_count


def editor_decide(
    *,
    briefing: dict[str, Any],
    validation: dict[str, Any] | None,
    review: dict[str, Any] | None,
    revision_count: int = 0,
) -> dict[str, Any]:
    stories = [s for s in (briefing.get("stories") or []) if isinstance(s, dict)]
    excluded: list[int] = []
    risk: list[str] = []

    if validation and not validation.get("ok", True):
        excluded.extend(int(i) for i in validation.get("hard_fail_indices") or [])
        risk.append("validator_hard_fail")

    if review:
        overall = review.get("overall")
        if overall == "reject":
            return {
                "decision": "reject",
                "reason": "review_reject",
                "excluded_story_ids": list(range(len(stories))),
                "risk_flags": ["review_reject"],
            }
        for item in review.get("stories") or []:
            if item.get("decision") == "reject":
                excluded.append(int(item.get("index", -1)))
                risk.append(f"story_{item.get('index')}_reject")

    excluded = sorted({i for i in excluded if i >= 0})
    remaining = [s for i, s in enumerate(stories) if i not in excluded]
    min_n = minimum_story_count()
    if len(remaining) < min_n:
        return {
            "decision": "reject",
            "reason": f"minimum_story_count:{len(remaining)}<{min_n}",
            "excluded_story_ids": excluded,
            "risk_flags": risk + ["below_minimum_stories"],
        }

    # Rebuild briefing stories if exclusions
    if excluded:
        briefing = dict(briefing)
        briefing["stories"] = remaining
        risk.append("stories_excluded")

    return {
        "decision": "publish",
        "reason": "hard_gates_pass",
        "excluded_story_ids": excluded,
        "risk_flags": risk,
        "revision_count": revision_count,
        "story_count": len(remaining),
        "briefing": briefing,
    }
