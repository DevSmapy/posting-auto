"""Notifier protocol for draft preview + Approve/Skip."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence


APPROVE_IMAGE_HINT = (
    "슬라이드 이미지를 확인한 뒤 Approve 하세요. "
    "Skip/타임아웃 시 저장·인스타 발행·seen_urls 기록이 없습니다."
)

APPROVE_CONTROLS_HINT = (
    "Discord: ✅ / ⏭  ·  Telegram·Slack: Approve/Skip 버튼 또는 리액션"
)


class Notifier(Protocol):
    name: str

    def send_text(self, text: str) -> None:
        """Best-effort notification."""

    def wait_for_approve(
        self,
        preview: str,
        image_paths: Sequence[Path] | None = None,
    ) -> bool:
        """Return True if approved, False if skipped/timeout.

        ``image_paths`` are local card PNGs to attach before the Approve control
        so the operator can review slides visually.
        """

    def send_file(self, path: Path, caption: str = "") -> None:
        """Optional file attach (Discord/Telegram/Slack)."""
