"""Discord Approve via message + ✅ / ⏭ reaction polling."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

import requests

from .approve_copy import approve_footer, existing_image_paths
from .envutil import approve_timeout_sec, env

API = "https://discord.com/api/v10"
APPROVE_EMOJI = "✅"
SKIP_EMOJI = "⏭"
# Discord allows up to 10 attachments per message.
_MAX_FILES_PER_MESSAGE = 10


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
        self._post_files([path], caption or f"첨부: {path.name}")

    def _post_files(self, paths: list[Path], content: str) -> str | None:
        """Upload files; return message id of the last successful batch."""
        last_id: str | None = None
        for start in range(0, len(paths), _MAX_FILES_PER_MESSAGE):
            batch = paths[start : start + _MAX_FILES_PER_MESSAGE]
            payload = {"content": content[:1900] if start == 0 else f"(슬라이드 계속 {start + 1}–)"}
            files: dict[str, Any] = {}
            handles = []
            try:
                for i, path in enumerate(batch):
                    fh = path.open("rb")
                    handles.append(fh)
                    mime = "image/png" if path.suffix.lower() == ".png" else "application/octet-stream"
                    files[f"files[{i}]"] = (path.name, fh, mime)
                resp = requests.post(
                    f"{API}/channels/{self.channel_id}/messages",
                    headers=self._auth_headers(),
                    data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                    files=files,
                    timeout=120,
                )
                if resp.status_code == 429:
                    time.sleep(float(resp.headers.get("Retry-After", "1")))
                    for h in handles:
                        h.seek(0)
                    resp = requests.post(
                        f"{API}/channels/{self.channel_id}/messages",
                        headers=self._auth_headers(),
                        data={"payload_json": json.dumps(payload, ensure_ascii=False)},
                        files=files,
                        timeout=120,
                    )
                if not resp.ok:
                    print(f"   !! Discord send files failed: {resp.status_code} {resp.text[:300]}")
                    continue
                data = resp.json()
                last_id = str(data.get("id") or "") or last_id
                print(f"   Discord files attached: {[p.name for p in batch]}")
            finally:
                for h in handles:
                    h.close()
        return last_id

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

    def wait_for_approve(
        self,
        preview: str,
        image_paths: Sequence[Path] | None = None,
    ) -> bool:
        timeout = approve_timeout_sec()
        if not self.token or not self.channel_id:
            raise RuntimeError("Discord Approve requires DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID")

        images = existing_image_paths(image_paths)
        footer = approve_footer(has_images=bool(images))
        body = preview[:1600] + footer
        body += "\n\n**Approve:** ✅  /  **Skip:** ⏭\n(봇이 미리 달아 둔 리액션에 추가로 눌러 주세요)"

        msg_id: str | None = None
        if images:
            msg_id = self._post_files(images, body)
        if not msg_id:
            msg_id = self._create_message(body)

        try:
            self._add_reaction(msg_id, APPROVE_EMOJI)
            self._add_reaction(msg_id, SKIP_EMOJI)
        except Exception as exc:  # noqa: BLE001
            print(f"   !! Discord seed reactions failed: {exc}")
        print("   Discord preview (+images) sent — react ✅ or ⏭ …")

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
                self.send_text("승인됨. 마크다운 저장(+선택 인스타)합니다.")
                return True
            if any(str(u.get("id")) != bot_id and not u.get("bot") for u in skip_users):
                self.send_text("스킵됨. 저장하지 않습니다.")
                return False
            time.sleep(2)

        self.send_text(f"[타임아웃] {timeout}s 내 응답 없음 — 마크다운 저장 취소")
        print("   Approve timeout — skip export")
        return False
