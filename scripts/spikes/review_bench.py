"""Spike C: run review fixtures; optional live Ollama bench."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from editorial.reviewer import review_story  # noqa: E402
from editorial.validator import quality_gate_story  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "review"


def main() -> int:
    live = os.getenv("REVIEW_SPIKE_LIVE", "").lower() in {"1", "true", "yes"}
    rows = []
    for path in sorted(FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        story = data["story"]
        expect = data.get("expect_decision")
        t0 = time.perf_counter()
        gate = quality_gate_story(story)
        review = review_story(story, sources=data.get("sources") or [], use_llm=live)
        ms = (time.perf_counter() - t0) * 1000
        ok = expect is None or review.get("decision") == expect
        rows.append(
            {
                "fixture": path.name,
                "expect": expect,
                "decision": review.get("decision"),
                "ok": ok,
                "gate_issues": len(gate),
                "ms": round(ms, 1),
                "reviewer": review.get("reviewer"),
            }
        )
        print(
            f"{path.name}: decision={review.get('decision')} "
            f"expect={expect} ok={ok} ms={ms:.0f}"
        )
    passed = sum(1 for r in rows if r["ok"])
    print(f"==> {passed}/{len(rows)} fixture decisions matched")
    if live:
        print("   live Ollama path enabled")
    else:
        print("   deterministic reviewer only (set REVIEW_SPIKE_LIVE=1 for Ollama)")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
