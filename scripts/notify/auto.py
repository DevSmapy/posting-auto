"""Auto-approve (local smoke / CI)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .approve_copy import existing_image_paths


class AutoNotifier:
    name = "auto"

    def send_text(self, text: str) -> None:
        print(f"[notify:auto] {text[:200]}")

    def wait_for_approve(
        self,
        preview: str,
        image_paths: Sequence[Path] | None = None,
    ) -> bool:
        images = existing_image_paths(image_paths)
        print(f"   auto-approve (images={len(images)})")
        return True

    def send_file(self, path: Path, caption: str = "") -> None:
        print(f"[notify:auto] file={path.name}")
