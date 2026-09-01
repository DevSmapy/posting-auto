"""Render card slides to HTML / PNG and export Instagram caption files."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import requests

from .config import CardFormatConfig
from .models import CardBundle, Slide, SlideType

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


class CardTemplateRenderer:
    """Fill HTML templates for cover / story / disclaimer / hook / cta slides."""

    def __init__(self, config: CardFormatConfig | None = None) -> None:
        self.config = config or CardFormatConfig.from_env()

    def render_slide(self, slide: Slide) -> str:
        brand = self.config.brand
        if slide.label:
            label = slide.label
        elif slide.role:
            label = slide.role
        elif slide.type == SlideType.STORY:
            label = "이슈"
        else:
            label = slide.type.value
        index = slide.index or "01"
        headline = self._nl(slide.headline)
        body = self._nl(slide.body)

        if slide.type == SlideType.HOOK:
            return self._fill(
                "hook.html",
                label=label,
                index=index,
                headline=headline,
                body=body,
                brand=brand,
            )
        if slide.type == SlideType.CTA:
            return self._fill(
                "cta.html",
                label=label,
                index=index,
                headline=headline,
                body=body,
                brand=brand,
            )
        if slide.type == SlideType.COVER:
            return self._fill(
                "cover.html",
                headline=headline,
                body=body,
                brand=brand,
            )
        if slide.type == SlideType.DISCLAIMER:
            return self._fill(
                "disclaimer.html",
                headline=headline,
                body=body,
                brand=brand,
            )
        return self._fill(
            "slide.html",
            label=label,
            index=index,
            headline=headline,
            body=body,
            brand=brand,
        )

    @staticmethod
    def _nl(text: str) -> str:
        """Convert newlines to a marker that _fill will turn into <br />."""
        return (text or "").replace("\r\n", "\n").replace("\n", "{{BR}}")

    def _fill(self, name: str, **kwargs: str) -> str:
        path = self.config.templates_dir / name
        text = path.read_text(encoding="utf-8")

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in kwargs:
                return match.group(0)
            value = kwargs[key]
            parts = value.split("{{BR}}")
            return "<br />".join(html.escape(p) for p in parts)

        return _PLACEHOLDER_RE.sub(repl, text)


class CardRenderer:
    """Export CardBundle to HTML, optional PNG, and Instagram caption files."""

    def __init__(
        self,
        config: CardFormatConfig | None = None,
        template_renderer: CardTemplateRenderer | None = None,
        screenshot_fn: Callable[[str, Path], None] | None = None,
    ) -> None:
        self.config = config or CardFormatConfig.from_env()
        self.templates = template_renderer or CardTemplateRenderer(self.config)
        self._screenshot_fn = screenshot_fn

    def export(
        self,
        bundle: CardBundle,
        out_dir: Path,
        *,
        render_png: bool = True,
    ) -> dict[str, list[Path] | Path | None]:
        """Write slides JSON, HTML, caption files, and optionally PNG."""
        out_dir.mkdir(parents=True, exist_ok=True)
        html_paths: list[Path] = []
        png_paths: list[Path] = []

        meta = {
            "template_id": bundle.template_id,
            "slides": bundle.slides_as_dicts(),
        }
        (out_dir / "slides.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        caption_path = out_dir / "caption.txt"
        hashtags_path = out_dir / "hashtags.txt"
        post_path = out_dir / "instagram_post.txt"
        caption_path.write_text(bundle.post.body + "\n", encoding="utf-8")
        hashtags_path.write_text(
            " ".join(f"#{t}" for t in bundle.post.hashtags) + "\n",
            encoding="utf-8",
        )
        post_path.write_text(bundle.post.full_text + "\n", encoding="utf-8")

        for i, slide in enumerate(bundle.slides, start=1):
            html_doc = self.templates.render_slide(slide)
            html_path = out_dir / f"slide-{i:02d}.html"
            html_path.write_text(html_doc, encoding="utf-8")
            html_paths.append(html_path)

            if render_png:
                png_path = out_dir / f"slide-{i:02d}.png"
                try:
                    self.screenshot_html(html_doc, png_path)
                    png_paths.append(png_path)
                    print(f"  card rendered: {png_path.name}")
                except Exception as exc:  # noqa: BLE001
                    print(f"  !! PNG skip {html_path.name}: {exc}")

        return {
            "html": html_paths,
            "png": png_paths,
            "caption": caption_path,
            "hashtags": hashtags_path,
            "instagram_post": post_path,
        }

    def render_png(self, bundle: CardBundle, out_dir: Path) -> list[Path]:
        result = self.export(bundle, out_dir, render_png=True)
        return list(result["png"] or [])  # type: ignore[arg-type]

    def screenshot_html(self, html_doc: str, out_path: Path) -> None:
        if self._screenshot_fn is not None:
            self._screenshot_fn(html_doc, out_path)
            return
        try:
            self._screenshot_browserless(html_doc, out_path)
            return
        except Exception as browserless_exc:  # noqa: BLE001
            last = browserless_exc
        try:
            self._screenshot_chrome(html_doc, out_path)
            return
        except Exception as chrome_exc:  # noqa: BLE001
            raise RuntimeError(
                f"screenshot failed (browserless: {last}; chrome: {chrome_exc})"
            ) from chrome_exc

    def _screenshot_browserless(self, html_doc: str, out_path: Path) -> None:
        # ghcr.io/browserless/chromium → /chromium/screenshot (not /chrome/…)
        path = self.config.browserless_screenshot_path or "/chromium/screenshot"
        endpoint = f"{self.config.browserless_url}{path}"
        params = {}
        if self.config.browserless_token:
            params["token"] = self.config.browserless_token
        resp = requests.post(
            endpoint,
            params=params or None,
            json={
                "html": html_doc,
                "options": {"type": "png", "fullPage": False},
                "viewport": {
                    "width": self.config.width,
                    "height": self.config.height,
                    "deviceScaleFactor": 1,
                },
                "gotoOptions": {"waitUntil": "networkidle0", "timeout": 60000},
            },
            timeout=90,
        )
        resp.raise_for_status()
        out_path.write_bytes(resp.content)

    def _screenshot_chrome(self, html_doc: str, out_path: Path) -> None:
        bin_name = self.config.screenshot_bin or self._find_chrome()
        if not bin_name:
            raise RuntimeError("no chrome/chromium binary found")
        with tempfile.TemporaryDirectory(prefix="cardnews-") as tmp:
            html_path = Path(tmp) / "slide.html"
            html_path.write_text(html_doc, encoding="utf-8")
            font = (
                Path(__file__).resolve().parents[2]
                / "website"
                / "public"
                / "fonts"
                / "PretendardVariable.woff2"
            )
            if font.is_file():
                shutil.copyfile(font, Path(tmp) / font.name)
            profile = Path(tmp) / "chrome-profile"
            profile.mkdir()
            uri = html_path.resolve().as_uri()
            cmd = [
                bin_name,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--hide-scrollbars",
                f"--user-data-dir={profile}",
                f"--window-size={self.config.width},{self.config.height}",
                f"--screenshot={out_path.resolve()}",
                uri,
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise RuntimeError("chrome screenshot produced empty file")

    @staticmethod
    def _find_chrome() -> str | None:
        for candidate in (
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"),
        ):
            if candidate.is_file():
                return str(candidate)
        for name in (
            "google-chrome-stable",
            "google-chrome",
            "chromium",
            "chromium-browser",
        ):
            found = shutil.which(name)
            if found:
                return found
        for candidate in (
            Path("/usr/local/bin/google-chrome"),
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ):
            if candidate.is_file():
                return str(candidate)
        return None
