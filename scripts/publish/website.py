"""Convert approved briefing output into website Markdown posts."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .protocol import PublishResult

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POSTS_DIR = REPO_ROOT / "website" / "src" / "content" / "posts"
SEOUL = ZoneInfo("Asia/Seoul")
GENERIC_TAGS = {"경제", "브리핑", "증시", "뉴스"}
KINDS = {"briefing", "note"}
_SLUG_STRIP = re.compile(r"[^\w]+", re.UNICODE)
_PIPELINE_GRAPHIC = re.compile(
    r"!\[[^\]]*\]\((?:[^)\s]*/)?infographic\.png(?:\s+\"[^\"]*\")?\)[ \t]*",
    re.IGNORECASE,
)


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def display_title(briefing: dict[str, Any]) -> str:
    raw = (briefing.get("title") or "오늘의 브리핑").strip()
    return raw.split("|", 1)[0].strip() or "오늘의 브리핑"


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


def kind_of(briefing: dict[str, Any]) -> str:
    raw = str(briefing.get("kind") or "briefing").strip().lower()
    return raw if raw in KINDS else "briefing"


def public_http_url(value: str | None) -> str | None:
    """Keep only http(s) URLs that can be safely used as public hrefs."""
    raw = (value or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return raw


def sources_of(briefing: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for story in briefing.get("stories") or []:
        if not isinstance(story, dict):
            continue
        title = (story.get("source_name") or story.get("headline") or "출처").strip()
        url = public_http_url(str(story.get("source_url") or ""))
        item: dict[str, str] = {"title": title or "출처"}
        if url:
            item["url"] = url
        rows.append(item)
    for src in briefing.get("sources") or []:
        if isinstance(src, dict):
            title = (src.get("title") or src.get("name") or "출처").strip()
            url = public_http_url(str(src.get("url") or ""))
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
    text = _PIPELINE_GRAPHIC.sub("", "\n".join(lines))
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def render_post(
    briefing: dict[str, Any],
    markdown: str | None = None,
    now: datetime | None = None,
    graphic: str | None = None,
) -> tuple[str, str]:
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
        f"kind: {_yaml_quote(kind_of(briefing))}",
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
    if graphic:
        fm.append(f"graphic: {_yaml_quote(graphic)}")
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
    def __init__(
        self,
        posts_dir: Path | None = None,
        images_dir: Path | None = None,
        renderer: Any | None = None,
    ) -> None:
        self.posts_dir = Path(posts_dir) if posts_dir else DEFAULT_POSTS_DIR
        self.images_dir = Path(images_dir) if images_dir else images_dir_from_env(self.posts_dir)
        self.renderer = renderer

    def _want_graphic(self, content: dict[str, Any]) -> bool:
        if "render_graphic" in content:
            return bool(content["render_graphic"])
        if self.renderer is not None:
            return True
        return os.getenv("WEBSITE_INFOGRAPHIC", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }

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
            when = published_at_of(briefing, now)
            slug = article_slug(briefing, when)
            dest = unique_post_path(self.posts_dir, slug, display_title(briefing))
            graphic = None
            if not dry_run and self._want_graphic(content):
                from .site_graphics import write_site_infographic

                source = content.get("graphic_png")
                graphic = write_site_infographic(
                    briefing,
                    dest.stem,
                    self.images_dir,
                    now=when,
                    renderer=self.renderer,
                    source_png=Path(source) if source else None,
                )
            _, rendered = render_post(briefing, markdown, now, graphic=graphic)
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


def images_dir_from_env(posts_dir: Path | None = None) -> Path:
    raw = os.getenv("WEBSITE_IMAGES_DIR", "").strip()
    if raw:
        return Path(raw)
    posts = Path(posts_dir) if posts_dir else posts_dir_from_env()
    default_posts = (REPO_ROOT / "website" / "src" / "content" / "posts").resolve()
    try:
        posts.resolve().relative_to(default_posts)
    except ValueError:
        return posts.resolve().parent / "images"
    return REPO_ROOT / "website" / "public" / "images" / "posts"


def posts_dir_from_env() -> Path:
    raw = os.getenv("WEBSITE_POSTS_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_POSTS_DIR


def website_publish_enabled() -> bool:
    return os.getenv("WEBSITE_PUBLISH", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def write_website_result(run_dir: Path, payload: dict[str, Any]) -> Path:
    path = run_dir / "website_result.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def maybe_git_push(*paths: Path) -> PublishResult | None:
    """Commit and push generated files when WEBSITE_GIT_PUSH=1. Skip otherwise."""
    flag = os.getenv("WEBSITE_GIT_PUSH", "0").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return None
    files = [path for path in paths if path]
    if not files:
        return None
    cwd = REPO_ROOT
    rels = [os.path.relpath(path, cwd) for path in files]
    add = subprocess.run(
        ["git", "add", "--", *rels],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if add.returncode != 0:
        return PublishResult(
            channel="website",
            status="failed",
            error_type="GIT_COMMIT_FAILED",
            detail=add.stderr.strip() or add.stdout.strip() or "git add failed",
        )
    commit = subprocess.run(
        ["git", "commit", "-m", f"publish: {files[0].stem}", "--only", "--", *rels],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        return PublishResult(
            channel="website",
            status="failed",
            error_type="GIT_COMMIT_FAILED",
            detail=commit.stderr.strip() or commit.stdout.strip() or "git commit failed",
        )
    push = subprocess.run(
        ["git", "push"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if push.returncode != 0:
        return PublishResult(
            channel="website",
            status="failed",
            error_type="GIT_PUSH_FAILED",
            detail=push.stderr.strip() or push.stdout.strip() or "git push failed",
        )
    return None


def maybe_verify_deploy(published_url: str, title: str) -> PublishResult | None:
    base = os.getenv("SITE_BASE_URL", "").strip().rstrip("/")
    if not base or not published_url:
        return None
    url = f"{base}{published_url if published_url.startswith('/') else '/' + published_url}/"
    try:
        with urlopen(Request(url, method="GET"), timeout=15) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return PublishResult(
            channel="website",
            status="failed",
            error_type="DEPLOY_VERIFY_FAILED",
            published_url=url,
            detail=f"HTTP {exc.code}",
        )
    except URLError as exc:
        return PublishResult(
            channel="website",
            status="failed",
            error_type="DEPLOY_VERIFY_FAILED",
            published_url=url,
            detail=str(exc.reason),
        )
    except Exception as exc:  # noqa: BLE001
        return PublishResult(
            channel="website",
            status="failed",
            error_type="DEPLOY_VERIFY_FAILED",
            published_url=url,
            detail=str(exc),
        )
    if status != 200 or title not in body:
        return PublishResult(
            channel="website",
            status="failed",
            error_type="DEPLOY_VERIFY_FAILED",
            published_url=url,
            detail=f"status={status} title_found={title in body}",
        )
    return PublishResult(
        channel="website",
        status="success",
        published_url=url,
        detail="verified",
    )


def publish_approved_briefing(
    briefing: dict[str, Any],
    markdown: str,
    run_dir: Path,
    *,
    now: datetime | None = None,
    dry_run: bool | None = None,
    infographic_path: Path | None = None,
) -> dict[str, Any]:
    """Write site Markdown, optionally git-push and verify the live URL."""
    if not website_publish_enabled():
        payload = {"status": "skipped", "error_type": None, "url": None, "path": None}
        write_website_result(run_dir, payload)
        return payload
    if dry_run is None:
        dry_run = os.getenv("WEBSITE_DRY_RUN", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    publisher = WebsitePublisher(posts_dir_from_env())
    result = publisher.publish(
        {
            "briefing": briefing,
            "markdown": markdown,
            "now": now,
            "dry_run": dry_run,
            "graphic_png": infographic_path,
        }
    )
    failed = result.status == "failed"
    payload: dict[str, Any] = {
        "status": result.status,
        "error_type": result.error_type,
        "url": result.published_url,
        "path": None if failed else result.detail,
        "verified": False,
    }
    if failed:
        payload["detail"] = result.detail
        write_website_result(run_dir, payload)
        return payload
    if result.status == "success" and result.detail:
        post_path = Path(result.detail)
        graphic = images_dir_from_env(posts_dir_from_env()) / f"{post_path.stem}-infographic.png"
        extra = [graphic] if graphic.is_file() else []
        git_fail = maybe_git_push(post_path, *extra)
        if git_fail is not None:
            payload["status"] = git_fail.status
            payload["error_type"] = git_fail.error_type
            payload["detail"] = git_fail.detail
            write_website_result(run_dir, payload)
            return payload
        verify = maybe_verify_deploy(result.published_url or "", display_title(briefing))
        if verify is not None:
            payload["verified"] = verify.status == "success"
            payload["live_url"] = verify.published_url
            if verify.status == "failed":
                payload["status"] = verify.status
                payload["error_type"] = verify.error_type
                payload["detail"] = verify.detail
                write_website_result(run_dir, payload)
                return payload
    write_website_result(run_dir, payload)
    return payload
