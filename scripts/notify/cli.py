"""CLI Approve / gate (stdin)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .approve_copy import approve_footer, existing_image_paths, gate_footer
from .base import GateAction, GateStage, normalize_stage


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
        print(preview)
        print(
            gate_footer(
                stage_s,
                has_images=bool(images),
                remaining=remaining,
                max_retries=max_retries,
                run_id=run_id,
                attempt=attempt,
            )
        )
        if images:
            print("이미지 경로:")
            for path in images:
                print(f"  - {path}")
        if stage_s == GateStage.CONTENT:
            prompt = "type approve / rerank / rewrite"
            mapping = {
                "a": GateAction.APPROVE,
                "approve": GateAction.APPROVE,
                "rerank": GateAction.RERANK,
                "rewrite": GateAction.REWRITE,
            }
        elif stage_s == GateStage.RENDER:
            prompt = "type approve / rerender"
            mapping = {
                "a": GateAction.APPROVE,
                "approve": GateAction.APPROVE,
                "rerender": GateAction.RERENDER,
            }
        else:
            prompt = "type keep_final / keep_all"
            mapping = {
                "keep_final": GateAction.KEEP_FINAL,
                "final": GateAction.KEEP_FINAL,
                "keep_all": GateAction.KEEP_ALL,
                "all": GateAction.KEEP_ALL,
            }
        print(f"\n--- {stage_s.value} gate: {prompt} ---")
        try:
            line = input("> ").strip().lower()
        except EOFError:
            return GateAction.TIMEOUT
        return mapping.get(line, GateAction.TIMEOUT)

    def send_file(self, path: Path, caption: str = "") -> None:
        print(f"[notify:cli] file ready: {path}" + (f" ({caption})" if caption else ""))
