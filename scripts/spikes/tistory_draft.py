"""Minimal Tistory draft spike via Playwright (experimental).

Storage state and passwords must stay outside the repository.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _path_inside_repo(path: Path) -> bool:
    """True if path is the repo root or any path under it."""
    try:
        resolved = path.expanduser().resolve()
        root = REPO_ROOT.resolve()
        resolved.relative_to(root)
        return True
    except ValueError:
        return False


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
        help="Fill editor and click draft-save; fail if save is not confirmed",
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
    if _path_inside_repo(state):
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
    title_filled = False
    body_filled = False
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(storage_state=str(state))
        page = context.new_page()
        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=60_000)
            for sel in ("input[name='title']", "#title", "textarea[name='title']"):
                loc = page.locator(sel)
                if loc.count():
                    loc.first.fill(args.title)
                    title_filled = True
                    break
            for sel in (
                "textarea[name='content']",
                ".CodeMirror",
                "[contenteditable='true']",
            ):
                loc = page.locator(sel)
                if loc.count():
                    try:
                        loc.first.fill(args.body)
                    except Exception:
                        loc.first.click()
                        page.keyboard.type(args.body)
                    body_filled = True
                    break
            if not title_filled or not body_filled:
                print(
                    f"!! Failed to fill editor fields "
                    f"(title={title_filled}, body={body_filled})",
                    file=sys.stderr,
                )
                return 1

            draft_clicked = False
            for sel in (
                "button:has-text('임시저장')",
                "button:has-text('임시 저장')",
                "button:has-text('Draft')",
                "[data-testid='draft-save']",
                "button.btn-draft",
            ):
                loc = page.locator(sel)
                if loc.count():
                    loc.first.click()
                    draft_clicked = True
                    break
            if not draft_clicked:
                print("!! Draft-save control not found.", file=sys.stderr)
                return 1

            confirmed = False
            try:
                page.wait_for_url("**/manage/**", timeout=15_000)
                confirmed = True
            except Exception:
                pass
            if not confirmed:
                for sel in (
                    "text=임시저장되었습니다",
                    "text=임시 저장",
                    "text=Draft saved",
                    ".toast-success",
                ):
                    loc = page.locator(sel)
                    try:
                        loc.first.wait_for(state="visible", timeout=5_000)
                        confirmed = True
                        break
                    except Exception:
                        continue
            if not confirmed:
                print(
                    f"!! Draft save not confirmed (page_url={page.url})",
                    file=sys.stderr,
                )
                return 1

            print(f"   page_url={page.url}")
            print("   draft save confirmed")
            return 0
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
