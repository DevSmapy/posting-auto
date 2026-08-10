"""Minimal publisher protocol (Instagram kept; Tistory experimental)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class PublishResult:
    channel: str
    status: str
    published_url: str | None = None
    error_type: str | None = None
    detail: str | None = None


class Publisher(Protocol):
    def publish(self, content: dict[str, Any]) -> PublishResult: ...


class TistoryPublisher:
    """Placeholder until Spike A promotes a real Playwright adapter."""

    def publish(self, content: dict[str, Any]) -> PublishResult:
        return PublishResult(
            channel="tistory",
            status="skipped",
            error_type="AUTH_FAILURE",
            detail=(
                "Tistory automation not promoted. "
                "Use briefing.md / publish_ready and Human Escalation. "
                "See docs/v2/spike-a-tistory.md"
            ),
        )
