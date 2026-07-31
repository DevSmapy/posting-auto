"""Notifier protocol for draft preview + Approve/Skip and multi-stage gates."""

from __future__ import annotations

import time
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol, Sequence


APPROVE_IMAGE_HINT = (
    "슬라이드 이미지를 확인한 뒤 Approve 하세요. "
    "Skip/타임아웃 시 저장·인스타 발행·seen_urls 기록이 없습니다."
)

APPROVE_CONTROLS_HINT = (
    "Discord: ✅ / ⏭  ·  Telegram·Slack: Approve/Skip 버튼 또는 리액션"
)


class GateAction(str, Enum):
    APPROVE = "approve"
    RERANK = "rerank"
    REWRITE = "rewrite"
    RERENDER = "rerender"
    KEEP_FINAL = "keep_final"
    KEEP_ALL = "keep_all"
    TIMEOUT = "timeout"


class GateStage(str, Enum):
    CONTENT = "content"
    RENDER = "render"
    CLEANUP = "cleanup"


def normalize_stage(stage: GateStage | str) -> GateStage:
    """Return GateStage unchanged, or coerce a string via GateStage()."""
    return stage if isinstance(stage, GateStage) else GateStage(stage)


def maybe_send_gate_reminder(
    send_text: Callable[[str], None],
    stage: GateStage | str,
    *,
    deadline: float,
    reminder_sec: int,
    reminded: bool,
) -> bool:
    """Send a one-time gate reminder near timeout; return updated ``reminded``."""
    if reminded or reminder_sec <= 0:
        return reminded
    stage_s = normalize_stage(stage)
    if stage_s == GateStage.CLEANUP:
        return reminded
    remaining = deadline - time.time()
    if remaining > reminder_sec:
        return reminded
    # Lazy import avoids circular dependency with approve_copy → base.
    from .approve_copy import reminder_message

    send_text(reminder_message(stage_s, max(1, int(remaining))))
    return True


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

    def wait_for_gate(
        self,
        stage: GateStage | str,
        preview: str,
        *,
        image_paths: Sequence[Path] | None = None,
        remaining: int | None = None,
        max_retries: int | None = None,
        run_id: str = "",
        attempt: str = "",
    ) -> GateAction:
        """Multi-stage draft gate. Default adapters implement this."""

    def send_file(self, path: Path, caption: str = "") -> None:
        """Optional file attach (Discord/Telegram/Slack)."""
