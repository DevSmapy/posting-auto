"""Notifier protocol for draft preview + Approve/Skip."""

from __future__ import annotations

from typing import Protocol


class Notifier(Protocol):
    name: str

    def send_text(self, text: str) -> None:
        """Best-effort notification."""

    def wait_for_approve(self, preview: str) -> bool:
        """Return True if approved, False if skipped/timeout."""
