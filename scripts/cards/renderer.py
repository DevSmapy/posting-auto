"""Render card slides to HTML / PNG and export Instagram caption files."""

from __future__ import annotations

import html
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import requests

from .config import CardFormatConfig
from .models import CardBundle, Slide, SlideType


class CardTemplateRenderer:
    """Fill HTML templates for cover / story / disclaimer slides."""

    def __init__(self, config: CardFormatConfig | None = None) -> None:
        self.config = config or CardFormatConfig.from_env()

    def render_slide(self, slide: Slide) -> str:
        brand = self.config.brand
        if slide.type == SlideType.COVER:
            # body may contain date\ntheme — show as multiline in template
            return self._fill(
                "cover.html",
                headline=slide.headline,
                body=slide.body.replace("\n", "<br />"),
                brand=brand,
            )
        if slide.type == SlideType.DISCLAIMER:
            return self._fill(
                "disclaimer.html",
                headline=slide.headline,
                body=slide.body,
                brand=brand,
            )
        index = slide.index or "01"
        return self._fill(
            "slide.html",
            index=index,
            headline=slide.headline,
            body=slide.body,
            brand=brand,
        )

    def _fill(self, name: str, **kwargs: str) -> str:
        path = self.config.templates_dir / name
        text = path.read_text(encoding="utf-8")
        for key, value in kwargs.items():
            # Allow intentional <br /> from cover body; escape other content first
            if key == "body" and "<br" in value:
                parts = value.split("<br />")
                safe = "<br />".join(html.escape(p) for p in parts)
            else:
                safe = html.escape(value)
            text = text.replace("{{" + key + "}}", safe)
        return text


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

        (out_dir / "slides.json").write_text(
            json.dumps(bundle.slides_as_dicts(), ensure_ascii=False, indent=2),
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
        endpoint = f"{self.config.browserless_url}/chrome/screenshot"
        resp = requests.post(
            endpoint,
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
            uri = html_path.resolve().as_uri()
            cmd = [
                bin_name,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                f"--window-size={self.config.width},{self.config.height}",
                f"--screenshot={out_path.resolve()}",
                uri,
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise RuntimeError("chrome screenshot produced empty file")

    @staticmethod
    def _find_chrome() -> str | None:
        for name in (
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
        ):
            found = shutil.which(name)
            if found:
                return found
        # Common absolute path in this agent environment
        agent_chrome = Path("/usr/local/bin/google-chrome")
        if agent_chrome.is_file():
            return str(agent_chrome)
        return None
