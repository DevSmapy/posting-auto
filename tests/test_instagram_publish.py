"""Logic tests for R2 → Instagram publish pipeline (no live Meta/R2 calls)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from publish import (  # noqa: E402
    InstagramCarouselPublisher,
    PublishCardsPipeline,
    PublishConfig,
    R2Uploader,
    caption_from_briefing,
)


def _cfg(**overrides: Any) -> PublishConfig:
    base = dict(
        publish_cards=True,
        ig_user_id="ig-user",
        meta_access_token="token",
        meta_graph_version="v21.0",
        caption_max_chars=2100,
        r2_endpoint="https://r2.example",
        r2_access_key_id="ak",
        r2_secret_access_key="sk",
        r2_bucket="bucket",
        r2_public_base_url="https://cdn.example",
        status_poll_attempts=5,
        status_poll_interval_sec=0.0,
    )
    base.update(overrides)
    return PublishConfig(**base)


class _FakeResp:
    def __init__(self, payload: dict[str, Any], ok: bool = True) -> None:
        self._payload = payload
        self._ok = ok

    def raise_for_status(self) -> None:
        if not self._ok:
            raise RuntimeError("http error")

    def json(self) -> dict[str, Any]:
        return self._payload


class CaptionFromBriefingTest(unittest.TestCase):
    def test_prefers_instagram_post(self) -> None:
        text = caption_from_briefing(
            {
                "instagram_post": "full post",
                "caption": "old",
                "hashtags": ["x"],
            }
        )
        self.assertEqual(text, "full post")

    def test_falls_back_to_caption_and_hashtags(self) -> None:
        text = caption_from_briefing(
            {"caption": "훅", "hashtags": ["경제뉴스", "#증시"]}
        )
        self.assertIn("훅", text)
        self.assertIn("#경제뉴스", text)
        self.assertIn("#증시", text)


class R2UploaderTest(unittest.TestCase):
    def test_upload_builds_public_urls(self) -> None:
        client = MagicMock()
        uploader = R2Uploader(_cfg(), client=client)
        paths = [Path("/tmp/slide-01.png"), Path("/tmp/slide-02.png")]
        urls = uploader.upload(paths, "briefs/2026-07-28")
        self.assertEqual(
            urls,
            [
                "https://cdn.example/briefs/2026-07-28/slide-01.png",
                "https://cdn.example/briefs/2026-07-28/slide-02.png",
            ],
        )
        self.assertEqual(client.upload_file.call_count, 2)
        first = client.upload_file.call_args_list[0]
        self.assertEqual(first.args[1], "bucket")
        self.assertEqual(first.args[2], "briefs/2026-07-28/slide-01.png")
        self.assertEqual(first.kwargs["ExtraArgs"]["ContentType"], "image/png")

    def test_incomplete_config_raises(self) -> None:
        uploader = R2Uploader(_cfg(r2_bucket=""))
        with self.assertRaises(RuntimeError):
            uploader.upload([Path("/tmp/a.png")], "prefix")


class InstagramCarouselPublisherTest(unittest.TestCase):
    def test_carousel_sequence(self) -> None:
        posts: list[tuple[str, dict[str, Any]]] = []
        gets: list[str] = []

        def post(url: str, data: dict[str, Any] | None = None, **_: Any) -> _FakeResp:
            posts.append((url, dict(data or {})))
            if url.endswith("/media_publish"):
                return _FakeResp({"id": "published-99"})
            if data and data.get("media_type") == "CAROUSEL":
                return _FakeResp({"id": "parent-1"})
            return _FakeResp({"id": f"child-{len(posts)}"})

        def get(url: str, params: dict[str, Any] | None = None, **_: Any) -> _FakeResp:
            gets.append(url)
            return _FakeResp({"status_code": "FINISHED"})

        sleeps: list[float] = []
        pub = InstagramCarouselPublisher(
            _cfg(),
            post=post,
            get=get,
            sleep=sleeps.append,
        )
        media_id = pub.publish(
            ["https://cdn.example/a.png", "https://cdn.example/b.png"],
            "caption body",
        )
        self.assertEqual(media_id, "published-99")
        self.assertEqual(len(posts), 4)  # 2 children + parent + publish
        self.assertEqual(posts[0][1]["is_carousel_item"], "true")
        self.assertEqual(posts[2][1]["media_type"], "CAROUSEL")
        self.assertEqual(posts[2][1]["children"], "child-1,child-2")
        self.assertEqual(posts[3][1]["creation_id"], "parent-1")
        self.assertEqual(len(gets), 1)

    def test_polls_until_finished(self) -> None:
        states = iter(["IN_PROGRESS", "FINISHED"])

        def post(url: str, data: dict[str, Any] | None = None, **_: Any) -> _FakeResp:
            if url.endswith("/media_publish"):
                return _FakeResp({"id": "ok"})
            if data and data.get("media_type") == "CAROUSEL":
                return _FakeResp({"id": "parent"})
            return _FakeResp({"id": "c1"})

        def get(*_: Any, **__: Any) -> _FakeResp:
            return _FakeResp({"status_code": next(states)})

        sleeps: list[float] = []
        pub = InstagramCarouselPublisher(
            _cfg(status_poll_interval_sec=0.0),
            post=post,
            get=get,
            sleep=sleeps.append,
        )
        pub.publish(["https://cdn.example/a.png"], "x")
        self.assertEqual(len(sleeps), 1)

    def test_error_status_raises(self) -> None:
        def post(url: str, data: dict[str, Any] | None = None, **_: Any) -> _FakeResp:
            if data and data.get("media_type") == "CAROUSEL":
                return _FakeResp({"id": "parent"})
            return _FakeResp({"id": "c1"})

        def get(*_: Any, **__: Any) -> _FakeResp:
            return _FakeResp({"status_code": "ERROR", "detail": "bad"})

        pub = InstagramCarouselPublisher(
            _cfg(),
            post=post,
            get=get,
            sleep=lambda _: None,
        )
        with self.assertRaises(RuntimeError) as ctx:
            pub.publish(["https://cdn.example/a.png"], "x")
        self.assertIn("IG container error", str(ctx.exception))

    def test_missing_credentials_raises(self) -> None:
        pub = InstagramCarouselPublisher(_cfg(ig_user_id="", meta_access_token=""))
        with self.assertRaises(RuntimeError):
            pub.publish(["https://cdn.example/a.png"], "x")

    def test_empty_urls_raises(self) -> None:
        pub = InstagramCarouselPublisher(_cfg())
        with self.assertRaises(ValueError):
            pub.publish([], "x")

    def test_truncates_caption(self) -> None:
        captured: dict[str, Any] = {}

        def post(url: str, data: dict[str, Any] | None = None, **_: Any) -> _FakeResp:
            if data and data.get("media_type") == "CAROUSEL":
                captured.update(data)
                return _FakeResp({"id": "parent"})
            if url.endswith("/media_publish"):
                return _FakeResp({"id": "ok"})
            return _FakeResp({"id": "c1"})

        pub = InstagramCarouselPublisher(
            _cfg(caption_max_chars=10),
            post=post,
            get=lambda *a, **k: _FakeResp({"status_code": "FINISHED"}),
            sleep=lambda _: None,
        )
        pub.publish(["https://cdn.example/a.png"], "0123456789abcdef")
        self.assertEqual(captured["caption"], "0123456789")


class PublishCardsPipelineTest(unittest.TestCase):
    def test_disabled_skips(self) -> None:
        result = PublishCardsPipeline(_cfg(publish_cards=False)).run(
            png_paths=[Path("/tmp/a.png")],
            briefing={},
            r2_prefix="briefs/x",
        )
        self.assertFalse(result.attempted)
        self.assertIsNone(result.ig_media_id)
        self.assertEqual(result.skipped_reason, "PUBLISH_CARDS disabled")

    def test_no_r2_skips_instagram(self) -> None:
        logs: list[str] = []
        result = PublishCardsPipeline(
            _cfg(r2_access_key_id=""),
            log=logs.append,
        ).run(
            png_paths=[Path("/tmp/a.png")],
            briefing={"instagram_post": "hi"},
            r2_prefix="briefs/x",
        )
        self.assertTrue(result.attempted)
        self.assertEqual(result.skipped_reason, "R2 not configured")
        self.assertTrue(any("R2 not configured" in m for m in logs))

    def test_happy_path(self) -> None:
        uploader = MagicMock()
        uploader.upload.return_value = ["https://cdn.example/a.png"]
        publisher = MagicMock()
        publisher.publish.return_value = "media-1"
        result = PublishCardsPipeline(
            _cfg(),
            uploader=uploader,
            publisher=publisher,
        ).run(
            png_paths=[Path("/tmp/a.png")],
            briefing={"instagram_post": "본문"},
            r2_prefix="briefs/2026-07-28",
        )
        self.assertEqual(result.ig_media_id, "media-1")
        self.assertEqual(result.image_urls, ["https://cdn.example/a.png"])
        self.assertIsNone(result.skipped_reason)
        publisher.publish.assert_called_once_with(
            ["https://cdn.example/a.png"], "본문"
        )

    def test_writes_image_urls_json(self) -> None:
        import tempfile

        uploader = MagicMock()
        uploader.upload.return_value = ["https://cdn.example/a.png"]
        publisher = MagicMock()
        publisher.publish.return_value = "media-1"
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            PublishCardsPipeline(
                _cfg(),
                uploader=uploader,
                publisher=publisher,
            ).run(
                png_paths=[Path("/tmp/a.png")],
                briefing={"instagram_post": "x"},
                r2_prefix="briefs/x",
                run_dir=run_dir,
            )
            saved = (run_dir / "image_urls.json").read_text(encoding="utf-8")
            self.assertIn("https://cdn.example/a.png", saved)


if __name__ == "__main__":
    unittest.main()
