"""Instagram Content Publishing API — carousel (docs/05, Meta Graph)."""

from __future__ import annotations

import time
from typing import Any, Callable

import requests

from .config import PublishConfig

HttpPost = Callable[..., Any]
HttpGet = Callable[..., Any]
Sleeper = Callable[[float], None]


class InstagramCarouselPublisher:
    """Publish a carousel via Meta Graph API (children → CAROUSEL → media_publish).

    Flow matches Instagram Content Publishing:
    1. Create carousel item containers (``is_carousel_item=true``)
    2. Create parent CAROUSEL container with caption
    3. Poll ``status_code`` until FINISHED (or ERROR)
    4. ``media_publish`` with ``creation_id``

    Steps 1–3 are ``create_containers``; step 4 is ``media_publish``.
    ``publish`` runs both (end-to-end, same as before).
    """

    def __init__(
        self,
        config: PublishConfig,
        *,
        post: HttpPost | None = None,
        get: HttpGet | None = None,
        sleep: Sleeper | None = None,
    ) -> None:
        self.config = config
        self._post = post or requests.post
        self._get = get or requests.get
        self._sleep = sleep or time.sleep

    def create_containers(self, image_urls: list[str], caption: str) -> str:
        """Create child + parent containers; wait until FINISHED. Returns creation_id."""
        if not image_urls:
            raise ValueError("instagram carousel requires at least one image_url")
        n = len(image_urls)
        if n < 2 or n > 10:
            raise ValueError(
                f"instagram carousel requires 2-10 images, got {n}"
            )
        if not self.config.instagram_configured:
            raise RuntimeError("IG_USER_ID / META_ACCESS_TOKEN required")

        ig_user = self.config.ig_user_id
        token = self.config.meta_access_token
        base = self.config.graph_base_url
        max_chars = self.config.caption_max_chars

        children: list[str] = []
        for url in image_urls:
            r = self._post(
                f"{base}/{ig_user}/media",
                data={
                    "image_url": url,
                    "is_carousel_item": "true",
                    "access_token": token,
                },
                timeout=60,
            )
            r.raise_for_status()
            children.append(r.json()["id"])

        parent = self._post(
            f"{base}/{ig_user}/media",
            data={
                "media_type": "CAROUSEL",
                "children": ",".join(children),
                "caption": (caption or "")[:max_chars],
                "access_token": token,
            },
            timeout=60,
        )
        parent.raise_for_status()
        creation_id = str(parent.json()["id"])

        self._wait_until_finished(base, creation_id, token)
        return creation_id

    def media_publish(self, creation_id: str) -> str:
        """Publish a finished container via ``media_publish``."""
        if not self.config.instagram_configured:
            raise RuntimeError("IG_USER_ID / META_ACCESS_TOKEN required")
        if not creation_id:
            raise ValueError("creation_id required")

        ig_user = self.config.ig_user_id
        token = self.config.meta_access_token
        base = self.config.graph_base_url

        pub = self._post(
            f"{base}/{ig_user}/media_publish",
            data={"creation_id": creation_id, "access_token": token},
            timeout=60,
        )
        pub.raise_for_status()
        return str(pub.json().get("id", creation_id))

    def publish(self, image_urls: list[str], caption: str) -> str:
        creation_id = self.create_containers(image_urls, caption)
        return self.media_publish(creation_id)

    def _wait_until_finished(
        self, base: str, creation_id: str, token: str
    ) -> None:
        attempts = max(1, self.config.status_poll_attempts)
        interval = max(0.0, self.config.status_poll_interval_sec)
        last: dict[str, Any] = {}
        for attempt in range(attempts):
            st = self._get(
                f"{base}/{creation_id}",
                params={"fields": "status_code", "access_token": token},
                timeout=30,
            )
            st.raise_for_status()
            last = st.json()
            code = last.get("status_code")
            if code == "FINISHED":
                return
            if code == "ERROR":
                raise RuntimeError(f"IG container error: {last}")
            if attempt + 1 < attempts:
                self._sleep(interval)
        raise RuntimeError(
            f"IG container not ready after {attempts} polls: {last}"
        )


def caption_from_briefing(briefing: dict[str, Any]) -> str:
    """Prefer assembled ``instagram_post``, else caption + hashtags."""
    direct = (briefing.get("instagram_post") or "").strip()
    if direct:
        return direct
    caption = (briefing.get("caption") or "").strip()
    tags = " ".join(
        f"#{str(t).lstrip('#')}" for t in (briefing.get("hashtags") or []) if t
    )
    return "\n\n".join(p for p in (caption, tags) if p).strip()
