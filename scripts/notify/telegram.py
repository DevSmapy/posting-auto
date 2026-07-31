"""Telegram Approve via inline keyboard + getUpdates poll."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

import requests

from .approve_copy import (
    approve_footer,
    existing_image_paths,
    gate_footer,
    reminder_message,
    timeout_message,
)
from .base import GateAction, GateStage, normalize_stage
from .envutil import approve_reminder_sec, approve_timeout_sec, env


class TelegramNotifier:
    name = "telegram"

    def __init__(self) -> None:
        self.token = env("TELEGRAM_BOT_TOKEN")
        self.chat_id = env("TELEGRAM_CHAT_ID")

    def _api(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN required")
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        resp = requests.post(url, json=payload or {}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API {method} failed: {data}")
        return data

    def send_text(self, text: str) -> None:
        if not self.token or not self.chat_id:
            print("Telegram skipped: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
            return
        self._api("sendMessage", {"chat_id": self.chat_id, "text": text[:4000]})

    def send_file(self, path: Path, caption: str = "") -> None:
        if not self.token or not self.chat_id:
            print("Telegram skipped: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
            return
        path = Path(path)
        if not path.is_file():
            print(f"Telegram send_file skipped: missing {path}")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        with path.open("rb") as fh:
            resp = requests.post(
                url,
                data={"chat_id": self.chat_id, "caption": (caption or path.name)[:1024]},
                files={"document": (path.name, fh)},
                timeout=60,
            )
        resp.raise_for_status()
        print(f"   Telegram document sent: {path.name}")

    def _send_images(self, images: list[Path]) -> None:
        """Send PNG slides as photos, using media groups only for 2-10 batches."""
        if not images:
            return
        for start in range(0, len(images), 10):
            batch = images[start : start + 10]
            if len(batch) == 1:
                path = batch[0]
                url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
                with path.open("rb") as fh:
                    resp = requests.post(
                        url,
                        data={
                            "chat_id": self.chat_id,
                            "caption": f"슬라이드 {start + 1}/{len(images)}",
                        },
                        files={"photo": (path.name, fh, "image/png")},
                        timeout=120,
                    )
                if not resp.ok:
                    print(
                        f"   !! Telegram sendPhoto failed: "
                        f"{resp.status_code} {resp.text[:300]}"
                    )
                    continue
                print(f"   Telegram photo sent: {path.name}")
                continue

            url = f"https://api.telegram.org/bot{self.token}/sendMediaGroup"
            media = []
            files: dict[str, Any] = {}
            handles = []
            try:
                for i, path in enumerate(batch):
                    key = f"photo{i}"
                    media.append(
                        {
                            "type": "photo",
                            "media": f"attach://{key}",
                            **(
                                {"caption": f"슬라이드 {start + i + 1}/{len(images)}"}
                                if i == 0
                                else {}
                            ),
                        }
                    )
                    fh = path.open("rb")
                    handles.append(fh)
                    files[key] = (path.name, fh, "image/png")
                resp = requests.post(
                    url,
                    data={
                        "chat_id": self.chat_id,
                        "media": json.dumps(media, ensure_ascii=False),
                    },
                    files=files,
                    timeout=120,
                )
                if not resp.ok:
                    print(
                        f"   !! Telegram sendMediaGroup failed: "
                        f"{resp.status_code} {resp.text[:300]}"
                    )
                    continue
                print(f"   Telegram photos sent: {[p.name for p in batch]}")
            finally:
                for h in handles:
                    h.close()

    def wait_for_approve(
        self,
        preview: str,
        image_paths: Sequence[Path] | None = None,
    ) -> bool:
        timeout = approve_timeout_sec()
        if not self.token or not self.chat_id:
            raise RuntimeError(
                "Telegram Approve requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
            )

        images = existing_image_paths(image_paths)
        if images:
            self._send_images(images)

        request_id = uuid.uuid4().hex[:12]
        approve_data = f"approve:{request_id}"
        skip_data = f"skip:{request_id}"
        footer = approve_footer(has_images=bool(images))
        preview_limit = max(0, 3500 - len(footer))
        chunk = preview[:preview_limit] + footer
        markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": approve_data},
                    {"text": "⏭ Skip", "callback_data": skip_data},
                ]
            ]
        }
        boot = self._api("getUpdates", {"offset": -1, "timeout": 0})
        offset = 0
        for upd in boot.get("result") or []:
            offset = max(offset, int(upd.get("update_id", 0)) + 1)

        self._api(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": chunk + f"\n\n[승인 요청 {request_id}]",
                "reply_markup": markup,
            },
        )
        print("   Telegram preview + Approve/Skip sent — waiting…")

        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(1, int(deadline - time.time()))
            poll_timeout = min(25, remaining)
            data = self._api(
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": poll_timeout,
                    "allowed_updates": ["callback_query", "message"],
                },
            )
            for upd in data.get("result") or []:
                offset = max(offset, int(upd.get("update_id", 0)) + 1)
                cb = upd.get("callback_query")
                if cb:
                    raw = str(cb.get("data") or "")
                    cq_id = cb.get("id")
                    if raw == approve_data:
                        if cq_id:
                            self._api(
                                "answerCallbackQuery",
                                {
                                    "callback_query_id": cq_id,
                                    "text": "Approve — 마크다운 저장",
                                },
                            )
                        self.send_text("승인됨. 마크다운 저장(+선택 인스타)합니다.")
                        return True
                    if raw == skip_data:
                        if cq_id:
                            self._api(
                                "answerCallbackQuery",
                                {"callback_query_id": cq_id, "text": "Skip"},
                            )
                        self.send_text("스킵됨. 저장하지 않습니다.")
                        return False
                msg = upd.get("message") or {}
                text = (msg.get("text") or "").strip().lower()
                if str(msg.get("chat", {}).get("id")) == str(self.chat_id):
                    if text in {"/approve", "approve"}:
                        self.send_text("승인됨. 마크다운 저장(+선택 인스타)합니다.")
                        return True
                    if text in {"/skip", "skip"}:
                        self.send_text("스킵됨. 저장하지 않습니다.")
                        return False

        self.send_text(f"[타임아웃] {timeout}s 내 응답 없음 — 마크다운 저장 취소")
        print("   Approve timeout — skip export")
        return False

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
        timeout = approve_timeout_sec()
        if not self.token or not self.chat_id:
            raise RuntimeError(
                "Telegram gate requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
            )

        stage_s = normalize_stage(stage)
        images = existing_image_paths(image_paths)
        if images:
            self._send_images(images)

        request_id = uuid.uuid4().hex[:12]
        footer = gate_footer(
            stage_s,
            has_images=bool(images),
            remaining=remaining,
            max_retries=max_retries,
            run_id=run_id,
            attempt=attempt,
        )
        preview_limit = max(0, 3500 - len(footer))
        chunk = preview[:preview_limit] + footer

        if stage_s == GateStage.CONTENT:
            rows = [
                [
                    {"text": "✅ Approve", "callback_data": f"approve:{request_id}"},
                    {"text": "🔀 Rerank", "callback_data": f"rerank:{request_id}"},
                    {"text": "✍️ Rewrite", "callback_data": f"rewrite:{request_id}"},
                ]
            ]
            action_map = {
                f"approve:{request_id}": GateAction.APPROVE,
                f"rerank:{request_id}": GateAction.RERANK,
                f"rewrite:{request_id}": GateAction.REWRITE,
            }
            text_map = {
                "/approve": GateAction.APPROVE,
                "approve": GateAction.APPROVE,
                "/rerank": GateAction.RERANK,
                "rerank": GateAction.RERANK,
                "/rewrite": GateAction.REWRITE,
                "rewrite": GateAction.REWRITE,
            }
        elif stage_s == GateStage.RENDER:
            rows = [
                [
                    {"text": "✅ Approve", "callback_data": f"approve:{request_id}"},
                    {"text": "🔁 Re-render", "callback_data": f"rerender:{request_id}"},
                ]
            ]
            action_map = {
                f"approve:{request_id}": GateAction.APPROVE,
                f"rerender:{request_id}": GateAction.RERENDER,
            }
            text_map = {
                "/approve": GateAction.APPROVE,
                "approve": GateAction.APPROVE,
                "/rerender": GateAction.RERENDER,
                "rerender": GateAction.RERENDER,
            }
        else:
            rows = [
                [
                    {"text": "✅ 확정본만", "callback_data": f"keep_final:{request_id}"},
                    {"text": "🗄 전부 보관", "callback_data": f"keep_all:{request_id}"},
                ]
            ]
            action_map = {
                f"keep_final:{request_id}": GateAction.KEEP_FINAL,
                f"keep_all:{request_id}": GateAction.KEEP_ALL,
            }
            text_map = {
                "/keep_final": GateAction.KEEP_FINAL,
                "keep_final": GateAction.KEEP_FINAL,
                "/keep_all": GateAction.KEEP_ALL,
                "keep_all": GateAction.KEEP_ALL,
            }

        boot = self._api("getUpdates", {"offset": -1, "timeout": 0})
        offset = 0
        for upd in boot.get("result") or []:
            offset = max(offset, int(upd.get("update_id", 0)) + 1)

        self._api(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": chunk + f"\n\n[게이트 {stage_s.value} {request_id}]",
                "reply_markup": {"inline_keyboard": rows},
            },
        )
        print(f"   Telegram {stage_s.value} gate sent — waiting…")

        deadline = time.time() + timeout
        reminder_sec = approve_reminder_sec()
        reminded = False
        while time.time() < deadline:
            remaining_s = max(1, int(deadline - time.time()))
            if (
                not reminded
                and reminder_sec > 0
                and remaining_s <= reminder_sec
                and stage_s != GateStage.CLEANUP
            ):
                self.send_text(reminder_message(stage_s, remaining_s))
                reminded = True
            poll_timeout = min(25, remaining_s)
            data = self._api(
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": poll_timeout,
                    "allowed_updates": ["callback_query", "message"],
                },
            )
            for upd in data.get("result") or []:
                offset = max(offset, int(upd.get("update_id", 0)) + 1)
                cb = upd.get("callback_query")
                if cb:
                    raw = str(cb.get("data") or "")
                    cq_id = cb.get("id")
                    if raw in action_map:
                        if cq_id:
                            self._api(
                                "answerCallbackQuery",
                                {"callback_query_id": cq_id, "text": action_map[raw].value},
                            )
                        return action_map[raw]
                msg = upd.get("message") or {}
                text = (msg.get("text") or "").strip().lower()
                if str(msg.get("chat", {}).get("id")) == str(self.chat_id) and text in text_map:
                    return text_map[text]

        self.send_text(timeout_message(stage_s, timeout, run_id=run_id))
        print(f"   {stage_s.value} gate timeout")
        return GateAction.TIMEOUT
