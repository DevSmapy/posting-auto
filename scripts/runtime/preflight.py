"""Preflight + bounded recovery helpers for Posting Auto 2.0."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _truthy(name: str, default: str = "0") -> bool:
    return _env(name, default).lower() in {"1", "true", "yes"}


def check_output_dir() -> dict[str, Any]:
    out = Path(_env("OUTPUT_DIR", str(ROOT / "output"))).expanduser()
    if not out.is_absolute():
        out = (ROOT / out).resolve()
    try:
        out.mkdir(parents=True, exist_ok=True)
        probe = out / ".preflight_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"name": "filesystem_output", "ok": True, "path": str(out)}
    except OSError as exc:
        return {"name": "filesystem_output", "ok": False, "path": str(out), "error": str(exc)}


def check_ollama() -> dict[str, Any]:
    host = _env("OLLAMA_HOST_URL", "http://127.0.0.1:11434").rstrip("/")
    url = f"{host}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            ok = 200 <= getattr(resp, "status", 200) < 300
        return {"name": "ollama", "ok": ok, "url": url}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"name": "ollama", "ok": False, "url": url, "error": str(exc)}


def check_publish_env() -> dict[str, Any]:
    keys = ["PUBLISH_CARDS", "R2_ENDPOINT", "IG_USER_ID", "META_ACCESS_TOKEN"]
    present = {k: bool(_env(k)) for k in keys}
    missing: list[str] = []
    ok = True
    # Live IG path only when autonomous publish + cards are both on.
    if _truthy("AUTO_PUBLISH") and _truthy("PUBLISH_CARDS"):
        for key in ("R2_ENDPOINT", "IG_USER_ID", "META_ACCESS_TOKEN"):
            if not present[key]:
                missing.append(key)
        ok = not missing
    return {
        "name": "publish_env",
        "ok": ok,
        "present": present,
        "missing": missing,
    }


def check_network() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("https://www.google.com/generate_204", timeout=3) as resp:
            return {"name": "network", "ok": getattr(resp, "status", 204) < 500}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"name": "network", "ok": False, "error": str(exc)}


def run_preflight(*, require_ollama: bool = False) -> dict[str, Any]:
    checks = [
        check_output_dir(),
        check_network(),
        check_ollama(),
        check_publish_env(),
    ]
    soft = {"ollama"}
    if not _truthy("PREFLIGHT_REQUIRE_NETWORK"):
        soft.add("network")
    required = []
    for c in checks:
        name = str(c.get("name") or "")
        if name in soft and not (require_ollama and name == "ollama"):
            continue
        if name == "ollama" and not require_ollama:
            continue
        required.append(c)
    ok = all(bool(c.get("ok")) for c in required)
    return {"ok": ok, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-ollama", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_preflight(require_ollama=args.require_ollama)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"preflight ok={result['ok']}")
        for c in result["checks"]:
            print(f"  - {c['name']}: {'ok' if c['ok'] else 'FAIL'} {c.get('error', '')}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
