"""Shared Approve / gate preview footer helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .base import APPROVE_CONTROLS_HINT, APPROVE_IMAGE_HINT, GateStage

_KEYCAPS = {
    0: "0️⃣",
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
}


def existing_image_paths(paths: Sequence[Path] | None) -> list[Path]:
    out: list[Path] = []
    for raw in paths or []:
        path = Path(raw)
        if path.is_file():
            out.append(path)
    return out


def keycap(n: int) -> str:
    if 0 <= n <= 9:
        return _KEYCAPS[n]
    return str(n)


def remaining_line(
    stage: GateStage | str,
    remaining: int,
    max_retries: int,
) -> str:
    stage_s = GateStage(stage) if not isinstance(stage, GateStage) else stage
    if stage_s == GateStage.CONTENT:
        label = "🔁 내용 재생성 남은 기회"
    elif stage_s == GateStage.RENDER:
        label = "🖼 이미지 재생성 남은 기회"
    else:
        label = "남은 기회"
    return f"**{label}: {keycap(remaining)} / {max_retries}**"


def stage_header(
    stage: GateStage | str,
    *,
    remaining: int | None = None,
    max_retries: int | None = None,
    run_id: str = "",
    attempt: str = "",
) -> str:
    stage_s = GateStage(stage) if not isinstance(stage, GateStage) else stage
    if stage_s == GateStage.CONTENT:
        title = "① 내용 확정"
    elif stage_s == GateStage.RENDER:
        title = "② 이미지 확정"
    else:
        title = "③ 클린업"
    parts = [f"**{title}**"]
    if run_id:
        parts.append(f"`{run_id}`")
    if attempt:
        parts.append(attempt)
    if remaining is not None and max_retries is not None and stage_s != GateStage.CLEANUP:
        parts.append(remaining_line(stage_s, remaining, max_retries))
    return " · ".join(parts)


def gate_controls_hint(stage: GateStage | str) -> str:
    stage_s = GateStage(stage) if not isinstance(stage, GateStage) else stage
    if stage_s == GateStage.CONTENT:
        return (
            "**Approve:** ✅  ·  **Rerank(다른 기사):** 🔀  ·  **Rewrite(같은 기사 다시쓰기):** ✍️\n"
            "(봇이 미리 달아 둔 리액션에 추가로 눌러 주세요)"
        )
    if stage_s == GateStage.RENDER:
        return (
            "**Approve:** ✅  ·  **Re-render(이미지만 다시):** 🔁\n"
            "(봇이 미리 달아 둔 리액션에 추가로 눌러 주세요)"
        )
    return (
        "**확정본만 유지:** ✅  ·  **전부 보관:** 🗄\n"
        "(봇이 미리 달아 둔 리액션에 추가로 눌러 주세요)"
    )


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


def gate_footer(
    stage: GateStage | str,
    *,
    has_images: bool = False,
    remaining: int | None = None,
    max_retries: int | None = None,
    run_id: str = "",
    attempt: str = "",
) -> str:
    stage_s = GateStage(stage) if not isinstance(stage, GateStage) else stage
    lines = [
        "",
        "---",
        stage_header(
            stage_s,
            remaining=remaining,
            max_retries=max_retries,
            run_id=run_id,
            attempt=attempt,
        ),
    ]
    if stage_s == GateStage.RENDER:
        if has_images:
            lines.append("슬라이드 이미지를 확인한 뒤 Approve 하세요.")
        else:
            lines.append("카드 이미지 생성 실패 또는 없음 — 텍스트만으로 Approve 할 수 있습니다.")
    elif stage_s == GateStage.CONTENT:
        lines.append("텍스트 브리핑을 확인한 뒤 Approve / Rerank / Rewrite 하세요.")
    lines.append(gate_controls_hint(stage_s))
    return "\n".join(lines)


def exhausted_message(stage: GateStage | str) -> str:
    stage_s = GateStage(stage) if not isinstance(stage, GateStage) else stage
    if stage_s == GateStage.CONTENT:
        kind = "내용 재생성(랭킹/다시쓰기)"
    else:
        kind = "이미지 재생성"
    return (
        f"⛔ {kind} 횟수를 모두 사용했습니다.\n"
        "작업을 중단합니다.\n"
        "계속하려면 스크립트를 다시 실행하세요:\n"
        "`./scripts/run_draft.sh`"
    )


def timeout_message(stage: GateStage | str, timeout_sec: int) -> str:
    stage_s = GateStage(stage) if not isinstance(stage, GateStage) else stage
    return (
        f"[타임아웃] {stage_s.value} 게이트 — {timeout_sec}s 내 응답 없음.\n"
        "재시도 횟수는 차감되지 않았습니다. attempt는 디스크에 유지됩니다.\n"
        "계속하려면 스크립트를 다시 실행하세요: `./scripts/run_draft.sh`"
    )


def regenerating_ack(action: str, remaining: int, max_retries: int) -> str:
    labels = {
        "rerank": "다른 기사로 랭킹 재생성",
        "rewrite": "같은 기사로 내용 다시쓰기",
        "rerender": "동일 브리핑으로 이미지 재생성",
    }
    label = labels.get(action, action)
    return (
        f"🔄 {label} 진행 중… "
        f"(남은 기회 {keycap(remaining)} / {max_retries})"
    )


KEEP_FINAL_WARNING = (
    "⚠️ 확정본만 유지하면, 선택되지 않은 앞선 리서치 결과물·렌더는 모두 삭제됩니다. "
    "(복구 불가)"
)


def cleanup_prompt(
    *,
    selected_label: str,
    unselected: list[str],
    run_id: str = "",
) -> str:
    lines = [
        stage_header(GateStage.CLEANUP, run_id=run_id),
        "",
        f"📦 확정본: `{selected_label}`",
    ]
    if unselected:
        lines.append("미선택 초안/렌더:")
        for item in unselected:
            lines.append(f"- `{item}`")
    else:
        lines.append("미선택 초안/렌더: 없음")
    lines.extend(
        [
            "",
            "**✅ 확정본만 유지**",
            KEEP_FINAL_WARNING,
            "",
            "**🗄 전부 보관**",
            "확정본과 미선택 초안을 모두 남깁니다.",
            "",
            gate_controls_hint(GateStage.CLEANUP),
            "무응답(타임아웃) 시 확정본만 유지로 정리합니다.",
        ]
    )
    return "\n".join(lines)


def cleanup_timeout_notice(deleted: list[str]) -> str:
    extra = f"\n삭제: {', '.join(deleted)}" if deleted else "\n삭제할 미선택 항목 없음."
    return (
        "[클린업 타임아웃] 무응답이라 **확정본만 유지**로 정리했습니다."
        + extra
    )
