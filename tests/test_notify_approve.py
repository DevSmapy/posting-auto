"""Logic tests for Approve notifiers (no live Discord/Telegram/Slack calls)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from notify.approve_copy import approve_footer, existing_image_paths  # noqa: E402
from notify.auto import AutoNotifier  # noqa: E402
from notify.cli import CliNotifier  # noqa: E402
from notify.factory import get_notifier, resolve_channel  # noqa: E402


class ApproveCopyTest(unittest.TestCase):
    def test_footer_with_images(self) -> None:
        text = approve_footer(has_images=True)
        self.assertIn("슬라이드 이미지를 확인한 뒤 Approve", text)

    def test_footer_without_images(self) -> None:
        text = approve_footer(has_images=False)
        self.assertIn("카드 이미지 생성 실패", text)

    def test_existing_image_paths_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok = Path(tmp) / "a.png"
            ok.write_bytes(b"png")
            missing = Path(tmp) / "missing.png"
            paths = existing_image_paths([ok, missing])
            self.assertEqual(paths, [ok])


class FactoryChannelTest(unittest.TestCase):
    def test_explicit_slack(self) -> None:
        with patch.dict("os.environ", {"NOTIFY_CHANNEL": "slack"}, clear=False):
            self.assertEqual(resolve_channel(), "slack")

    def test_discord_preferred_when_configured(self) -> None:
        env = {
            "NOTIFY_CHANNEL": "",
            "DISCORD_BOT_TOKEN": "d",
            "DISCORD_CHANNEL_ID": "1",
            "TELEGRAM_BOT_TOKEN": "t",
            "TELEGRAM_CHAT_ID": "2",
            "SLACK_BOT_TOKEN": "s",
            "SLACK_CHANNEL_ID": "3",
            "APPROVE_MODE": "",
            "TELEGRAM_APPROVE_MODE": "",
        }
        with patch.dict("os.environ", env, clear=False):
            self.assertEqual(resolve_channel(), "discord")
            self.assertEqual(get_notifier().name, "discord")

    def test_slack_notifier_selected(self) -> None:
        with patch.dict("os.environ", {"NOTIFY_CHANNEL": "slack"}, clear=False):
            self.assertEqual(get_notifier().name, "slack")


class AutoCliApproveTest(unittest.TestCase):
    def test_auto_accepts_image_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "s.png"
            img.write_bytes(b"x")
            self.assertTrue(AutoNotifier().wait_for_approve("preview", [img]))

    def test_cli_approve(self) -> None:
        with patch("builtins.input", return_value="approve"):
            ok = CliNotifier().wait_for_approve("preview", image_paths=[])
        self.assertTrue(ok)

    def test_cli_skip(self) -> None:
        with patch("builtins.input", return_value="skip"):
            ok = CliNotifier().wait_for_approve("preview", image_paths=[])
        self.assertFalse(ok)


class DiscordWaitApproveTest(unittest.TestCase):
    def test_posts_images_then_approve_reaction(self) -> None:
        from notify.discord import DiscordNotifier

        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "slide-01.png"
            img.write_bytes(b"png-bytes")
            n = DiscordNotifier()
            n.token = "tok"
            n.channel_id = "ch"

            calls: list[str] = []

            def fake_request(method: str, path: str, **kwargs):  # noqa: ANN003
                calls.append(f"{method} {path}")
                if path == "/users/@me":
                    return {"id": "bot"}
                if path.endswith("/reactions/%E2%9C%85"):  # ✅ encoded differently — use endswith check
                    return [{"id": "bot"}, {"id": "human", "bot": False}]
                if "/reactions/" in path:
                    return [{"id": "bot"}]
                if method == "POST" and path.endswith("/messages"):
                    return {"id": "msg1"}
                return {}

            n._request = fake_request  # type: ignore[method-assign]
            n._post_files = MagicMock(return_value="msg1")  # type: ignore[method-assign]
            n._add_reaction = MagicMock()  # type: ignore[method-assign]
            n.send_text = MagicMock()  # type: ignore[method-assign]

            # First poll: only bot on approve; second: human approve
            react_state = {"n": 0}

            def reaction_users(message_id: str, emoji: str):
                react_state["n"] += 1
                if emoji == "✅" and react_state["n"] >= 2:
                    return [{"id": "human", "bot": False}]
                return [{"id": "bot"}]

            n._reaction_users = reaction_users  # type: ignore[method-assign]

            with patch("notify.discord.approve_timeout_sec", return_value=5):
                with patch("notify.discord.time.sleep", return_value=None):
                    ok = n.wait_for_approve("hello", image_paths=[img])
            self.assertTrue(ok)
            n._post_files.assert_called_once()
            args = n._post_files.call_args[0]
            self.assertEqual(args[0], [img])


class SlackWaitApproveTest(unittest.TestCase):
    def test_uploads_then_approve(self) -> None:
        from notify.slack import SlackNotifier

        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "slide-01.png"
            img.write_bytes(b"png")
            n = SlackNotifier()
            n.token = "xoxb-test"
            n.channel_id = "C1"
            n._upload_file = MagicMock()  # type: ignore[method-assign]
            n._post_message = MagicMock(return_value="123.456")  # type: ignore[method-assign]
            n._add_reaction = MagicMock()  # type: ignore[method-assign]
            n.send_text = MagicMock()  # type: ignore[method-assign]
            n._api = MagicMock(return_value={"user_id": "B0", "ok": True})  # type: ignore[method-assign]

            state = {"n": 0}

            def reaction_users(ts: str, name: str):
                state["n"] += 1
                if name == "white_check_mark" and state["n"] >= 2:
                    return ["U_HUMAN"]
                return ["B0"]

            n._reaction_users = reaction_users  # type: ignore[method-assign]
            with patch("notify.slack.approve_timeout_sec", return_value=5):
                with patch("notify.slack.time.sleep", return_value=None):
                    ok = n.wait_for_approve("preview", [img])
            self.assertTrue(ok)
            n._upload_file.assert_called()


if __name__ == "__main__":
    unittest.main()
