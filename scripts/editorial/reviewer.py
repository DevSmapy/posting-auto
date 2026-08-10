"""LLM + deterministic Reviewer. Consistency/quality vs sources — not global fact-check."""

from __future__ import annotations

import json
import re
from typing import Any

from editorial.config import ollama_host, ollama_model
from editorial.validator import quality_gate_story

_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _deterministic_review(story: dict[str, Any], sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    issues = quality_gate_story(story)
    generic = any(i.startswith("fallback_phrase:") or i == "heuristic_fallback" for i in issues)
    shallow = any(i.endswith(":too_shallow") for i in issues)
    dup = any("duplicate" in i or "repetition" in i or "equals_" in i for i in issues)
    if story.get("_entity_corruption"):
        issues.append("entity_corruption")
    if story.get("_unsupported_claim"):
        issues.append("unsupported_interpretation")

    if any(i.endswith(":empty") for i in issues) or generic:
        decision = "reject" if generic and shallow else "revise"
    elif shallow or dup or story.get("_entity_corruption") or story.get("_unsupported_claim"):
        decision = "revise"
    elif issues:
        decision = "revise"
    else:
        decision = "pass"

    if decision == "pass" and sources:
        # Light source-title overlap check
        title_blob = " ".join(str(s.get("title") or "") for s in sources).casefold()
        headline = str(story.get("headline") or "").casefold()
        if headline and title_blob and headline[:8] not in title_blob and len(headline) > 12:
            # not hard fail — warn only
            pass

    return {
        "source_consistency": "fail" if decision == "reject" else ("warn" if issues else "pass"),
        "analysis_depth": "fail" if shallow else "pass",
        "language_quality": "fail" if any("language:" in i for i in issues) else "pass",
        "generic_fallback_detected": generic,
        "unsupported_claims": [],
        "duplication_detected": dup,
        "risk_flags": list(issues),
        "decision": decision,
        "revision_instructions": [
            f"Fix: {i}" for i in issues[:8]
        ],
        "reviewer": "deterministic",
    }


def review_story(
    story: dict[str, Any],
    *,
    sources: list[dict[str, Any]] | None = None,
    use_llm: bool = False,
) -> dict[str, Any]:
    base = _deterministic_review(story, sources)
    if not use_llm or base["decision"] == "pass":
        return base
    try:
        llm = _llm_review(story, sources or [], base)
        if isinstance(llm, dict) and llm.get("decision") in {"pass", "revise", "reject"}:
            llm.setdefault("reviewer", "ollama")
            # Never override deterministic hard reject on generic fallback
            if base.get("generic_fallback_detected") and llm["decision"] == "pass":
                llm["decision"] = "revise"
                llm.setdefault("risk_flags", []).append("deterministic_override:generic_fallback")
            return llm
    except Exception as exc:  # noqa: BLE001
        base["llm_error"] = str(exc)
    return base


def _llm_review(
    story: dict[str, Any],
    sources: list[dict[str, Any]],
    prior: dict[str, Any],
) -> dict[str, Any]:
    import requests

    payload = {
        "model": ollama_model(),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an editorial reviewer for Korean economy briefings. "
                    "Judge draft vs provided sources for consistency and usefulness. "
                    "You are NOT a global fact-checker. "
                    "Return JSON with keys: source_consistency, analysis_depth, "
                    "language_quality (pass|warn|fail each), generic_fallback_detected (bool), "
                    "unsupported_claims (array), duplication_detected (bool), risk_flags (array), "
                    "decision (pass|revise|reject), revision_instructions (array of strings)."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"story": story, "sources": sources[:3], "deterministic": prior},
                    ensure_ascii=False,
                ),
            },
        ],
    }
    resp = requests.post(f"{ollama_host().rstrip('/')}/api/chat", json=payload, timeout=180)
    resp.raise_for_status()
    raw = resp.json().get("message", {}).get("content") or "{}"
    match = _JSON_RE.search(raw)
    return json.loads(match.group(0) if match else raw)


def review_briefing(
    briefing: dict[str, Any],
    *,
    sources: list[dict[str, Any]] | None = None,
    use_llm: bool = False,
) -> dict[str, Any]:
    stories = list(briefing.get("stories") or [])
    results = []
    for i, story in enumerate(stories):
        if not isinstance(story, dict):
            results.append({"index": i, "decision": "reject", "risk_flags": ["invalid_story"]})
            continue
        src = sources
        if sources and i < len(sources):
            src = [sources[i]]
        results.append({"index": i, **review_story(story, sources=src, use_llm=use_llm)})
    decisions = [r.get("decision") for r in results]
    if any(d == "reject" for d in decisions):
        overall = "reject"
    elif any(d == "revise" for d in decisions):
        overall = "revise"
    else:
        overall = "pass"
    return {"overall": overall, "stories": results}
