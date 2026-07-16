"""Telegram Approve via inline keyboard + getUpdates poll."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import requests

from .envutil import approve_timeout_sec, env


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

    def wait_for_approve(self, preview: str) -> bool:
        timeout = approve_timeout_sec()
        if not self.token or not self.chat_id:
            raise RuntimeError("Telegram Approve requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")

        request_id = uuid.uuid4().hex[:12]
        approve_data = f"approve:{request_id}"
        skip_data = f"skip:{request_id}"
        chunk = preview[:3500]
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
                                {"callback_query_id": cq_id, "text": "Approve — 마크다운 저장"},
                            )
                        self.send_text("승인됨. 마크다운 파일로 저장합니다.")
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
                        self.send_text("승인됨. 마크다운 파일로 저장합니다.")
                        return True
                    if text in {"/skip", "skip"}:
                        self.send_text("스킵됨. 저장하지 않습니다.")
                        return False

        self.send_text(f"[타임아웃] {timeout}s 내 응답 없음 — 마크다운 저장 취소")
        print("   Approve timeout — skip export")
        return False
