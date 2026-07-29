"""Auto-approve (local smoke / CI)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .approve_copy import existing_image_paths
from .base import GateAction, GateStage, normalize_stage


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
        stage_s = normalize_stage(stage)
        images = existing_image_paths(image_paths)
        if stage_s == GateStage.CLEANUP:
            print(f"   auto keep_final (images={len(images)})")
            return GateAction.KEEP_FINAL
        print(f"   auto-approve gate={stage_s.value} (images={len(images)})")
        return GateAction.APPROVE

    def send_file(self, path: Path, caption: str = "") -> None:
        print(f"[notify:auto] file={path.name}")
