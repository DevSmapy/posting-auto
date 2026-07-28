"""Shared Approve preview footer / image helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .base import APPROVE_CONTROLS_HINT, APPROVE_IMAGE_HINT


def existing_image_paths(paths: Sequence[Path] | None) -> list[Path]:
    out: list[Path] = []
    for raw in paths or []:
        path = Path(raw)
        if path.is_file():
            out.append(path)
    return out


def approve_footer(*, has_images: bool) -> str:
    lines = ["", "---"]
    if has_images:
        lines.append(APPROVE_IMAGE_HINT)
    else:
        lines.append(
            "카드 이미지 생성 실패 또는 없음 — 텍스트만으로 Approve 할 수 있습니다."
        )
    lines.append(APPROVE_CONTROLS_HINT)
    return "\n".join(lines)
