"""Optional Approve-after step: cards already rendered → R2 → Instagram."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import PublishConfig
from .instagram import InstagramCarouselPublisher, caption_from_briefing
from .r2 import R2Uploader


@dataclass(frozen=True)
class PublishCardsResult:
    """Outcome of the optional Instagram publish path."""

    attempted: bool
    image_urls: list[str]
    ig_media_id: str | None
    skipped_reason: str | None = None
    creation_id: str | None = None


LogFn = Callable[[str], None]


class PublishCardsPipeline:
    """R2 upload + Instagram carousel after local card PNG export.

    Card HTML/PNG rendering stays in ``mvp_pipeline.render_cards`` /
    ``scripts.cards``; this class only covers hosting + Graph publish.
    """

    def __init__(
        self,
        config: PublishConfig | None = None,
        *,
        uploader: R2Uploader | None = None,
        publisher: InstagramCarouselPublisher | None = None,
        log: LogFn | None = None,
    ) -> None:
        self.config = config or PublishConfig.from_env()
        self.uploader = uploader or R2Uploader(self.config)
        self.publisher = publisher or InstagramCarouselPublisher(self.config)
        self._log = log or (lambda _msg: None)

    def run(
        self,
        *,
        png_paths: list[Path],
        briefing: dict[str, Any],
        r2_prefix: str,
        run_dir: Path | None = None,
    ) -> PublishCardsResult:
        if not self.config.publish_cards:
            return PublishCardsResult(
                attempted=False,
                image_urls=[],
                ig_media_id=None,
                skipped_reason="PUBLISH_CARDS disabled",
            )

        if not png_paths:
            return PublishCardsResult(
                attempted=True,
                image_urls=[],
                ig_media_id=None,
                skipped_reason="no PNG paths",
            )

        n = len(png_paths)
        if n < 2 or n > 10:
            return PublishCardsResult(
                attempted=True,
                image_urls=[],
                ig_media_id=None,
                skipped_reason=f"need 2-10 PNGs, got {n}",
            )

        if not self.config.r2_configured:
            self._log("R2 not configured — skip Instagram (local cards kept)")
            return PublishCardsResult(
                attempted=True,
                image_urls=[],
                ig_media_id=None,
                skipped_reason="R2 not configured",
            )

        self._log("Upload R2")
        image_urls = self.uploader.upload(png_paths, r2_prefix)
        if run_dir is not None:
            (run_dir / "image_urls.json").write_text(
                json.dumps(image_urls, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if self.config.package_only:
            self._log("PUBLISH_MODE=package — skip media_publish (use publish_ready CLI)")
            return PublishCardsResult(
                attempted=True,
                image_urls=image_urls,
                ig_media_id=None,
                skipped_reason="PUBLISH_MODE=package",
            )

        if not self.config.instagram_configured:
            self._log("Instagram not configured — R2 URLs saved")
            return PublishCardsResult(
                attempted=True,
                image_urls=image_urls,
                ig_media_id=None,
                skipped_reason="Instagram not configured",
            )

        caption = caption_from_briefing(briefing)
        self._log("Instagram create_containers")
        creation_id = self.publisher.create_containers(image_urls, caption)
        if run_dir is not None:
            (run_dir / "creation_id.json").write_text(
                json.dumps({"creation_id": creation_id}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
        self._log("Instagram media_publish")
        ig_media_id = self.publisher.media_publish(creation_id)
        self._log(f"ig media id: {ig_media_id}")
        return PublishCardsResult(
            attempted=True,
            image_urls=image_urls,
            ig_media_id=ig_media_id,
            skipped_reason=None,
            creation_id=creation_id,
        )
