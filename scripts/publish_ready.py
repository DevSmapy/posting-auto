#!/usr/bin/env python3
"""CLI for final/publish_ready packages — package locally or publish via Graph.

Usage (from repo root):
  uv run python scripts/publish_ready.py package output/<run_id>
  uv run python scripts/publish_ready.py publish output/<run_id>

n8n: Execute Command with the same publish invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

from publish import (  # noqa: E402
    InstagramCarouselPublisher,
    PublishConfig,
    R2Uploader,
    ensure_publish_ready_from_run,
    load_publish_ready_package,
    write_publish_ready_package,
)

TZ = ZoneInfo("Asia/Seoul")


def _cmd_package(run_dir: Path) -> int:
    pkg = ensure_publish_ready_from_run(run_dir)
    print(f"package ready: {pkg.root}")
    print(f"  slides: {len(pkg.png_paths)}")
    print(f"  caption chars: {len(pkg.caption)}")
    return 0


def _cmd_publish(run_dir: Path, *, r2_prefix: str | None) -> int:
    try:
        pkg = load_publish_ready_package(run_dir)
    except FileNotFoundError:
        print("publish_ready missing — building package first")
        pkg = ensure_publish_ready_from_run(run_dir)

    n = len(pkg.png_paths)
    if n < 2 or n > 10:
        print(f"!! need 2-10 PNGs, got {n}", file=sys.stderr)
        return 1

    cfg = PublishConfig.from_env()
    # Force Graph path regardless of PUBLISH_MODE=package on the morning run.
    if not cfg.r2_configured:
        print("!! R2 not configured", file=sys.stderr)
        return 1
    if not cfg.instagram_configured:
        print("!! IG_USER_ID / META_ACCESS_TOKEN required", file=sys.stderr)
        return 1

    prefix = r2_prefix or f"briefs/{datetime.now(TZ).strftime('%Y-%m-%d')}/publish_ready"
    print(f"==> Upload R2 ({prefix})")
    urls = R2Uploader(cfg).upload(pkg.png_paths, prefix)
    (pkg.root / "image_urls.json").write_text(
        json.dumps(urls, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    publisher = InstagramCarouselPublisher(cfg)
    print("==> create_containers")
    creation_id = publisher.create_containers(urls, pkg.caption)
    print(f"   creation_id={creation_id}")
    (pkg.root / "creation_id.json").write_text(
        json.dumps({"creation_id": creation_id}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("==> media_publish")
    media_id = publisher.media_publish(creation_id)
    print(f"   ig media id: {media_id}")

    status = {
        "creation_id": creation_id,
        "ig_media_id": media_id,
        "image_urls": urls,
        "published_at": datetime.now(TZ).isoformat(),
    }
    (pkg.root / "publish_result.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="publish_ready package / Instagram publish")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pkg = sub.add_parser("package", help="Write or refresh final/publish_ready/")
    p_pkg.add_argument("run_dir", type=Path, help="output/<run_id> directory")

    p_pub = sub.add_parser("publish", help="R2 upload + Graph media_publish")
    p_pub.add_argument("run_dir", type=Path, help="output/<run_id> directory")
    p_pub.add_argument(
        "--r2-prefix",
        default="",
        help="R2 object prefix (default briefs/YYYY-MM-DD/publish_ready)",
    )

    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"!! not a directory: {run_dir}", file=sys.stderr)
        return 1

    if args.command == "package":
        return _cmd_package(run_dir)
    if args.command == "publish":
        prefix = (args.r2_prefix or "").strip() or None
        return _cmd_publish(run_dir, r2_prefix=prefix)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
