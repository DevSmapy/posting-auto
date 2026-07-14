#!/usr/bin/env python3
"""Smoke: Tistory credentials (list posts or write-readiness check)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def main() -> int:
    token = env("TISTORY_ACCESS_TOKEN")
    blog = env("TISTORY_BLOG_NAME")
    if not token or not blog:
        print("FAIL: TISTORY_ACCESS_TOKEN / TISTORY_BLOG_NAME empty — set in .env")
        return 1
    resp = requests.get(
        "https://www.tistory.com/apis/blog/info",
        params={"access_token": token, "output": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    status = str(data.get("tistory", {}).get("status") or "")
    if status != "200":
        print(f"FAIL: blog/info {data}")
        return 1
    names = []
    item = data.get("tistory", {}).get("item")
    if isinstance(item, list):
        names = [str(x.get("name") or "") for x in item]
    elif isinstance(item, dict):
        names = [str(item.get("name") or "")]
    print(f"OK blog/info blogs={names} target={blog}")
    if blog not in names and names:
        print(f"WARN: TISTORY_BLOG_NAME={blog} not in account blogs {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
