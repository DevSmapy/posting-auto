"""Render human-readable editorial reports from editorial_result dicts."""

from __future__ import annotations

from typing import Any


def render_editorial_report(
    result: dict[str, Any],
    *,
    run_id: str = "",
) -> str:
    """Build markdown for Validator / Reviewer / Editor judgments."""
    decision = result.get("editor_decision") or {}
    review = result.get("review") or {}
    validation = result.get("validation") or {}
    history = list(result.get("revision_history") or [])
    stories = list(review.get("stories") or [])
    rid = run_id or "unknown"

    lines: list[str] = [
        f"# Editorial Report — {rid}",
        "",
        "## Verdict",
        "",
        f"- **Editor decision:** `{decision.get('decision', 'n/a')}`",
        f"- **Reason:** {decision.get('reason', 'n/a')}",
        f"- **Story count:** {decision.get('story_count', 'n/a')}",
        f"- **Revision count:** {result.get('revision_count', 0)}",
        f"- **Excluded story ids:** {decision.get('excluded_story_ids') or []}",
        f"- **Excluded reasons:** {decision.get('excluded_reasons') or []}",
        f"- **Risk flags:** {decision.get('risk_flags') or []}",
        "",
        "## Pipeline roles",
        "",
        f"- **Validator:** ok=`{validation.get('ok')}` "
        f"hard_fail_indices=`{validation.get('hard_fail_indices') or []}`",
        f"- **Reviewer:** overall=`{review.get('overall', 'n/a')}` "
        f"stories={len(stories)}",
        f"- **Editor:** `{decision.get('decision', 'n/a')}` — {decision.get('reason', '')}",
        "",
        "## Per-story",
        "",
    ]

    if not stories:
        lines.append("_No story review rows._")
        lines.append("")
    else:
        for item in stories:
            idx = item.get("index", "?")
            lines.append(f"### Story {idx}")
            lines.append("")
            lines.append(f"- **decision:** `{item.get('decision', 'n/a')}`")
            lines.append(f"- **reviewer:** `{item.get('reviewer', 'n/a')}`")
            lines.append(f"- **risk_flags:** {item.get('risk_flags') or []}")
            instr = item.get("revision_instructions") or []
            if instr:
                lines.append("- **revision_instructions:**")
                for tip in instr:
                    lines.append(f"  - {tip}")
            else:
                lines.append("- **revision_instructions:** _(none)_")
            lines.append("")

    lines.extend(["## Revision history", ""])
    if not history:
        lines.append("_No revision rounds._")
        lines.append("")
    else:
        for row in history:
            if "stopped" in row:
                lines.append(f"- stopped: `{row.get('stopped')}`")
                continue
            lines.append(
                f"- revision={row.get('revision')}: "
                f"validation_ok=`{row.get('validation_ok')}` "
                f"review_overall=`{row.get('review_overall')}` "
                f"hard_fail_indices=`{row.get('hard_fail_indices') or []}`"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_editorial_report(result: dict[str, Any], run_dir: Any, *, run_id: str = "") -> Any:
    """Write editorial_report.md next to editorial_result.json. Returns path."""
    from pathlib import Path

    path = Path(run_dir) / "editorial_report.md"
    rid = run_id or Path(run_dir).name
    path.write_text(
        render_editorial_report(result, run_id=rid),
        encoding="utf-8",
    )
    return path
