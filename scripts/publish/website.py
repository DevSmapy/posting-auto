"""Convert approved briefing output into website Markdown posts."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .protocol import PublishResult

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POSTS_DIR = REPO_ROOT / "website" / "src" / "content" / "posts"
SEOUL = ZoneInfo("Asia/Seoul")
GENERIC_TAGS = {"경제", "브리핑", "증시"}
_SLUG_STRIP = re.compile(r"[^\w]+", re.UNICODE)


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def display_title(briefing: dict[str, Any]) -> str:
    raw = (briefing.get("title") or "오늘의 경제 브리핑").strip()
    return raw.split("|", 1)[0].strip() or "오늘의 경제 브리핑"


def description_of(briefing: dict[str, Any]) -> str:
    intro = (briefing.get("intro") or "").strip()
    if intro:
        return intro
    return display_title(briefing)


def category_of(briefing: dict[str, Any]) -> str:
    for tag in briefing.get("blog_tags") or []:
        text = str(tag).strip()
        if text and text not in GENERIC_TAGS:
            return text
    return "시장"


def sources_of(briefing: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for story in briefing.get("stories") or []:
        if not isinstance(story, dict):
            continue
        title = (story.get("source_name") or story.get("headline") or "출처").strip()
        url = (story.get("source_url") or "").strip()
        item: dict[str, str] = {"title": title or "출처"}
        if url:
            item["url"] = url
        rows.append(item)
    for src in briefing.get("sources") or []:
        if isinstance(src, dict):
            title = (src.get("title") or src.get("name") or "출처").strip()
            url = (src.get("url") or "").strip()
            item = {"title": title or "출처"}
            if url:
                item["url"] = url
            rows.append(item)
    return rows


def published_at_of(briefing: dict[str, Any], now: datetime | None = None) -> datetime:
    raw = briefing.get("published_at")
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=SEOUL)
    if isinstance(raw, str) and raw.strip():
        text = raw.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=SEOUL)
    title = (briefing.get("title") or "")
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", title)
    if match:
        return datetime.fromisoformat(match.group(1)).replace(
            hour=7, minute=0, tzinfo=SEOUL
        )
    stamp = now or datetime.now(SEOUL)
    return stamp.astimezone(SEOUL)


def slug_tail(title: str) -> str:
    text = title.replace("·", " ").replace("—", " ").replace("/", " ")
    slug = _SLUG_STRIP.sub("-", text).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:48] or "briefing"


def article_slug(briefing: dict[str, Any], when: datetime) -> str:
    return f"{when.astimezone(SEOUL).strftime('%Y-%m-%d')}-{slug_tail(display_title(briefing))}"


def body_markdown(briefing: dict[str, Any], markdown: str | None = None) -> str:
    if markdown is None:
        from mvp_pipeline import assemble_blog_markdown

        markdown = assemble_blog_markdown(briefing)
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        if lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip() + "\n"


def render_post(briefing: dict[str, Any], markdown: str | None = None, now: datetime | None = None) -> tuple[str, str]:
    when = published_at_of(briefing, now)
    slug = article_slug(briefing, when)
    title = display_title(briefing)
    tags = [str(t).strip() for t in (briefing.get("blog_tags") or []) if str(t).strip()]
    sources = sources_of(briefing)
    fm = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"description: {_yaml_quote(description_of(briefing))}",
        f"published_at: {_yaml_quote(when.isoformat())}",
        f"category: {_yaml_quote(category_of(briefing))}",
        "tags:",
    ]
    if tags:
        fm.extend(f"  - {_yaml_quote(tag)}" for tag in tags)
    else:
        fm.append("  - \"경제\"")
    fm.append("sources:")
    if sources:
        for src in sources:
            fm.append(f"  - title: {_yaml_quote(src['title'])}")
            if src.get("url"):
                fm.append(f"    url: {_yaml_quote(src['url'])}")
    else:
        fm[-1] = "sources: []"
    fm.append("status: \"published\"")
    fm.append("---")
    fm.append("")
    return slug, "\n".join(fm) + body_markdown(briefing, markdown)


def unique_post_path(posts_dir: Path, slug: str, title: str) -> Path:
    candidate = posts_dir / f"{slug}.md"
    n = 2
    needle = f"title: {_yaml_quote(title)}"
    while candidate.exists():
        existing = candidate.read_text(encoding="utf-8")
        if needle in existing:
            return candidate
        candidate = posts_dir / f"{slug}-{n}.md"
        n += 1
    return candidate


class WebsitePublisher:
    def __init__(self, posts_dir: Path | None = None) -> None:
        self.posts_dir = Path(posts_dir) if posts_dir else DEFAULT_POSTS_DIR

    def publish(self, content: dict[str, Any]) -> PublishResult:
        briefing = content.get("briefing")
        if not isinstance(briefing, dict):
            return PublishResult(
                channel="website",
                status="failed",
                error_type="CONTENT_WRITE_FAILED",
                detail="briefing dict required",
            )
        dry_run = bool(content.get("dry_run"))
        markdown = content.get("markdown")
        if markdown is not None:
            markdown = str(markdown)
        now = content.get("now")
        if not isinstance(now, datetime):
            now = None
        try:
            slug, rendered = render_post(briefing, markdown, now)
            dest = unique_post_path(self.posts_dir, slug, display_title(briefing))
            if not dry_run:
                self.posts_dir.mkdir(parents=True, exist_ok=True)
                dest.write_text(rendered, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return PublishResult(
                channel="website",
                status="failed",
                error_type="CONTENT_WRITE_FAILED",
                detail=str(exc),
            )
        return PublishResult(
            channel="website",
            status="dry_run" if dry_run else "success",
            published_url=f"/articles/{dest.stem}",
            detail=str(dest),
        )
