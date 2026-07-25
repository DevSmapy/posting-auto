#!/usr/bin/env python3
"""Local MVP: assemble sample card news → HTML / PNG / Instagram caption files.

Usage (from repo root):
  python scripts/preview_cardnews.py
  python scripts/preview_cardnews.py --out output/cardnews-preview --no-png

Does not require Ollama, R2, or Instagram credentials.
PNG needs Browserless (`docker compose up -d browserless`) or local Chrome.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

from cards import CardAssembler, CardFormatConfig, CardRenderer  # noqa: E402
from cards.fixtures import sample_related_keywords, sample_stories  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview card news locally (MVP)")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "output" / "cardnews-preview",
        help="Output directory (default: output/cardnews-preview)",
    )
    parser.add_argument(
        "--no-png",
        action="store_true",
        help="Write HTML + caption only (skip screenshot)",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=None,
        help="Optional second output dir (e.g. /opt/cursor/artifacts/cardnews-preview)",
    )
    args = parser.parse_args()

    tz = ZoneInfo("Asia/Seoul")
    now = datetime.now(tz)
    config = CardFormatConfig.from_env()
    stories = sample_stories()
    keywords = sample_related_keywords()
    bundle = CardAssembler(config).assemble(stories, now, related_keywords=keywords)
    renderer = CardRenderer(config)

    targets = [args.out]
    if args.artifacts:
        targets.append(args.artifacts)

    png_ok = False
    for out_dir in targets:
        print(f"==> export → {out_dir}")
        result = renderer.export(bundle, out_dir, render_png=not args.no_png)
        png_list = result.get("png") or []
        if png_list:
            png_ok = True
        print(f"   slides: {len(bundle.slides)}")
        print(f"   caption chars: {len(bundle.post.full_text)}")
        print(f"   instagram_post: {result['instagram_post']}")

    print()
    print("--- Instagram post preview ---")
    print(bundle.post.full_text)
    print("--- end ---")

    if args.no_png:
        return 0
    if not png_ok:
        print(
            "\n!! PNG not produced. HTML/caption are ready. "
            "Start browserless (`docker compose up -d browserless`) "
            "or install Chrome, then re-run."
        )
        return 0  # assembly MVP still succeeded
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
