"""Final publish guard before external Instagram/R2 calls."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from editorial.config import minimum_story_count
from publish.config import PublishConfig
from publish.instagram import caption_from_briefing
from story_quality import assess_korean_text, language_hard_fail_issues, target_language


def editorial_llm_reviewer_enabled() -> bool:
    """Fail-closed: unset/empty/unknown → disabled (live requires explicit 1)."""
    return os.getenv("EDITORIAL_LLM_REVIEWER", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def assert_publish_ready(
    briefing: dict[str, Any],
    *,
    png_paths: list[Path] | None = None,
    live: bool = False,
    editorial_decision: dict[str, Any] | None = None,
    preflight: dict[str, Any] | None = None,
    markdown_text: str = "",
) -> dict[str, Any]:
    """Return {ok, blockers} for autonomous publish boundary."""
    blockers: list[str] = []
    decision = editorial_decision or {}
    stories = [s for s in (briefing.get("stories") or []) if isinstance(s, dict)]

    if live:
        if decision.get("decision") != "publish":
            blockers.append(f"editorial:{decision.get('decision', 'missing')}")
        min_n = minimum_story_count()
        if len(stories) < min_n:
            blockers.append(f"minimum_story_count:{len(stories)}<{min_n}")

        if target_language() == "ko":
            for i, story in enumerate(stories):
                for issue in language_hard_fail_issues(story):
                    blockers.append(f"story_{i}:{issue}")

            caption = (briefing.get("instagram_post") or caption_from_briefing(briefing) or "").strip()
            cap_verdict, cap_signals = assess_korean_text(caption)
            if cap_verdict == "hard_fail":
                blockers.append(
                    f"caption:language:hard_fail:{','.join(cap_signals[:3]) or 'unknown'}"
                )

            md_sample = (markdown_text or briefing.get("blog_markdown") or "").strip()
            if md_sample:
                md_verdict, md_signals = assess_korean_text(md_sample[:4000])
                if md_verdict == "hard_fail":
                    blockers.append(
                        f"markdown:language:hard_fail:{','.join(md_signals[:3]) or 'unknown'}"
                    )

    cfg = PublishConfig.from_env()
    paths = list(png_paths or [])

    if live:
        if not editorial_llm_reviewer_enabled():
            blockers.append("EDITORIAL_LLM_REVIEWER required for autonomous live")
        if preflight is not None and not preflight.get("ok"):
            blockers.append("preflight_failed")
        if cfg.publish_cards and not cfg.package_only:
            if not cfg.r2_configured:
                blockers.append("r2_not_configured")
            if not cfg.instagram_configured:
                blockers.append("instagram_not_configured")
            n = len(paths)
            if n < 2 or n > 10:
                blockers.append(f"card_png_count:{n}")

    for path in paths:
        if not Path(path).is_file():
            blockers.append(f"card_png_missing:{path}")

    return {"ok": not blockers, "blockers": blockers}


def write_publish_guard(run_dir: Path, result: dict[str, Any]) -> Path:
    path = run_dir / "publish_guard.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
