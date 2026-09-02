"""Run-directory attempt/manifest helpers for two-stage draft gates."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


CONTENT_PREFIX = "content-"
RENDER_PREFIX = "render-"


@dataclass
class RunManifest:
    run_id: str
    content_remaining: int = 3
    render_remaining: int = 3
    content_max: int = 3
    render_max: int = 3
    current_content: str | None = None
    selected_content: str | None = None
    current_render: str | None = None
    final: str | None = None
    status: str = "active"
    parked_stage: str | None = None
    content_attempts: list[str] = field(default_factory=list)
    render_attempts: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunManifest":
        return cls(
            run_id=str(data.get("run_id") or ""),
            content_remaining=int(data.get("content_remaining", 3)),
            render_remaining=int(data.get("render_remaining", 3)),
            content_max=int(data.get("content_max", 3)),
            render_max=int(data.get("render_max", 3)),
            current_content=data.get("current_content"),
            selected_content=data.get("selected_content"),
            current_render=data.get("current_render"),
            final=data.get("final"),
            status=str(data.get("status") or "active"),
            parked_stage=data.get("parked_stage"),
            content_attempts=list(data.get("content_attempts") or []),
            render_attempts=list(data.get("render_attempts") or []),
            actions=list(data.get("actions") or []),
        )


class DraftRunStore:
    """Owns output/<run_id>/attempts, renders, final, and manifest.json."""

    def __init__(self, run_dir: Path, *, content_max: int = 3, render_max: int = 3) -> None:
        self.run_dir = Path(run_dir)
        self.attempts_dir = self.run_dir / "attempts"
        self.renders_dir = self.run_dir / "renders"
        self.final_dir = self.run_dir / "final"
        self.manifest_path = self.run_dir / "manifest.json"
        self.manifest = RunManifest(
            run_id=self.run_dir.name,
            content_remaining=content_max,
            render_remaining=render_max,
            content_max=content_max,
            render_max=render_max,
        )

    def init_layout(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.attempts_dir.mkdir(exist_ok=True)
        self.renders_dir.mkdir(exist_ok=True)
        self.final_dir.mkdir(exist_ok=True)
        self.save()

    def save(self) -> None:
        self.manifest_path.write_text(
            json.dumps(self.manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self) -> None:
        if not self.manifest_path.is_file():
            return
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.manifest = RunManifest.from_dict(data)

    def _next_name(self, existing: list[str], prefix: str) -> str:
        n = len(existing) + 1
        return f"{prefix}{n:02d}"

    def new_content_attempt(self) -> Path:
        name = self._next_name(self.manifest.content_attempts, CONTENT_PREFIX)
        path = self.attempts_dir / name
        path.mkdir(parents=True, exist_ok=True)
        self.manifest.content_attempts.append(name)
        self.manifest.current_content = name
        self.save()
        return path

    def new_render_attempt(self) -> Path:
        name = self._next_name(self.manifest.render_attempts, RENDER_PREFIX)
        path = self.renders_dir / name
        path.mkdir(parents=True, exist_ok=True)
        (path / "cards").mkdir(exist_ok=True)
        self.manifest.render_attempts.append(name)
        self.manifest.current_render = name
        self.save()
        return path

    def content_dir(self, name: str | None = None) -> Path:
        key = name or self.manifest.current_content
        if not key:
            raise RuntimeError("no content attempt")
        return self.attempts_dir / key

    def render_dir(self, name: str | None = None) -> Path:
        key = name or self.manifest.current_render
        if not key:
            raise RuntimeError("no render attempt")
        return self.renders_dir / key

    def selected_content_dir(self) -> Path:
        if not self.manifest.selected_content:
            raise RuntimeError("no selected content")
        return self.attempts_dir / self.manifest.selected_content

    def set_selected_content(self, name: str | None = None) -> None:
        key = name or self.manifest.current_content
        if not key:
            raise RuntimeError("no content attempt to select")
        self.manifest.selected_content = key
        selected_link = self.run_dir / "selected"
        if selected_link.is_symlink() or selected_link.exists():
            selected_link.unlink()
        try:
            selected_link.symlink_to(Path("attempts") / key)
        except OSError:
            # Fallback when symlink is unavailable: copy pointer via manifest only.
            pass
        self.save()

    def record_action(
        self,
        stage: str,
        action: str,
        *,
        skip_reason: str = "unknown",
    ) -> None:
        self.manifest.actions.append(
            {
                "stage": stage,
                "action": action,
                "skip_reason": skip_reason,
                "content": self.manifest.current_content,
                "render": self.manifest.current_render,
            }
        )
        self.save()

    def consume_content_retry(self) -> int:
        if self.manifest.content_remaining <= 0:
            return 0
        self.manifest.content_remaining -= 1
        self.save()
        return self.manifest.content_remaining

    def restore_content_retry(self) -> int:
        """Undo a content retry consume (e.g. regenerate failed before a new attempt)."""
        if self.manifest.content_remaining >= self.manifest.content_max:
            return self.manifest.content_remaining
        self.manifest.content_remaining += 1
        self.save()
        return self.manifest.content_remaining

    def consume_render_retry(self) -> int:
        if self.manifest.render_remaining <= 0:
            return 0
        self.manifest.render_remaining -= 1
        self.save()
        return self.manifest.render_remaining

    def restore_render_retry(self) -> int:
        """Undo a render retry consume (e.g. re-render failed before a new attempt)."""
        if self.manifest.render_remaining >= self.manifest.render_max:
            return self.manifest.render_remaining
        self.manifest.render_remaining += 1
        self.save()
        return self.manifest.render_remaining

    def prior_pick_urls(self) -> set[str]:
        """URLs already used in completed content attempts this run."""
        urls: set[str] = set()
        for name in self.manifest.content_attempts:
            ranked = self.attempts_dir / name / "ranked.json"
            if not ranked.is_file():
                continue
            try:
                rows = json.loads(ranked.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict):
                    link = str(row.get("link") or "").strip()
                    if link:
                        urls.add(link)
        return urls

    def exclude_prior_picks(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        used = self.prior_pick_urls()
        if not used:
            return list(candidates)
        return [c for c in candidates if str(c.get("link") or "") not in used]

    def mark_final(self) -> Path:
        self.manifest.final = "final"
        self.final_dir.mkdir(exist_ok=True)
        self.save()
        return self.final_dir

    def mark_parked(self, stage: str) -> None:
        self.manifest.status = "parked"
        self.manifest.parked_stage = stage
        self.record_action("park", stage)
        self.save()

    def clear_parked(self) -> None:
        self.manifest.status = "active"
        self.manifest.parked_stage = None
        self.save()

    def mark_completed(self) -> None:
        self.manifest.status = "completed"
        self.manifest.parked_stage = None
        self.save()

    def copy_into_final(
        self,
        *,
        briefing: dict[str, Any] | None = None,
        md_path: Path | None = None,
        html_path: Path | None = None,
        card_pngs: list[Path] | None = None,
        infographic_png: Path | None = None,
    ) -> None:
        from publish.ready import write_publish_ready_package

        final = self.mark_final()
        if briefing is not None:
            (final / "briefing.json").write_text(
                json.dumps(briefing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if md_path and md_path.is_file():
            shutil.copy2(md_path, final / "briefing.md")
        if html_path and html_path.is_file():
            shutil.copy2(html_path, final / "briefing.html")
        # Kept beside briefing.md, and out of the Instagram PNG list on purpose.
        if infographic_png and Path(infographic_png).is_file():
            shutil.copy2(infographic_png, final / "infographic.png")
        cards_out = final / "cards"
        cards_out.mkdir(exist_ok=True)
        copied_pngs: list[Path] = []
        for path in card_pngs or []:
            if Path(path).is_file():
                dest = cards_out / Path(path).name
                shutil.copy2(path, dest)
                copied_pngs.append(dest)
        if copied_pngs:
            write_publish_ready_package(
                final,
                png_paths=copied_pngs,
                briefing=briefing,
                extra_manifest={"run_id": self.manifest.run_id},
            )

    def cleanup_keep_final(self) -> list[str]:
        """Delete unselected content/render attempts. Keep final/ + manifest."""
        deleted: list[str] = []
        selected = self.manifest.selected_content
        current_render = self.manifest.current_render
        for name in list(self.manifest.content_attempts):
            if name == selected:
                continue
            path = self.attempts_dir / name
            if path.is_dir():
                shutil.rmtree(path)
                deleted.append(f"attempts/{name}")
        for name in list(self.manifest.render_attempts):
            if name == current_render:
                continue
            path = self.renders_dir / name
            if path.is_dir():
                shutil.rmtree(path)
                deleted.append(f"renders/{name}")
        self.manifest.content_attempts = [n for n in self.manifest.content_attempts if n == selected]
        self.manifest.render_attempts = [
            n for n in self.manifest.render_attempts if n == current_render
        ]
        self.record_action("cleanup", "keep_final")
        self.save()
        return deleted

    def cleanup_keep_all(self) -> None:
        self.record_action("cleanup", "keep_all")
        self.save()

    def unselected_labels(self) -> list[str]:
        labels: list[str] = []
        selected = self.manifest.selected_content
        current_render = self.manifest.current_render
        for name in self.manifest.content_attempts:
            if name != selected:
                labels.append(f"attempts/{name}")
        for name in self.manifest.render_attempts:
            if name != current_render:
                labels.append(f"renders/{name}")
        return labels
