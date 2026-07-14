#!/usr/bin/env python3
"""Smoke: seen_urls Postgres/SQLite round-trip."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

from seen_urls import SeenUrlsStore, url_hash  # noqa: E402


def main() -> int:
    store = SeenUrlsStore()
    print(f"backend={store.backend}")
    uniq = f"https://example.com/smoke-seen-urls-{int(__import__('time').time())}"
    sample = [
        {
            "link": uniq,
            "title": "smoke article 1",
        }
    ]
    before = store.filter_new(sample)
    assert len(before) == 1, before
    n = store.record_published(sample, tistory_post_id="smoke-post")
    assert n == 1
    after = store.filter_new(sample)
    assert len(after) == 0, after
    h = url_hash(sample[0]["link"])
    hashes = store.fetch_hashes()
    assert h in hashes
    store.close()
    print(f"OK seen_urls round-trip hash={h[:12]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
