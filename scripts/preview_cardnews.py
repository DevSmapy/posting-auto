#!/usr/bin/env python3
"""Local MVP: assemble sample card news → HTML / PNG / Instagram caption files.

Usage (from repo root):
  python scripts/preview_cardnews.py
  python scripts/preview_cardnews.py --bundle why_cause_impact
  python scripts/preview_cardnews.py --list-bundles

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

from cards import (  # noqa: E402
    CardAssembler,
    CardFormatConfig,
    CardRenderer,
    NarrativeAssembler,
    get_bundle,
    list_bundles,
    recommend_for_economy_society,
)
from cards.fixtures import sample_related_keywords, sample_stories  # noqa: E402
from cards.fixtures_why_cause_impact import (  # noqa: E402
    CAPTION_HOOK,
    why_cause_impact_example,
    why_cause_impact_keywords,
)


def _print_bundles() -> None:
    picked = recommend_for_economy_society()
    print("Available template bundles:\n")
    for b in list_bundles():
        mark = " ← recommended (economy/society)" if b.id == picked.id else ""
        badge = f" [{b.badge}]" if b.badge else ""
        print(f"  {b.index}. {b.id} — {b.name_ko}{badge}{mark}")
        print(f"     cards={b.card_count}  fit={b.fit_score_economy_society}/5")
        print(f"     {b.purpose}")
        print()


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
    parser.add_argument(
        "--bundle",
        default="why_cause_impact",
        help=(
            "Template bundle id (default: why_cause_impact). "
            "Use 'daily_briefing' for cover+stories+disclaimer sample."
        ),
    )
    parser.add_argument(
        "--list-bundles",
        action="store_true",
        help="List stored template bundles and exit",
    )
    args = parser.parse_args()

    if args.list_bundles:
        _print_bundles()
        return 0

    tz = ZoneInfo("Asia/Seoul")
    now = datetime.now(tz)
    config = CardFormatConfig.from_env()

    if args.bundle == "daily_briefing":
        bundle_meta = get_bundle("daily_briefing")
        card_bundle = CardAssembler(config).assemble(
            sample_stories(),
            now,
            related_keywords=sample_related_keywords(),
        )
        # annotate for export meta
        from cards.models import CardBundle as CB

        card_bundle = CB(
            slides=card_bundle.slides,
            post=card_bundle.post,
            related_keywords=card_bundle.related_keywords,
            template_id=bundle_meta.id,
        )
    else:
        template = get_bundle(args.bundle)
        if template.id != "why_cause_impact":
            print(
                f"!! No fixture fill for {template.id!r} yet — "
                "using why_cause_impact example structure only if counts match."
            )
        filled = why_cause_impact_example()
        if len(filled) != len(template.slides):
            raise SystemExit(
                f"fixture slides={len(filled)} != template {template.id} "
                f"slides={len(template.slides)}. Use --bundle why_cause_impact."
            )
        card_bundle = NarrativeAssembler(config).assemble(
            filled,
            now,
            bundle=template,
            related_keywords=why_cause_impact_keywords(),
            caption_hook=CAPTION_HOOK,
        )

    renderer = CardRenderer(config)
    targets = [args.out]
    if args.artifacts:
        targets.append(args.artifacts)

    png_ok = False
    for out_dir in targets:
        print(f"==> export → {out_dir}  (template={card_bundle.template_id})")
        result = renderer.export(card_bundle, out_dir, render_png=not args.no_png)
        png_list = result.get("png") or []
        if png_list:
            png_ok = True
        print(f"   slides: {len(card_bundle.slides)}")
        print(f"   caption chars: {len(card_bundle.post.full_text)}")
        print(f"   instagram_post: {result['instagram_post']}")

    print()
    print("--- Instagram post preview ---")
    print(card_bundle.post.full_text)
    print("--- end ---")

    if args.no_png:
        return 0
    if not png_ok:
        print(
            "\n!! PNG not produced. HTML/caption are ready. "
            "Start browserless (`docker compose up -d browserless`) "
            "or install Chrome, then re-run."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
