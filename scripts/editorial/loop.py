"""Bounded Writer → Validator → Reviewer → revise loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from editorial.config import max_revision_count
from editorial.editor import editor_decide
from editorial.report import write_editorial_report
from editorial.reviewer import review_briefing
from editorial.validator import quality_gate_briefing
from monitor import emit

RewriteFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _story_snapshot(
    briefing: dict[str, Any],
    review: dict[str, Any],
    *,
    excluded_ids: list[Any] | None = None,
) -> list[dict[str, Any]]:
    review_map: dict[int, str] = {}
    for item in review.get("stories") or []:
        if isinstance(item, dict) and "index" in item:
            try:
                review_map[int(item["index"])] = str(item.get("decision") or "")
            except (TypeError, ValueError):
                continue
    excluded: set[int] = set()
    for idx in excluded_ids or []:
        try:
            excluded.add(int(idx))
        except (TypeError, ValueError):
            continue
    rows: list[dict[str, Any]] = []
    for i, story in enumerate(briefing.get("stories") or []):
        headline = str(story.get("headline") or "") if isinstance(story, dict) else ""
        status = review_map.get(i, "")
        if i in excluded and status not in {"reject", "revise"}:
            status = status or "excluded"
        rows.append({"index": i, "headline": headline, "status": status})
    return rows


def run_editorial_loop(
    briefing: dict[str, Any],
    *,
    sources: list[dict[str, Any]] | None = None,
    rewrite_story: RewriteFn | None = None,
    use_llm_reviewer: bool = False,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    current = briefing
    revision_count = 0
    max_rev = max_revision_count()
    validation: dict[str, Any] = {"ok": True, "hard_fail_indices": [], "story_results": []}
    review: dict[str, Any] = {"overall": "pass", "stories": []}
    emit(run_dir=run_dir, stage="REVIEW", event="review started")

    while True:
        validation = quality_gate_briefing(current)
        review = review_briefing(current, sources=sources, use_llm=use_llm_reviewer)
        history.append(
            {
                "revision": revision_count,
                "validation_ok": validation.get("ok"),
                "review_overall": review.get("overall"),
                "hard_fail_indices": list(validation.get("hard_fail_indices") or []),
            }
        )
        emit(
            run_dir=run_dir,
            stage="REVIEW",
            review_overall=review.get("overall"),
            revision_count=revision_count,
            stories=_story_snapshot(current, review),
            event=f"review overall={review.get('overall')} revision={revision_count}",
        )

        ok = bool(validation.get("ok")) and review.get("overall") == "pass"
        if ok:
            break
        if revision_count >= max_rev or rewrite_story is None:
            if revision_count >= max_rev:
                history.append({"stopped": "max_revision_count"})
            elif rewrite_story is None:
                history.append({"stopped": "no_rewrite_fn"})
            break

        stories = list(current.get("stories") or [])
        review_stories = {
            int(s["index"]): s for s in review.get("stories") or [] if "index" in s
        }
        fail_idx = set(int(i) for i in (validation.get("hard_fail_indices") or []))
        for i, s in review_stories.items():
            if s.get("decision") in {"revise", "reject"}:
                fail_idx.add(i)
        if not fail_idx:
            break

        emit(
            run_dir=run_dir,
            stage="REVISE",
            review_overall=review.get("overall"),
            revision_count=revision_count,
            stories=_story_snapshot(current, review),
            event=f"revision requested stories={sorted(fail_idx)}",
        )
        new_stories: list[Any] = []
        for i, story in enumerate(stories):
            if i not in fail_idx or not isinstance(story, dict):
                new_stories.append(story)
                continue
            instr = review_stories.get(i) or {}
            try:
                rewritten = rewrite_story(story, instr)
                new_stories.append(rewritten if isinstance(rewritten, dict) else story)
            except Exception as exc:  # noqa: BLE001
                failed = dict(story)
                failed["_rewrite_error"] = str(exc)
                new_stories.append(failed)
        current = dict(current)
        current["stories"] = new_stories
        revision_count += 1

    decision = editor_decide(
        briefing=current,
        validation=validation,
        review=review,
        revision_count=revision_count,
    )
    out_briefing = decision.pop("briefing", current)
    emit(
        run_dir=run_dir,
        stage="EDITOR",
        review_overall=review.get("overall"),
        revision_count=revision_count,
        stories=_story_snapshot(
            current,
            review,
            excluded_ids=decision.get("excluded_story_ids"),
        ),
        event=f"editor {decision.get('decision')}",
    )
    result = {
        "validation": validation,
        "review": review,
        "revision_count": revision_count,
        "revision_history": history,
        "editor_decision": decision,
        "briefing": out_briefing,
    }
    if run_dir is not None:
        out = Path(run_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "editorial_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_editorial_report(result, out, run_id=out.name)
    return result
