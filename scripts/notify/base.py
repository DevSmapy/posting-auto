"""Notifier protocol for draft preview + Approve/Skip."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Notifier(Protocol):
    name: str

    def send_text(self, text: str) -> None:
        """Best-effort notification."""

    def wait_for_approve(self, preview: str) -> bool:
        """Return True if approved, False if skipped/timeout."""

    def send_file(self, path: Path, caption: str = "") -> None:
        """Optional file attach (Discord/Telegram). Default: no-op via duck typing."""
