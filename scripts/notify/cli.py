"""CLI Approve gate (stdin)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .approve_copy import approve_footer, existing_image_paths


class CliNotifier:
    name = "cli"

    def send_text(self, text: str) -> None:
        print(f"[notify:cli]\n{text[:4000]}")

    def wait_for_approve(
        self,
        preview: str,
        image_paths: Sequence[Path] | None = None,
    ) -> bool:
        images = existing_image_paths(image_paths)
        print(preview)
        print(approve_footer(has_images=bool(images)))
        if images:
            print("이미지 경로:")
            for path in images:
                print(f"  - {path}")
        print("\n--- 슬라이드 이미지를 확인한 뒤 Approve? type approve / skip ---")
        try:
            line = input("> ").strip().lower()
        except EOFError:
            line = "skip"
        approved = line in {"a", "approve", "y", "yes", "ok"}
        print("   approved" if approved else "   skipped")
        return approved

    def send_file(self, path: Path, caption: str = "") -> None:
        print(f"[notify:cli] file ready: {path}" + (f" ({caption})" if caption else ""))
