"""Publishing config for R2 upload and Instagram Graph API."""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _truthy(raw: str) -> bool:
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PublishConfig:
    """Env-backed settings for optional card → R2 → Instagram publish."""

    publish_cards: bool = False
    publish_mode: str = "publish"
    ig_user_id: str = ""
    meta_access_token: str = ""
    meta_graph_version: str = "v21.0"
    caption_max_chars: int = 2100
    r2_endpoint: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_public_base_url: str = ""
    status_poll_attempts: int = 20
    status_poll_interval_sec: float = 3.0

    @classmethod
    def from_env(cls) -> PublishConfig:
        raw_mode = _env("PUBLISH_MODE", "publish") or "publish"
        mode = raw_mode.lower()
        if mode not in {"publish", "package"}:
            warnings.warn(
                f"Unrecognized PUBLISH_MODE={raw_mode!r}; falling back to 'package'",
                UserWarning,
                stacklevel=2,
            )
            mode = "package"
        return cls(
            publish_cards=_truthy(_env("PUBLISH_CARDS", "0")),
            publish_mode=mode,
            ig_user_id=_env("IG_USER_ID"),
            meta_access_token=_env("META_ACCESS_TOKEN"),
            meta_graph_version=_env("META_GRAPH_VERSION", "v21.0") or "v21.0",
            caption_max_chars=int(
                _env("CARD_CAPTION_MAX_CHARS", "2100") or "2100"
            ),
            r2_endpoint=_env("R2_ENDPOINT"),
            r2_access_key_id=_env("R2_ACCESS_KEY_ID"),
            r2_secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
            r2_bucket=_env("R2_BUCKET"),
            r2_public_base_url=_env("R2_PUBLIC_BASE_URL").rstrip("/"),
            status_poll_attempts=int(
                _env("IG_STATUS_POLL_ATTEMPTS", "20") or "20"
            ),
            status_poll_interval_sec=float(
                _env("IG_STATUS_POLL_INTERVAL_SEC", "3") or "3"
            ),
        )

    @property
    def r2_configured(self) -> bool:
        return all(
            [
                self.r2_endpoint,
                self.r2_access_key_id,
                self.r2_secret_access_key,
                self.r2_bucket,
                self.r2_public_base_url,
            ]
        )

    @property
    def instagram_configured(self) -> bool:
        return bool(self.ig_user_id and self.meta_access_token)

    @property
    def graph_base_url(self) -> str:
        return f"https://graph.facebook.com/{self.meta_graph_version}"

    @property
    def package_only(self) -> bool:
        return self.publish_mode == "package"
