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

RewriteFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


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
