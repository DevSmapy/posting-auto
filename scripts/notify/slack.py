"""Slack Approve via file upload + ✅ / ⏭ reaction polling.

Uses Bot Token (``SLACK_BOT_TOKEN``) and channel id (``SLACK_CHANNEL_ID``).
Interactive Block Kit buttons need a public Request URL; reactions mirror Discord
and work without an HTTP endpoint.
"""

from __future__ import annotations

import time
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

API = "https://slack.com/api"
APPROVE_EMOJI = "white_check_mark"
SKIP_EMOJI = "next_track_button"
RERANK_EMOJI = "twisted_rightwards_arrows"
REWRITE_EMOJI = "writing_hand"
RERENDER_EMOJI = "repeat"
KEEP_ALL_EMOJI = "file_cabinet"

_STAGE_EMOJIS: dict[GateStage, list[tuple[str, GateAction]]] = {
    GateStage.CONTENT: [
        (APPROVE_EMOJI, GateAction.APPROVE),
        (RERANK_EMOJI, GateAction.RERANK),
        (REWRITE_EMOJI, GateAction.REWRITE),
    ],
    GateStage.RENDER: [
        (APPROVE_EMOJI, GateAction.APPROVE),
        (RERENDER_EMOJI, GateAction.RERENDER),
    ],
    GateStage.CLEANUP: [
        (APPROVE_EMOJI, GateAction.KEEP_FINAL),
        (KEEP_ALL_EMOJI, GateAction.KEEP_ALL),
    ],
}


class SlackNotifier:
    name = "slack"

    def __init__(self) -> None:
        self.token = env("SLACK_BOT_TOKEN")
        self.channel_id = env("SLACK_CHANNEL_ID")

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("SLACK_BOT_TOKEN required")
        return {"Authorization": f"Bearer {self.token}"}

    def _api(self, method: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST form-urlencoded args (Slack Web API)."""
        resp = requests.post(
            f"{API}/{method}",
            headers=self._headers(),
            data=payload or {},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API {method} failed: {data.get('error') or data}")
        return data

    def _api_get(self, method: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = requests.get(
            f"{API}/{method}",
            headers=self._headers(),
            params=params or {},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API {method} failed: {data.get('error') or data}")
        return data

    def _api_json(self, method: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = requests.post(
            f"{API}/{method}",
            headers={**self._headers(), "Content-Type": "application/json; charset=utf-8"},
            json=json_body or {},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API {method} failed: {data.get('error') or data}")
        return data

    def _reaction_data(self, ts: str) -> dict[str, Any]:
        return self._api_get(
            "reactions.get",
            params={
                "channel": self.channel_id,
                "timestamp": ts,
                "full": "true",
            },
        )

    def send_text(self, text: str) -> None:
        if not self.token or not self.channel_id:
            print("Slack skipped: missing SLACK_BOT_TOKEN or SLACK_CHANNEL_ID")
            return
        try:
            self._api_json(
                "chat.postMessage",
                json_body={"channel": self.channel_id, "text": text[:3900]},
            )
        except Exception as exc:  # noqa: BLE001
            print(f"   !! Slack send_text failed: {exc}")

    def send_file(self, path: Path, caption: str = "") -> None:
        if not self.token or not self.channel_id:
            print("Slack skipped: missing SLACK_BOT_TOKEN or SLACK_CHANNEL_ID")
            return
        path = Path(path)
        if not path.is_file():
            print(f"Slack send_file skipped: missing {path}")
            return
        self._upload_file(path, caption or path.name)

    def _upload_file(self, path: Path, title: str) -> None:
        length = path.stat().st_size
        meta = self._api(
            "files.getUploadURLExternal",
            payload={"filename": path.name, "length": str(length)},
        )
        upload_url = str(meta.get("upload_url") or "")
        file_id = str(meta.get("file_id") or "")
        if not upload_url or not file_id:
            raise RuntimeError(f"Slack upload URL missing: {meta}")
        with path.open("rb") as fh:
            up = requests.post(upload_url, data=fh.read(), timeout=120)
            up.raise_for_status()
        self._api_json(
            "files.completeUploadExternal",
            json_body={
                "files": [{"id": file_id, "title": title[:100]}],
                "channel_id": self.channel_id,
                "initial_comment": title[:500],
            },
        )
        print(f"   Slack file uploaded: {path.name}")

    def _post_message(self, text: str) -> str:
        data = self._api_json(
            "chat.postMessage",
            json_body={"channel": self.channel_id, "text": text[:3900]},
        )
        return str(data.get("ts") or "")

    def _add_reaction(self, ts: str, name: str) -> None:
        try:
            self._api(
                "reactions.add",
                payload={"channel": self.channel_id, "timestamp": ts, "name": name},
            )
        except RuntimeError as exc:
            if "already_reacted" not in str(exc):
                raise

    def _reaction_users(self, data: dict[str, Any], name: str) -> list[str]:
        msg = data.get("message") or {}
        users: list[str] = []
        for rx in msg.get("reactions") or []:
            if rx.get("name") == name:
                users.extend(str(u) for u in (rx.get("users") or []))
        return users

    def wait_for_approve(
        self,
        preview: str,
        image_paths: Sequence[Path] | None = None,
    ) -> bool:
        timeout = approve_timeout_sec()
        if not self.token or not self.channel_id:
            raise RuntimeError("Slack Approve requires SLACK_BOT_TOKEN and SLACK_CHANNEL_ID")

        images = existing_image_paths(image_paths)
        uploaded_images: list[Path] = []
        for path in images:
            try:
                self._upload_file(path, f"카드 슬라이드: {path.name}")
                uploaded_images.append(path)
            except Exception as exc:  # noqa: BLE001
                print(f"   !! Slack image upload failed ({path.name}): {exc}")

        footer = approve_footer(has_images=bool(uploaded_images))
        body = (
            preview[:3000]
            + footer
            + "\n\n*Approve:* :white_check_mark:  /  *Skip:* :next_track_button:\n"
            "(봇이 미리 달아 둔 리액션에 추가로 눌러 주세요)"
        )
        ts = self._post_message(body)
        if not ts:
            raise RuntimeError("Slack chat.postMessage returned empty ts")

        bot_user = ""
        try:
            auth = self._api("auth.test", payload={})
            bot_user = str(auth.get("user_id") or "")
        except Exception as exc:  # noqa: BLE001
            print(f"   !! Slack auth.test failed: {exc}")

        try:
            self._add_reaction(ts, APPROVE_EMOJI)
            self._add_reaction(ts, SKIP_EMOJI)
        except Exception as exc:  # noqa: BLE001
            print(f"   !! Slack seed reactions failed: {exc}")
        print("   Slack preview (+images) sent — react ✅ or ⏭ …")

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data = self._reaction_data(ts)
                approve_users = [
                    u for u in self._reaction_users(data, APPROVE_EMOJI) if u != bot_user
                ]
                skip_users = [
                    u for u in self._reaction_users(data, SKIP_EMOJI) if u != bot_user
                ]
            except Exception as exc:  # noqa: BLE001
                response = getattr(exc, "response", None)
                if (
                    isinstance(response, requests.Response)
                    and response.status_code == 429
                ):
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else 2.0
                    except ValueError:
                        delay = 2.0
                    time.sleep(delay)
                    continue
                print(f"   !! Slack reaction poll error: {exc}")
                time.sleep(2)
                continue
            if approve_users:
                self.send_text("승인됨. 마크다운 저장(+선택 인스타)합니다.")
                return True
            if skip_users:
                self.send_text("스킵됨. 저장하지 않습니다.")
                return False
            time.sleep(2)

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
        if not self.token or not self.channel_id:
            raise RuntimeError("Slack gate requires SLACK_BOT_TOKEN and SLACK_CHANNEL_ID")

        stage_s = normalize_stage(stage)
        images = existing_image_paths(image_paths)
        uploaded_images: list[Path] = []
        for path in images:
            try:
                self._upload_file(path, f"카드 슬라이드: {path.name}")
                uploaded_images.append(path)
            except Exception as exc:  # noqa: BLE001
                print(f"   !! Slack image upload failed ({path.name}): {exc}")

        footer = gate_footer(
            stage_s,
            has_images=bool(uploaded_images),
            remaining=remaining,
            max_retries=max_retries,
            run_id=run_id,
            attempt=attempt,
        )
        body = preview[:3000] + footer
        ts = self._post_message(body)
        if not ts:
            raise RuntimeError("Slack chat.postMessage returned empty ts")

        bot_user = ""
        try:
            auth = self._api("auth.test", payload={})
            bot_user = str(auth.get("user_id") or "")
        except Exception as exc:  # noqa: BLE001
            print(f"   !! Slack auth.test failed: {exc}")

        mapping = _STAGE_EMOJIS[stage_s]
        try:
            for emoji, _action in mapping:
                self._add_reaction(ts, emoji)
        except Exception as exc:  # noqa: BLE001
            print(f"   !! Slack seed reactions failed: {exc}")
        print(f"   Slack {stage_s.value} gate sent — waiting…")

        deadline = time.time() + timeout
        reminder_sec = approve_reminder_sec()
        reminded = False
        while time.time() < deadline:
            remaining = deadline - time.time()
            if (
                not reminded
                and reminder_sec > 0
                and remaining <= reminder_sec
                and stage_s != GateStage.CLEANUP
            ):
                self.send_text(reminder_message(stage_s, int(remaining)))
                reminded = True
            try:
                data = self._reaction_data(ts)
                for emoji, action in mapping:
                    users = [u for u in self._reaction_users(data, emoji) if u != bot_user]
                    if users:
                        return action
            except Exception as exc:  # noqa: BLE001
                response = getattr(exc, "response", None)
                if (
                    isinstance(response, requests.Response)
                    and response.status_code == 429
                ):
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else 2.0
                    except ValueError:
                        delay = 2.0
                    time.sleep(delay)
                    continue
                print(f"   !! Slack reaction poll error: {exc}")
                time.sleep(2)
                continue
            time.sleep(2)

        self.send_text(timeout_message(stage_s, timeout, run_id=run_id))
        print(f"   {stage_s.value} gate timeout")
        return GateAction.TIMEOUT
