"""Tests for persist_seen modes and publish guard integration."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from mvp_pipeline import (  # noqa: E402
    adopt_infographic,
    gate_image_paths,
    run_publish,
)
from publish import PublishCardsResult, PublishConfig  # noqa: E402


def _good_story(i: int = 1) -> dict:
    return {
        "headline": f"원·달러 환율 하루 만에 {i}0원 하락",
        "what_happened": "서울 외환시장에서 원·달러 환율이 전일 대비 빠르게 떨어졌습니다.",
        "why_important": "환율 하락은 수입 물가와 수출 기업 채산성에 동시에 영향을 줍니다.",
        "watch_next": "미국 고용지표 발표와 당국의 구두 개입 여부를 확인해야 합니다.",
        "one_liner": "환율이 빠르게 내려 수입·수출 셈법이 바뀌고 있습니다.",
        "source_url": f"https://example.com/{i}",
    }


def _briefing(n: int = 3) -> dict:
    stories = [_good_story(i) for i in range(1, n + 1)]
    return {
        "title": "t",
        "blog_html": "<p>hi</p>",
        "instagram_post": "한국어 캡션입니다.",
        "stories": stories,
    }


def _picked(n: int = 3) -> list[dict]:
    return [
        {"url": f"https://example.com/{i}", "link": f"https://example.com/{i}", "title": f"A{i}"}
        for i in range(1, n + 1)
    ]


class _FakeStore:
    backend = "memory"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def reopen(self) -> None:
        return None

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


class InfographicHandoffTest(unittest.TestCase):
    """The infographic rides beside briefing.md, never inside the card list."""

    def test_gate_shows_the_infographic_first_without_joining_the_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            render_dir = Path(tmp)
            (render_dir / "infographic").mkdir()
            info = render_dir / "infographic" / "infographic.png"
            info.write_bytes(b"png")
            cards = [render_dir / "slide-01.png", render_dir / "slide-02.png"]
            self.assertEqual([info, *cards], gate_image_paths(render_dir, cards))
            self.assertEqual(2, len(cards))

    def test_gate_falls_back_to_cards_only_when_the_render_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cards = [Path(tmp) / "slide-01.png"]
            self.assertEqual(cards, gate_image_paths(Path(tmp), cards))

    def test_approved_render_is_copied_next_to_the_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            render_dir = Path(tmp) / "renders" / "render-02"
            (render_dir / "infographic").mkdir(parents=True)
            run_dir.mkdir()
            source = render_dir / "infographic" / "infographic.png"
            source.write_bytes(b"png")
            self.assertEqual("infographic.png", adopt_infographic(run_dir, source))
            self.assertEqual(b"png", (run_dir / "infographic.png").read_bytes())

    def test_missing_render_yields_no_markdown_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual("", adopt_infographic(Path(tmp)))
            self.assertFalse((Path(tmp) / "infographic.png").exists())

    def test_run_publish_links_the_image_it_copied(self) -> None:
        notifier = _FakeNotifier()
        store = _FakeStore()
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        cfg = PublishConfig(
            publish_cards=False,
            ig_user_id="",
            meta_access_token="",
            r2_endpoint="",
            r2_access_key_id="",
            r2_secret_access_key="",
            r2_bucket="",
            r2_public_base_url="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "renders" / "infographic.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"png")
            with (
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
            ):
                run_publish(
                    _briefing(),
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    persist_seen="never",
                    editorial_decision={"decision": "publish", "story_count": 3},
                    infographic_path=source,
                )
            md = (run_dir / "briefing.md").read_text(encoding="utf-8")
            self.assertIn("![브리핑 인포그래픽](infographic.png)", md)
            self.assertTrue((run_dir / "infographic.png").is_file())


class RunPublishTest(unittest.TestCase):
    def test_reuses_pngs_and_records_seen_on_ig_skip(self) -> None:
        notifier = _FakeNotifier()
        store = _FakeStore()
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png = run_dir / "slide-01.png"
            png.write_bytes(b"x")
            png2 = run_dir / "slide-02.png"
            png2.write_bytes(b"y")
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
                    _briefing(),
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png, png2],
                    persist_seen="after_export",
                )
                pipe.run.assert_called_once()
        self.assertEqual(len(store.calls), 1)
        self.assertIsNone(store.calls[0]["ig_media_id"])
        self.assertTrue(
            any("부분스킵" in t or "R2 not configured" in t for t in notifier.texts)
        )

    def test_dry_run_never_records_seen(self) -> None:
        notifier = _FakeNotifier()
        store = _FakeStore()
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        cfg = PublishConfig(
            publish_cards=False,
            ig_user_id="",
            meta_access_token="",
            r2_endpoint="",
            r2_access_key_id="",
            r2_secret_access_key="",
            r2_bucket="",
            r2_public_base_url="",
        )
        decision = {"decision": "publish", "story_count": 3}
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
            ):
                run_publish(
                    _briefing(),
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    persist_seen="never",
                    editorial_decision=decision,
                )
            self.assertTrue((run_dir / "briefing.md").is_file())
            self.assertTrue((run_dir / "publish_guard.json").is_file())
        self.assertEqual(len(store.calls), 0)

    def test_after_ig_records_only_on_success(self) -> None:
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
        decision = {"decision": "publish", "story_count": 3}
        preflight = {"ok": True, "checks": []}
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png1 = run_dir / "a.png"
            png2 = run_dir / "b.png"
            png1.write_bytes(b"x")
            png2.write_bytes(b"y")
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
                patch("mvp_pipeline.PublishCardsPipeline") as pipe_cls,
                patch.dict("os.environ", {"EDITORIAL_LLM_REVIEWER": "1"}, clear=False),
            ):
                pipe = MagicMock()
                pipe.run.return_value = PublishCardsResult(
                    attempted=True,
                    image_urls=["https://cdn/a.png"],
                    ig_media_id="ig_123",
                    skipped_reason=None,
                )
                pipe_cls.return_value = pipe
                run_publish(
                    _briefing(),
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png1, png2],
                    persist_seen="after_ig",
                    live_publish=True,
                    editorial_decision=decision,
                    preflight=preflight,
                )
        self.assertEqual(len(store.calls), 1)
        self.assertEqual(store.calls[0]["ig_media_id"], "ig_123")

    def test_ig_failure_after_ig_does_not_record(self) -> None:
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
        decision = {"decision": "publish", "story_count": 3}
        preflight = {"ok": True, "checks": []}
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png1 = run_dir / "a.png"
            png2 = run_dir / "b.png"
            png1.write_bytes(b"x")
            png2.write_bytes(b"y")
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
                patch("mvp_pipeline.PublishCardsPipeline") as pipe_cls,
                patch.dict("os.environ", {"EDITORIAL_LLM_REVIEWER": "1"}, clear=False),
            ):
                pipe = MagicMock()
                pipe.run.side_effect = RuntimeError("graph down")
                pipe_cls.return_value = pipe
                run_publish(
                    _briefing(),
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png1, png2],
                    persist_seen="after_ig",
                    live_publish=True,
                    editorial_decision=decision,
                    preflight=preflight,
                )
        self.assertEqual(len(store.calls), 0)
        self.assertTrue(any("ACTION REQUIRED" in t for t in notifier.texts))

    def test_notify_failure_still_records_seen_urls(self) -> None:
        events: list[str] = []
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)

        class _OrderedStore(_FakeStore):
            def record_published(self, picked, tistory_post_id=None, ig_media_id=None):  # noqa: ANN001
                events.append("record")
                return super().record_published(
                    picked,
                    tistory_post_id=tistory_post_id,
                    ig_media_id=ig_media_id,
                )

        class _BoomNotifier:
            def send_text(self, text: str) -> None:
                events.append("notify")
                raise RuntimeError("channel down")

            def send_file(self, path: Path, caption: str = "") -> None:
                events.append("notify")
                raise RuntimeError("channel down")

        store = _OrderedStore()
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            cfg = PublishConfig(
                publish_cards=False,
                ig_user_id="",
                meta_access_token="",
                r2_endpoint="",
                r2_access_key_id="",
                r2_secret_access_key="",
                r2_bucket="",
                r2_public_base_url="",
            )
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
            ):
                run_publish(
                    _briefing(),
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    _BoomNotifier(),
                    persist_seen="after_export",
                )
        self.assertEqual(len(store.calls), 1)
        self.assertIn("record", events)
        self.assertIn("notify", events)

    def test_live_guard_blocks_chinese_caption(self) -> None:
        notifier = _FakeNotifier()
        store = _FakeStore()
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        briefing = _briefing()
        briefing["instagram_post"] = "中国市场今天上涨。"
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
        decision = {"decision": "publish", "story_count": 3}
        preflight = {"ok": True, "checks": []}
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png1 = run_dir / "a.png"
            png2 = run_dir / "b.png"
            png1.write_bytes(b"x")
            png2.write_bytes(b"y")
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
                patch("mvp_pipeline.PublishCardsPipeline") as pipe_cls,
                patch.dict(
                    "os.environ",
                    {"EDITORIAL_LLM_REVIEWER": "1", "TARGET_LANGUAGE": "ko"},
                    clear=False,
                ),
            ):
                pipe = MagicMock()
                pipe_cls.return_value = pipe
                outcome = run_publish(
                    briefing,
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png1, png2],
                    persist_seen="after_ig",
                    live_publish=True,
                    editorial_decision=decision,
                    preflight=preflight,
                )
                pipe.run.assert_not_called()
        self.assertFalse(outcome.get("ok"))
        self.assertEqual(outcome.get("reason"), "publish_guard")
        self.assertEqual(len(store.calls), 0)

    def test_live_reviewer_disabled_does_not_call_pipeline(self) -> None:
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
        decision = {"decision": "publish", "story_count": 3}
        preflight = {"ok": True, "checks": []}
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png1 = run_dir / "a.png"
            png2 = run_dir / "b.png"
            png1.write_bytes(b"x")
            png2.write_bytes(b"y")
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
                patch("mvp_pipeline.PublishCardsPipeline") as pipe_cls,
                patch.dict(
                    "os.environ",
                    {"AUTO_PUBLISH": "true", "EDITORIAL_LLM_REVIEWER": "0"},
                    clear=False,
                ),
            ):
                pipe = MagicMock()
                pipe_cls.return_value = pipe
                outcome = run_publish(
                    _briefing(),
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png1, png2],
                    persist_seen="after_ig",
                    live_publish=True,
                    editorial_decision=decision,
                    preflight=preflight,
                )
                pipe.run.assert_not_called()
        self.assertFalse(outcome.get("ok"))
        self.assertEqual(outcome.get("reason"), "publish_guard")
        self.assertEqual(len(store.calls), 0)

    def test_live_without_ig_media_id_fails(self) -> None:
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
        decision = {"decision": "publish", "story_count": 3}
        preflight = {"ok": True, "checks": []}
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png1 = run_dir / "a.png"
            png2 = run_dir / "b.png"
            png1.write_bytes(b"x")
            png2.write_bytes(b"y")
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
                patch("mvp_pipeline.PublishCardsPipeline") as pipe_cls,
                patch.dict("os.environ", {"EDITORIAL_LLM_REVIEWER": "1"}, clear=False),
            ):
                pipe = MagicMock()
                pipe.run.return_value = PublishCardsResult(
                    attempted=True,
                    image_urls=["https://cdn/a.png"],
                    ig_media_id=None,
                    skipped_reason=None,
                )
                pipe_cls.return_value = pipe
                outcome = run_publish(
                    _briefing(),
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png1, png2],
                    persist_seen="after_ig",
                    live_publish=True,
                    editorial_decision=decision,
                    preflight=preflight,
                )
                pipe.run.assert_called_once()
        self.assertFalse(outcome.get("ok"))
        self.assertEqual(outcome.get("reason"), "missing_ig_media_id")
        self.assertEqual(len(store.calls), 0)
        self.assertTrue(any("ACTION REQUIRED" in t for t in notifier.texts))

    def test_live_package_only_exports_without_media(self) -> None:
        notifier = _FakeNotifier()
        store = _FakeStore()
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        cfg = PublishConfig(
            publish_cards=True,
            publish_mode="package",
            ig_user_id="ig",
            meta_access_token="tok",
            r2_endpoint="https://r2",
            r2_access_key_id="ak",
            r2_secret_access_key="sk",
            r2_bucket="b",
            r2_public_base_url="https://cdn",
        )
        decision = {"decision": "publish", "story_count": 3}
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png1 = run_dir / "a.png"
            png2 = run_dir / "b.png"
            png1.write_bytes(b"x")
            png2.write_bytes(b"y")
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
                patch("mvp_pipeline.PublishCardsPipeline") as pipe_cls,
            ):
                pipe = MagicMock()
                pipe_cls.return_value = pipe
                outcome = run_publish(
                    _briefing(),
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png1, png2],
                    persist_seen="never",
                    live_publish=True,
                    editorial_decision=decision,
                )
                pipe.run.assert_not_called()
        self.assertTrue(outcome.get("ok"))
        self.assertEqual(outcome.get("reason"), "exported")
        self.assertEqual(len(store.calls), 0)

    def test_after_ig_record_failure_fails_live(self) -> None:
        class _BoomStore(_FakeStore):
            def record_published(self, picked, tistory_post_id=None, ig_media_id=None):  # noqa: ANN001
                raise RuntimeError("db down")

        notifier = _FakeNotifier()
        store = _BoomStore()
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
        decision = {"decision": "publish", "story_count": 3}
        preflight = {"ok": True, "checks": []}
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png1 = run_dir / "a.png"
            png2 = run_dir / "b.png"
            png1.write_bytes(b"x")
            png2.write_bytes(b"y")
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
                patch("mvp_pipeline.PublishCardsPipeline") as pipe_cls,
                patch("mvp_pipeline.time.sleep"),
                patch.dict("os.environ", {"EDITORIAL_LLM_REVIEWER": "1"}, clear=False),
            ):
                pipe = MagicMock()
                pipe.run.return_value = PublishCardsResult(
                    attempted=True,
                    image_urls=["https://cdn/a.png"],
                    ig_media_id="ig_123",
                    skipped_reason=None,
                )
                pipe_cls.return_value = pipe
                outcome = run_publish(
                    _briefing(),
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png1, png2],
                    persist_seen="after_ig",
                    live_publish=True,
                    editorial_decision=decision,
                    preflight=preflight,
                )
        self.assertFalse(outcome.get("ok"))
        self.assertEqual(outcome.get("reason"), "seen_urls_unrecorded")
        self.assertEqual(outcome.get("ig_media_id"), "ig_123")
        self.assertTrue(any("ACTION REQUIRED" in t for t in notifier.texts))

    def test_after_ig_empty_picked_fails_live(self) -> None:
        notifier = _FakeNotifier()
        store = _FakeStore()
        now = datetime(2026, 7, 28, tzinfo=timezone.utc)
        briefing = _briefing()
        for story in briefing["stories"]:
            story.pop("source_url", None)
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
        decision = {"decision": "publish", "story_count": 3}
        preflight = {"ok": True, "checks": []}
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            png1 = run_dir / "a.png"
            png2 = run_dir / "b.png"
            png1.write_bytes(b"x")
            png2.write_bytes(b"y")
            with (
                patch("mvp_pipeline.assemble_blog_markdown", return_value="# md"),
                patch("mvp_pipeline.assemble_blog_html", return_value="<p>x</p>"),
                patch("mvp_pipeline.PublishConfig.from_env", return_value=cfg),
                patch("mvp_pipeline.PublishCardsPipeline") as pipe_cls,
                patch.dict("os.environ", {"EDITORIAL_LLM_REVIEWER": "1"}, clear=False),
            ):
                pipe = MagicMock()
                pipe.run.return_value = PublishCardsResult(
                    attempted=True,
                    image_urls=["https://cdn/a.png"],
                    ig_media_id="ig_123",
                    skipped_reason=None,
                )
                pipe_cls.return_value = pipe
                outcome = run_publish(
                    briefing,
                    _picked(),
                    now,
                    run_dir,
                    store,  # type: ignore[arg-type]
                    notifier,
                    card_png_paths=[png1, png2],
                    persist_seen="after_ig",
                    live_publish=True,
                    editorial_decision=decision,
                    preflight=preflight,
                )
        self.assertFalse(outcome.get("ok"))
        self.assertEqual(outcome.get("reason"), "seen_urls_unrecorded")
        self.assertEqual(len(store.calls), 1)
        self.assertEqual(store.calls[0]["picked"], [])


class NotifyAfterDeadlineTest(unittest.TestCase):
    def test_waits_once_then_forwards(self) -> None:
        from mvp_pipeline import _NotifyAfterDeadline

        calls: list[object] = []

        class Fake:
            def send_text(self, message: str) -> str:
                calls.append(message)
                return "ok"

            def other(self) -> str:
                return "passthrough"

        wrapped = _NotifyAfterDeadline(Fake())
        with patch(
            "mvp_pipeline.wait_until_notify_send_at",
            side_effect=lambda: calls.append("wait"),
        ):
            wrapped.send_text("one")
            wrapped.send_text("two")
        self.assertEqual(calls, ["wait", "one", "two"])
        self.assertEqual(wrapped.other(), "passthrough")


if __name__ == "__main__":
    unittest.main()
