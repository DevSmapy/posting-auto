"""Editorial theme list/clone helpers (no Streamlit dependency)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates" / "cards"
EDITORIAL_DIR = TEMPLATES / "editorial"

_THEME_RE = re.compile(r"^editorial(_[a-z0-9_]+)?$")


def list_editorial_themes(templates_dir: Path | None = None) -> list[str]:
    base = Path(templates_dir) if templates_dir is not None else TEMPLATES
    names: list[str] = []
    if not base.is_dir():
        return names
    for path in sorted(base.iterdir()):
        if path.is_dir() and _THEME_RE.match(path.name):
            names.append(path.name)
    if "editorial" not in names and (base / "editorial").is_dir():
        names.insert(0, "editorial")
    return names


def theme_dir(name: str, templates_dir: Path | None = None) -> Path:
    base = (Path(templates_dir) if templates_dir is not None else TEMPLATES).resolve()
    raw = (name or "").strip()
    candidate = Path(raw)
    if (
        not raw
        or candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.name != raw
    ):
        raise ValueError(f"invalid theme name: {name!r}")
    resolved = (base / raw).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"theme path escapes templates dir: {name!r}") from exc
    return resolved


def clone_theme(
    source: str,
    new_name: str,
    *,
    templates_dir: Path | None = None,
) -> Path:
    slug = re.sub(r"[^a-z0-9_]+", "_", new_name.strip().lower()).strip("_")
    if not slug:
        raise ValueError("theme name required")
    if not slug.startswith("editorial_"):
        slug = f"editorial_{slug}"
    dest = theme_dir(slug, templates_dir)
    if dest.exists():
        raise FileExistsError(f"already exists: {dest}")
    src = theme_dir(source, templates_dir)
    if not src.is_dir():
        raise FileNotFoundError(f"source theme missing: {src}")
    shutil.copytree(src, dest)
    return dest
