"""Minimal Tistory draft spike via Playwright (experimental).

Storage state and passwords must stay outside the repository.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Spike A: Tistory draft via Playwright")
    parser.add_argument(
        "--storage-state",
        default=os.getenv("TISTORY_STORAGE_STATE", ""),
        help="Path to Playwright storage_state JSON (outside repo)",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("TISTORY_BLOG_URL", ""),
        help="Tistory new-post or manage URL",
    )
    parser.add_argument(
        "--dry-check",
        action="store_true",
        help="Validate env/paths only; do not launch browser",
    )
    parser.add_argument(
        "--publish-draft",
        action="store_true",
        help="Attempt draft save (not public publish)",
    )
    parser.add_argument("--title", default="[Spike] Posting Auto draft test")
    parser.add_argument("--body", default="Spike A body — safe draft only.")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    state = Path(args.storage_state).expanduser() if args.storage_state else None
    print("==> Spike A Tistory Playwright")
    print(f"   storage_state={state}")
    print(f"   url={args.url or '(unset)'}")

    if not state or not str(state):
        print("!! Set TISTORY_STORAGE_STATE to a file outside the repo.", file=sys.stderr)
        return 2
    if state.exists() and "포스팅 자동화" in str(state.resolve()):
        print("!! Refusing storage state inside the repository.", file=sys.stderr)
        return 2
    if args.dry_check:
        print(f"   state_exists={state.is_file()}")
        print("   dry-check ok (no browser)")
        print("   Install: uv pip install playwright && playwright install chromium")
        return 0 if state.is_file() and args.url else 1

    if not state.is_file():
        print(f"!! Missing storage state: {state}", file=sys.stderr)
        return 2
    if not args.url:
        print("!! Set TISTORY_BLOG_URL", file=sys.stderr)
        return 2
    if not args.publish_draft:
        print("!! Pass --publish-draft to attempt a draft save (still experimental).")
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("!! playwright not installed. uv pip install playwright", file=sys.stderr)
        return 2

    # Selectors are intentionally isolated; Tistory UI changes often.
    # ponytail: brittle DOM selectors — upgrade via TistoryEditorAdapter when promoting.
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(storage_state=str(state))
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=60_000)
        # Best-effort fill; adapters will harden after live spike.
        for sel in ("input[name='title']", "#title", "textarea[name='title']"):
            loc = page.locator(sel)
            if loc.count():
                loc.first.fill(args.title)
                break
        for sel in ("textarea[name='content']", ".CodeMirror", "[contenteditable='true']"):
            loc = page.locator(sel)
            if loc.count():
                try:
                    loc.first.fill(args.body)
                except Exception:
                    loc.first.click()
                    page.keyboard.type(args.body)
                break
        print(f"   page_url={page.url}")
        print("   filled best-effort; verify draft manually / extend selectors after UI inspect")
        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
