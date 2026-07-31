#!/usr/bin/env python3
"""Resume a parked draft gate from disk artifacts.

Usage:
  uv run python scripts/resume_draft.py output/<run_id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

from mvp_pipeline import resume_parked_draft  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Resume parked draft gate")
    parser.add_argument(
        "run_dir",
        type=Path,
        help="output/<run_id> (or absolute path)",
    )
    args = parser.parse_args()
    run_dir = args.run_dir
    if not run_dir.is_absolute():
        run_dir = (ROOT / run_dir).resolve()
    else:
        run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        print(f"!! not a directory: {run_dir}", file=sys.stderr)
        return 1
    return resume_parked_draft(run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
