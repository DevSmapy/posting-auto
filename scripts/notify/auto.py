"""Auto-approve (local smoke / CI)."""

from __future__ import annotations

from pathlib import Path


class AutoNotifier:
    name = "auto"

    def send_text(self, text: str) -> None:
        print(f"[notify:auto] {text[:200]}")

    def wait_for_approve(self, preview: str) -> bool:
        print("   auto-approve")
        return True

    def send_file(self, path: Path, caption: str = "") -> None:
        print(f"[notify:auto] file={path.name}")
