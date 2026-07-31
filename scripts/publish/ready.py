"""Local publish_ready package: PNG cards + caption + manifest under final/."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .instagram import caption_from_briefing


PUBLISH_READY_DIRNAME = "publish_ready"
MANIFEST_NAME = "publish_manifest.json"


@dataclass(frozen=True)
class PublishReadyPackage:
    """Resolved paths for a publish_ready package on disk."""

    root: Path
    png_paths: list[Path]
    caption: str
    manifest: dict[str, Any]

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_NAME


def publish_ready_dir(run_or_final: Path) -> Path:
    """Return ``…/final/publish_ready`` for a run dir or final dir."""
    path = Path(run_or_final)
    if path.name == "final":
        return path / PUBLISH_READY_DIRNAME
    final = path / "final"
    if final.is_dir() or (path / "manifest.json").is_file():
        return final / PUBLISH_READY_DIRNAME
    if path.name == PUBLISH_READY_DIRNAME:
        return path
    return path / PUBLISH_READY_DIRNAME


def write_publish_ready_package(
    dest_root: Path,
    *,
    png_paths: list[Path],
    briefing: dict[str, Any] | None = None,
    caption: str | None = None,
    extra_manifest: dict[str, Any] | None = None,
) -> PublishReadyPackage:
    """Write PNG copies, caption files, and publish_manifest.json."""
    root = Path(dest_root)
    if root.name != PUBLISH_READY_DIRNAME:
        root = root / PUBLISH_READY_DIRNAME
    cards_out = root / "cards"
    if root.exists():
        shutil.rmtree(root)
    cards_out.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    for src in png_paths:
        src_path = Path(src)
        if not src_path.is_file():
            continue
        dest = cards_out / src_path.name
        shutil.copy2(src_path, dest)
        copied.append(dest)

    text = (caption if caption is not None else caption_from_briefing(briefing or {})).strip()
    (root / "caption.txt").write_text(text + ("\n" if text else ""), encoding="utf-8")
    (root / "instagram_post.txt").write_text(
        text + ("\n" if text else ""), encoding="utf-8"
    )

    manifest: dict[str, Any] = {
        "version": 1,
        "slide_count": len(copied),
        "slides": [p.name for p in copied],
        "caption_file": "instagram_post.txt",
        "cards_dir": "cards",
    }
    if briefing:
        title = str(briefing.get("title") or "").strip()
        if title:
            manifest["title"] = title
    if extra_manifest:
        manifest.update(extra_manifest)

    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return PublishReadyPackage(
        root=root, png_paths=copied, caption=text, manifest=manifest
    )


def load_publish_ready_package(run_or_package: Path) -> PublishReadyPackage:
    """Load an existing publish_ready directory (or run containing final/)."""
    root = publish_ready_dir(run_or_package)
    if not root.is_dir():
        raise FileNotFoundError(f"publish_ready not found: {root}")

    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {}

    cards_dir = root / str(manifest.get("cards_dir") or "cards")
    names = list(manifest.get("slides") or [])
    png_paths: list[Path] = []
    if names:
        for name in names:
            path = cards_dir / str(name)
            if path.is_file():
                png_paths.append(path)
    else:
        png_paths = sorted(cards_dir.glob("*.png")) if cards_dir.is_dir() else []

    caption = ""
    for candidate in (
        root / str(manifest.get("caption_file") or "instagram_post.txt"),
        root / "instagram_post.txt",
        root / "caption.txt",
    ):
        if candidate.is_file():
            caption = candidate.read_text(encoding="utf-8").strip()
            break

    return PublishReadyPackage(
        root=root, png_paths=png_paths, caption=caption, manifest=manifest
    )


def ensure_publish_ready_from_run(
    run_dir: Path,
    *,
    briefing: dict[str, Any] | None = None,
    card_pngs: list[Path] | None = None,
) -> PublishReadyPackage:
    """Load package if present; otherwise build from final/cards or given paths."""
    ready = publish_ready_dir(run_dir)
    if (ready / MANIFEST_NAME).is_file():
        return load_publish_ready_package(run_dir)

    pngs = list(card_pngs or [])
    if not pngs:
        final_cards = Path(run_dir) / "final" / "cards"
        if final_cards.is_dir():
            pngs = sorted(final_cards.glob("*.png"))
    if not pngs:
        raise FileNotFoundError(
            f"no card PNGs for publish_ready under {run_dir}"
        )

    brief = briefing
    if brief is None:
        for candidate in (
            Path(run_dir) / "final" / "briefing.json",
            Path(run_dir) / "briefing.json",
        ):
            if candidate.is_file():
                brief = json.loads(candidate.read_text(encoding="utf-8"))
                break

    return write_publish_ready_package(
        Path(run_dir) / "final",
        png_paths=pngs,
        briefing=brief if isinstance(brief, dict) else None,
    )
