"""Upload card PNGs to Cloudflare R2 (S3-compatible) for public HTTPS URLs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .config import PublishConfig


class S3Client(Protocol):
    def upload_file(
        self,
        Filename: str,
        Bucket: str,
        Key: str,
        ExtraArgs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any: ...


class R2Uploader:
    """Upload local PNG paths and return public HTTPS URLs for Instagram Media API."""

    def __init__(
        self,
        config: PublishConfig,
        client: S3Client | None = None,
    ) -> None:
        self.config = config
        self._client = client

    def _build_client(self) -> S3Client:
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 required for R2 upload") from exc
        if not self.config.r2_configured:
            raise RuntimeError("R2_* env vars incomplete")
        return boto3.client(
            "s3",
            endpoint_url=self.config.r2_endpoint,
            aws_access_key_id=self.config.r2_access_key_id,
            aws_secret_access_key=self.config.r2_secret_access_key,
            region_name="auto",
        )

    def upload(self, paths: list[Path], prefix: str) -> list[str]:
        """Upload files under ``prefix/`` and return public URLs in path order."""
        if not paths:
            return []
        client = self._build_client()
        base = self.config.r2_public_base_url.rstrip("/")
        urls: list[str] = []
        for path in paths:
            key = f"{prefix.rstrip('/')}/{path.name}"
            client.upload_file(
                str(path),
                self.config.r2_bucket,
                key,
                ExtraArgs={"ContentType": "image/png"},
            )
            urls.append(f"{base}/{key}")
        return urls
