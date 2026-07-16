"""CLI Approve gate (stdin)."""

from __future__ import annotations

from pathlib import Path


class CliNotifier:
    name = "cli"

    def send_text(self, text: str) -> None:
        print(f"[notify:cli]\n{text[:4000]}")

    def wait_for_approve(self, preview: str) -> bool:
        print(preview)
        print("\n--- Approve? type approve / skip ---")
        try:
            line = input("> ").strip().lower()
        except EOFError:
            line = "skip"
        approved = line in {"a", "approve", "y", "yes", "ok"}
        print("   approved" if approved else "   skipped")
        return approved

    def send_file(self, path: Path, caption: str = "") -> None:
        print(f"[notify:cli] file ready: {path}" + (f" ({caption})" if caption else ""))
