"""Discord Approve via message + ✅ / ⏭ reaction polling."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from .envutil import approve_timeout_sec, env

API = "https://discord.com/api/v10"
APPROVE_EMOJI = "✅"
SKIP_EMOJI = "⏭"


class DiscordNotifier:
    name = "discord"

    def __init__(self) -> None:
        self.token = env("DISCORD_BOT_TOKEN")
        self.channel_id = env("DISCORD_CHANNEL_ID")

    def _auth_headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("DISCORD_BOT_TOKEN required")
        return {"Authorization": f"Bot {self.token}"}

    def _headers(self) -> dict[str, str]:
        return {
            **self._auth_headers(),
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{API}{path}"
        resp = requests.request(method, url, headers=self._headers(), timeout=30, **kwargs)
        if resp.status_code == 429:
            retry = float(resp.headers.get("Retry-After", "1"))
            time.sleep(retry)
            resp = requests.request(method, url, headers=self._headers(), timeout=30, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def send_text(self, text: str) -> None:
        if not self.token or not self.channel_id:
            print("Discord skipped: missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID")
            return
        chunk = text[:1900]
        self._request("POST", f"/channels/{self.channel_id}/messages", json={"content": chunk})

    def send_file(self, path: Path, caption: str = "") -> None:
        if not self.token or not self.channel_id:
            print("Discord skipped: missing DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID")
            return
        path = Path(path)
        if not path.is_file():
            print(f"Discord send_file skipped: missing {path}")
            return
        payload = {"content": (caption or f"첨부: {path.name}")[:1900]}
        with path.open("rb") as fh:
            resp = requests.post(
                f"{API}/channels/{self.channel_id}/messages",
                headers=self._auth_headers(),
                data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                files={"files[0]": (path.name, fh, "text/markdown; charset=utf-8")},
                timeout=60,
            )
        if resp.status_code == 429:
            time.sleep(float(resp.headers.get("Retry-After", "1")))
            with path.open("rb") as fh:
                resp = requests.post(
                    f"{API}/channels/{self.channel_id}/messages",
                    headers=self._auth_headers(),
                    data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                    files={"files[0]": (path.name, fh, "text/markdown; charset=utf-8")},
                    timeout=60,
                )
        if not resp.ok:
            print(f"   !! Discord send_file failed: {resp.status_code} {resp.text[:300]}")
            return
        print(f"   Discord file attached: {path.name}")

    def _create_message(self, content: str) -> str:
        data = self._request(
            "POST",
            f"/channels/{self.channel_id}/messages",
            json={"content": content[:1900]},
        )
        return str(data["id"])

    def _add_reaction(self, message_id: str, emoji: str) -> None:
        enc = quote(emoji)
        self._request(
            "PUT",
            f"/channels/{self.channel_id}/messages/{message_id}/reactions/{enc}/@me",
        )

    def _reaction_users(self, message_id: str, emoji: str) -> list[dict[str, Any]]:
        enc = quote(emoji)
        data = self._request(
            "GET",
            f"/channels/{self.channel_id}/messages/{message_id}/reactions/{enc}",
            params={"limit": 25},
        )
        return data if isinstance(data, list) else []

    def wait_for_approve(self, preview: str) -> bool:
        timeout = approve_timeout_sec()
        if not self.token or not self.channel_id:
            raise RuntimeError("Discord Approve requires DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID")

        body = (
            preview[:1700]
            + "\n\n---\n**Approve:** ✅  /  **Skip:** ⏭\n"
            "(봇이 미리 달아 둔 리액션에 추가로 눌러 주세요)"
        )
        msg_id = self._create_message(body)
        try:
            self._add_reaction(msg_id, APPROVE_EMOJI)
            self._add_reaction(msg_id, SKIP_EMOJI)
        except Exception as exc:  # noqa: BLE001
            print(f"   !! Discord seed reactions failed: {exc}")
        print("   Discord preview sent — react ✅ or ⏭ …")

        me = self._request("GET", "/users/@me")
        bot_id = str(me.get("id") or "")

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                approve_users = self._reaction_users(msg_id, APPROVE_EMOJI)
                skip_users = self._reaction_users(msg_id, SKIP_EMOJI)
            except Exception as exc:  # noqa: BLE001
                print(f"   !! Discord reaction poll error: {exc}")
                time.sleep(2)
                continue

            if any(str(u.get("id")) != bot_id and not u.get("bot") for u in approve_users):
                self.send_text("승인됨. 마크다운 파일로 저장합니다.")
                return True
            if any(str(u.get("id")) != bot_id and not u.get("bot") for u in skip_users):
                self.send_text("스킵됨. 저장하지 않습니다.")
                return False
            time.sleep(2)

        self.send_text(f"[타임아웃] {timeout}s 내 응답 없음 — 마크다운 저장 취소")
        print("   Approve timeout — skip export")
        return False
