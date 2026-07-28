"""Logic tests for run_publish partial success / card reuse."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mvp_pipeline import run_publish  # noqa: E402
from publish import PublishCardsResult, PublishConfig  # noqa: E402


class _FakeStore:
    backend = "memory"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record_published(self, picked, tistory_post_id=None, ig_media_id=None):  # noqa: ANN001
        self.calls.append(
            {
                "picked": picked,
                "tistory_post_id": tistory_post_id,
                "ig_media_id": ig_media_id,
            }
        )
        return len(picked)


class _FakeNotifier:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.files: list[Path] = []

    def send_text(self, text: str) -> None:
        self.texts.append(text)

    def send_file(self, path: Path, caption: str = "") -> None:
        self.files.append(path)


class RunPublishTest(unittest.TestCase):
    def test_reuses_pngs_and_records_seen_on_ig_skip(self) -> None:
        briefing = {
            "title": "t",
            "blog_markdown": "# hi",
            "blog_html": "<p>hi</p>",
            "instagram_post": "cap",
        }
        # assemble_blog_markdown may need more fields — patch it
        notifier = _FakeNotifier()
        store = _FakeStore()
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png = run_dir / "slide-01.png"
            png.write_bytes(b"x")
            cfg = PublishConfig(
                publish_cards=True,
                ig_user_id="ig",
                meta_access_token="tok",
                r2_endpoint="https://r2",
                r2_access_key_id="",
                r2_secret_access_key="",
                r2_bucket="",
                r2_public_base_url="",
            )
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
                patch("mvp_pipeline.PublishCardsPipeline") as pipe_cls,
            ):
                pipe = MagicMock()
                pipe.run.return_value = PublishCardsResult(
                    attempted=True,
                    image_urls=[],
                    ig_media_id=None,
                    skipped_reason="R2 not configured",
                )
                pipe_cls.return_value = pipe
                run_publish(
                    briefing,
                    [{"url": "http://a", "title": "A"}],
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png],
                )
                pipe.run.assert_called_once()
                kwargs = pipe.run.call_args.kwargs
                self.assertEqual(kwargs["png_paths"], [png])
        self.assertEqual(len(store.calls), 1)
        self.assertIsNone(store.calls[0]["ig_media_id"])
        self.assertTrue(
            any("부분스킵" in t or "R2 not configured" in t for t in notifier.texts)
        )

    def test_ig_failure_still_records_markdown(self) -> None:
        briefing = {"title": "t"}
        notifier = _FakeNotifier()
        store = _FakeStore()
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        cfg = PublishConfig(
            publish_cards=True,
            ig_user_id="ig",
            meta_access_token="tok",
            r2_endpoint="https://r2",
            r2_access_key_id="ak",
            r2_secret_access_key="sk",
            r2_bucket="b",
            r2_public_base_url="https://cdn",
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png = run_dir / "a.png"
            png.write_bytes(b"x")
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
                patch("mvp_pipeline.PublishCardsPipeline") as pipe_cls,
            ):
                pipe = MagicMock()
                pipe.run.side_effect = RuntimeError("graph down")
                pipe_cls.return_value = pipe
                run_publish(
                    briefing,
                    [{"url": "http://a", "title": "A"}],
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png],
                )
            self.assertTrue((run_dir / "briefing.md").is_file())
        self.assertEqual(len(store.calls), 1)
        self.assertTrue(any("R2/인스타 실패" in t for t in notifier.texts))


if __name__ == "__main__":
    unittest.main()
