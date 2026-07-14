#!/usr/bin/env python3
"""MVP pipeline: Google News → filter → Ollama rank/brief → Approve → publish.

Modes (MVP_MODE):
  dry_run  - fetch + LLM, write output/*.json (default)
  draft    - Telegram preview + Approve/Skip; Approve → publish
  publish  - publish without Approve wait (requires tokens)
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import feedparser
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

from seen_urls import SeenUrlsStore  # noqa: E402

TZ = ZoneInfo(os.getenv("NEWS_TIMEZONE", "Asia/Seoul"))
PROMPTS = ROOT / "prompts"
TEMPLATES = ROOT / "templates" / "cards"
OUTPUT = Path(os.getenv("OUTPUT_DIR", str(ROOT / "output")))


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def ollama_base() -> str:
    """Host scripts must not use the Docker DNS name `ollama`."""
    host_url = env("OLLAMA_HOST_URL")
    if host_url:
        return host_url.rstrip("/")
    base = env("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    base = base.replace("http://ollama:", "http://127.0.0.1:")
    base = base.replace("https://ollama:", "https://127.0.0.1:")
    base = base.replace("host.docker.internal", "127.0.0.1")
    return base


def read_prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def render_template(name: str, **kwargs: str) -> str:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    for key, value in kwargs.items():
        text = text.replace("{{" + key + "}}", html.escape(value))
    return text


def strip_html(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def cluster_size(description: str) -> int:
    return len(re.findall(r"<li\b", description or "", flags=re.I))


def stable_id(link: str, title: str) -> str:
    raw = (link or title).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def parse_entry(entry: Any, topic: str, feed_rank: int) -> dict[str, Any] | None:
    title = strip_html(getattr(entry, "title", "") or "")
    link = getattr(entry, "link", "") or ""
    if not title or title == "Google 뉴스":
        return None
    source = ""
    if hasattr(entry, "source") and entry.source:
        source = strip_html(getattr(entry.source, "title", "") or str(entry.source))
    if " - " in title:
        maybe_title, maybe_source = title.rsplit(" - ", 1)
        if maybe_title.strip():
            title = maybe_title.strip()
            if not source:
                source = maybe_source.strip()
            elif maybe_source.strip() and maybe_source.strip() != source:
                pass

    published = None
    if getattr(entry, "published_parsed", None):
        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(TZ)
    desc = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    return {
        "id": stable_id(link, title),
        "title": title,
        "snippet": strip_html(desc)[:800],
        "link": link,
        "source": source,
        "published_at": published.isoformat() if published else None,
        "published_dt": published,
        "topic": topic,
        "feed_rank": feed_rank,
        "cluster_size": cluster_size(desc),
    }


def fetch_topic(url: str, topic: str) -> list[dict[str, Any]]:
    parsed = feedparser.parse(url)
    items: list[dict[str, Any]] = []
    for i, entry in enumerate(parsed.entries, start=1):
        row = parse_entry(entry, topic, i)
        if row:
            items.append(row)
    return items


def is_today(dt: datetime | None, now: datetime) -> bool:
    if dt is None:
        return True
    local = dt.astimezone(TZ)
    return local.date() == now.date()


def fetch_candidates(now: datetime) -> list[dict[str, Any]]:
    business = env(
        "GNEWS_BUSINESS_RSS",
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko",
    )
    nation = env(
        "GNEWS_NATION_RSS",
        "https://news.google.com/rss/headlines/section/topic/NATION?hl=ko&gl=KR&ceid=KR:ko",
    )
    merged = fetch_topic(business, "BUSINESS") + fetch_topic(nation, "NATION")
    today = [a for a in merged if is_today(a.get("published_dt"), now)]
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for a in today:
        key = a["id"]
        title_key = re.sub(r"\s+", "", a["title"].lower())
        if key in seen or title_key in seen:
            continue
        seen.add(key)
        seen.add(title_key)
        unique.append(a)
    unique.sort(key=lambda x: (0 if x["topic"] == "BUSINESS" else 1, x["feed_rank"], -x["cluster_size"]))
    limit = int(env("NEWS_MAX_CANDIDATES", "20"))
    return unique[:limit]


def extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def as_bool_drop(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def ollama_options() -> dict[str, Any]:
    opts: dict[str, Any] = {
        "temperature": float(env("OLLAMA_TEMPERATURE", "0.3")),
        "num_thread": int(env("OLLAMA_NUM_THREAD", "4")),
    }
    num_ctx = env("OLLAMA_NUM_CTX")
    if num_ctx:
        opts["num_ctx"] = int(num_ctx)
    return opts


def ollama_chat(system: str, user: str) -> tuple[Any, str]:
    model = env("OLLAMA_MODEL", "qwen2.5:14b")
    timeout = int(env("OLLAMA_TIMEOUT_MS", "180000")) / 1000
    url = f"{ollama_base()}/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": ollama_options(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    last_err: Exception | None = None
    for _attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            return extract_json(content), content
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.5)
    raise RuntimeError(f"Ollama failed after retry: {last_err}")


def heuristic_rank(articles: list[dict[str, Any]], pick: int) -> list[dict[str, Any]]:
    watchlist = [w.strip() for w in env("WATCHLIST", "").split(",") if w.strip()]
    scored: list[dict[str, Any]] = []
    for a in articles:
        score = 4
        if a.get("topic") == "BUSINESS":
            score += 2
        score += max(0, 8 - int(a.get("feed_rank") or 99))
        score += min(int(a.get("cluster_size") or 0), 5)
        blob = f"{a.get('title', '')} {a.get('snippet', '')}"
        hits = [w for w in watchlist if w and w in blob]
        score += 2 * len(hits)
        item = dict(a)
        item["score"] = score
        item["audience"] = "market" if a.get("topic") == "BUSINESS" else "general"
        item["reason"] = "heuristic" + (f" / watchlist:{','.join(hits)}" if hits else "")
        item["drop"] = False
        scored.append(item)
    scored.sort(key=lambda x: (-x["score"], x["feed_rank"]))
    return scored[:pick]


def normalize_ranked_payload(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if isinstance(parsed, dict):
        for key in ("ranked", "items", "articles", "results"):
            val = parsed.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
    return []


def rank_articles(
    articles: list[dict[str, Any]],
    now: datetime,
    run_dir: Path | None = None,
) -> list[dict[str, Any]]:
    pick = int(env("NEWS_PICK_COUNT", "5"))
    llm_limit = int(env("NEWS_LLM_CANDIDATES", "10"))
    pre = heuristic_rank(articles, max(llm_limit, pick))
    watchlist = env("WATCHLIST", "")
    payload = [
        {
            "id": a["id"],
            "title": a["title"],
            "snippet": a["snippet"][:400],
            "source": a["source"],
            "topic": a["topic"],
            "feed_rank": a["feed_rank"],
            "cluster_size": a["cluster_size"],
        }
        for a in pre
    ]
    user = (
        read_prompt("importance_user.md")
        .replace("{{date}}", now.strftime("%Y-%m-%d"))
        .replace("{{watchlist}}", watchlist)
        .replace("{{articles_json}}", json.dumps(payload, ensure_ascii=False, indent=2))
    )

    use_llm = env("RANK_MODE", "llm").lower() != "heuristic"
    scored: list[dict[str, Any]] = []
    raw = ""
    parsed: Any = None
    if use_llm:
        try:
            parsed, raw = ollama_chat(read_prompt("importance_system.md"), user)
            if run_dir is not None:
                (run_dir / "importance_raw.json").write_text(
                    json.dumps({"raw": raw, "parsed": parsed}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            by_id = {a["id"]: a for a in pre}
            for row in normalize_ranked_payload(parsed):
                rid = str(row.get("id") or "").strip()
                base = by_id.get(rid)
                if not base:
                    continue
                if as_bool_drop(row.get("drop")):
                    continue
                item = dict(base)
                try:
                    item["score"] = int(row.get("score") or 0)
                except (TypeError, ValueError):
                    item["score"] = 0
                item["audience"] = row.get("audience") or "general"
                item["reason"] = row.get("reason") or ""
                scored.append(item)
            scored.sort(key=lambda x: (-x["score"], x["feed_rank"]))
            scored = scored[:pick]
        except Exception as exc:  # noqa: BLE001
            print(f"   !! LLM rank failed: {exc} — heuristic fallback")
            scored = []

    if not scored:
        print("   !! empty LLM rank — using heuristic fallback")
        scored = heuristic_rank(articles, pick)
        if run_dir is not None and raw:
            (run_dir / "importance_fallback.txt").write_text(
                f"LLM returned no usable ranks.\nraw={raw[:2000]}\n",
                encoding="utf-8",
            )
    return scored


def build_briefing_heuristic(articles: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """LLM 없이 발행 경로 스모크·폴백용 브리핑."""
    date = now.strftime("%Y-%m-%d")
    stories = []
    slides: list[dict[str, str]] = [
        {
            "type": "cover",
            "headline": f"{date} 경제 브리핑",
            "body": "오늘의 주요 경제 뉴스",
        }
    ]
    for i, a in enumerate(articles, start=1):
        summary = (a.get("snippet") or a.get("title") or "")[:280]
        stories.append(
            {
                "headline": a.get("title") or f"이슈 {i}",
                "summary": summary,
                "why_it_matters": a.get("reason") or "시장·정책 흐름 점검",
                "source_name": a.get("source") or "",
                "source_url": a.get("link") or "",
            }
        )
        slides.append(
            {
                "type": "story",
                "headline": (a.get("title") or "")[:80],
                "body": summary[:160],
            }
        )
    slides.append(
        {
            "type": "disclaimer",
            "headline": "면책",
            "body": "정보 안내용이며 투자 권유가 아닙니다.",
        }
    )
    tops = [a.get("title") or "" for a in articles[:3]]
    return {
        "title": f"오늘의 경제 브리핑 ({date})",
        "intro": "휴리스틱 브리핑(테스트/폴백).",
        "market_one_liner": " · ".join(t for t in tops if t) or "오늘 주요 뉴스 정리",
        "stories": stories,
        "today_points": [f"{a.get('title')}" for a in articles[:5]],
        "blog_tags": ["경제", "브리핑", "뉴스"],
        "slides": slides,
        "caption": f"{date} 경제 브리핑",
        "hashtags": ["경제", "뉴스", "브리핑"],
    }


def build_briefing(articles: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    if env("BRIEFING_MODE", "llm").lower() == "heuristic":
        print("   briefing mode=heuristic")
        return build_briefing_heuristic(articles, now)

    payload = [
        {
            "title": a["title"],
            "snippet": a["snippet"],
            "source": a["source"],
            "link": a["link"],
            "topic": a["topic"],
            "score": a.get("score"),
            "reason": a.get("reason"),
        }
        for a in articles
    ]
    user = (
        read_prompt("briefing_user.md")
        .replace("{{date}}", now.strftime("%Y-%m-%d"))
        .replace("{{articles_json}}", json.dumps(payload, ensure_ascii=False, indent=2))
    )
    try:
        parsed, raw = ollama_chat(read_prompt("briefing_system.md"), user)
        if not isinstance(parsed, dict):
            raise RuntimeError(f"briefing JSON must be object, got {type(parsed)}: {raw[:500]}")
        return parsed
    except Exception as exc:  # noqa: BLE001
        if env("ALLOW_BRIEFING_FALLBACK", "1").lower() in {"1", "true", "yes"}:
            print(f"   !! LLM briefing failed: {exc} — heuristic fallback")
            return build_briefing_heuristic(articles, now)
        raise


def assemble_blog_html(briefing: dict[str, Any]) -> str:
    parts = [
        f"<p>{html.escape(briefing.get('intro', ''))}</p>",
        f"<p><strong>오늘 한줄</strong> {html.escape(briefing.get('market_one_liner', ''))}</p>",
    ]
    for story in briefing.get("stories") or []:
        parts.append(f"<h2>{html.escape(story.get('headline', ''))}</h2>")
        parts.append(f"<p>{html.escape(story.get('summary', ''))}</p>")
        parts.append(f"<p><em>{html.escape(story.get('why_it_matters', ''))}</em></p>")
        name = html.escape(story.get("source_name") or "")
        url = html.escape(story.get("source_url") or "#", quote=True)
        parts.append(f'<p>출처: <a href="{url}">{name}</a></p>')
    parts.append("<h2>오늘 포인트</h2><ul>")
    for point in briefing.get("today_points") or []:
        parts.append(f"<li>{html.escape(str(point))}</li>")
    parts.append("</ul><hr>")
    parts.append(
        "<p>본 콘텐츠는 정보 안내용이며 특정 종목의 매수·매도·투자를 권유하지 않습니다. "
        "투자 판단과 책임은 독자 본인에게 있습니다.</p>"
    )
    return "\n".join(parts)


def telegram_api(method: str, payload: dict[str, Any] | None = None, *, token: str | None = None) -> dict[str, Any]:
    tok = token or env("TELEGRAM_BOT_TOKEN")
    if not tok:
        raise RuntimeError("TELEGRAM_BOT_TOKEN required")
    url = f"https://api.telegram.org/bot{tok}/{method}"
    resp = requests.post(url, json=payload or {}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API {method} failed: {data}")
    return data


def telegram_send(text: str) -> None:
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram skipped: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return
    chunk = text[:4000]
    telegram_api("sendMessage", {"chat_id": chat_id, "text": chunk}, token=token)


def _approve_mode() -> str:
    """telegram | cli | auto

    auto: approve without waiting (tests / CI)
    cli: stdin approve/skip when Telegram tokens missing or forced
    telegram: inline keyboard + getUpdates poll
    """
    explicit = env("TELEGRAM_APPROVE_MODE").lower()
    if explicit in {"telegram", "cli", "auto"}:
        return explicit
    if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        return "telegram"
    return "cli"


def wait_for_approve(preview: str) -> bool:
    """Return True if approved, False if skipped/timeout."""
    mode = _approve_mode()
    timeout = int(env("TELEGRAM_APPROVE_TIMEOUT_SEC", "900"))
    print(f"==> Approve gate mode={mode} timeout={timeout}s")

    if mode == "auto":
        print("   auto-approve")
        return True

    if mode == "cli":
        print(preview)
        print("\n--- Approve? type approve / skip ---")
        try:
            line = input("> ").strip().lower()
        except EOFError:
            line = "skip"
        approved = line in {"a", "approve", "y", "yes", "ok"}
        print("   approved" if approved else "   skipped")
        return approved

    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Telegram Approve requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")

    request_id = uuid.uuid4().hex[:12]
    approve_data = f"approve:{request_id}"
    skip_data = f"skip:{request_id}"
    chunk = preview[:3500]
    markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": approve_data},
                {"text": "⏭ Skip", "callback_data": skip_data},
            ]
        ]
    }
    # Drop pending updates so we only see new callbacks
    boot = telegram_api("getUpdates", {"offset": -1, "timeout": 0}, token=token)
    offset = 0
    for upd in boot.get("result") or []:
        offset = max(offset, int(upd.get("update_id", 0)) + 1)

    telegram_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": chunk + f"\n\n[승인 요청 {request_id}]",
            "reply_markup": markup,
        },
        token=token,
    )
    print("   Telegram preview + Approve/Skip sent — waiting…")

    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = max(1, int(deadline - time.time()))
        poll_timeout = min(25, remaining)
        data = telegram_api(
            "getUpdates",
            {"offset": offset, "timeout": poll_timeout, "allowed_updates": ["callback_query", "message"]},
            token=token,
        )
        for upd in data.get("result") or []:
            offset = max(offset, int(upd.get("update_id", 0)) + 1)
            cb = upd.get("callback_query")
            if cb:
                raw = str(cb.get("data") or "")
                cq_id = cb.get("id")
                if raw == approve_data:
                    if cq_id:
                        telegram_api(
                            "answerCallbackQuery",
                            {"callback_query_id": cq_id, "text": "Approve — 발행 진행"},
                            token=token,
                        )
                    telegram_send("승인됨. 발행을 시작합니다.")
                    return True
                if raw == skip_data:
                    if cq_id:
                        telegram_api(
                            "answerCallbackQuery",
                            {"callback_query_id": cq_id, "text": "Skip"},
                            token=token,
                        )
                    telegram_send("스킵됨. 발행하지 않습니다.")
                    return False
            msg = upd.get("message") or {}
            text = (msg.get("text") or "").strip().lower()
            if str(msg.get("chat", {}).get("id")) == str(chat_id):
                if text in {"/approve", "approve"}:
                    telegram_send("승인됨. 발행을 시작합니다.")
                    return True
                if text in {"/skip", "skip"}:
                    telegram_send("스킵됨. 발행하지 않습니다.")
                    return False

    telegram_send(f"[타임아웃] {timeout}s 내 응답 없음 — 발행 취소")
    print("   Approve timeout — skip publish")
    return False


def tistory_write(title: str, content: str, tags: list[str]) -> dict[str, Any]:
    if env("TISTORY_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        print("   TISTORY_DRY_RUN=1 — skipping API, writing local stub")
        return {
            "tistory": {
                "status": "200",
                "postId": f"dry-{int(time.time())}",
                "url": "https://example.tistory.com/dry-run",
            },
            "dry_run": True,
            "title": title,
            "tags": tags,
            "content_len": len(content),
        }
    token = env("TISTORY_ACCESS_TOKEN")
    blog = env("TISTORY_BLOG_NAME")
    if not token or not blog:
        raise RuntimeError("TISTORY_ACCESS_TOKEN / TISTORY_BLOG_NAME required for publish")
    visibility = env("TISTORY_VISIBILITY", "3")
    resp = requests.post(
        "https://www.tistory.com/apis/post/write",
        data={
            "access_token": token,
            "output": "json",
            "blogName": blog,
            "title": title,
            "content": content,
            "visibility": visibility,
            "tag": ",".join(tags),
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def extract_tistory_post_id(res: dict[str, Any]) -> str | None:
    try:
        return str(res["tistory"]["postId"])
    except (KeyError, TypeError):
        return None


def screenshot_html(html_doc: str, out_path: Path) -> None:
    base = env("BROWSERLESS_URL", "http://localhost:3000").rstrip("/")
    endpoint = f"{base}/chrome/screenshot"
    resp = requests.post(
        endpoint,
        json={
            "html": html_doc,
            "options": {"type": "png", "fullPage": False},
            "viewport": {
                "width": int(env("CARD_WIDTH", "1080")),
                "height": int(env("CARD_HEIGHT", "1080")),
                "deviceScaleFactor": 1,
            },
            "gotoOptions": {"waitUntil": "networkidle0", "timeout": 60000},
        },
        timeout=90,
    )
    resp.raise_for_status()
    out_path.write_bytes(resp.content)


def render_cards(briefing: dict[str, Any], out_dir: Path) -> list[Path]:
    brand = env("TISTORY_BLOG_NAME") or "경제 브리핑"
    slides = briefing.get("slides") or []
    paths: list[Path] = []
    story_i = 0
    for i, slide in enumerate(slides, start=1):
        stype = slide.get("type") or "story"
        headline = slide.get("headline") or ""
        body = slide.get("body") or ""
        if stype == "cover":
            html_doc = render_template("cover.html", headline=headline, body=body, brand=brand)
        elif stype == "disclaimer":
            html_doc = render_template("disclaimer.html", headline=headline, body=body, brand=brand)
        else:
            story_i += 1
            html_doc = render_template(
                "slide.html",
                index=f"0{story_i}",
                headline=headline,
                body=body,
                brand=brand,
            )
        path = out_dir / f"slide-{i:02d}.png"
        screenshot_html(html_doc, path)
        paths.append(path)
        print(f"  card rendered: {path.name}")
    return paths


def upload_r2(paths: list[Path], prefix: str) -> list[str]:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 required for R2 upload") from exc

    endpoint = env("R2_ENDPOINT")
    key_id = env("R2_ACCESS_KEY_ID")
    secret = env("R2_SECRET_ACCESS_KEY")
    bucket = env("R2_BUCKET")
    public_base = env("R2_PUBLIC_BASE_URL").rstrip("/")
    if not all([endpoint, key_id, secret, bucket, public_base]):
        raise RuntimeError("R2_* env vars incomplete")

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        region_name="auto",
    )
    urls: list[str] = []
    for path in paths:
        key = f"{prefix}/{path.name}"
        client.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={"ContentType": "image/png"},
        )
        urls.append(f"{public_base}/{key}")
    return urls


def instagram_carousel(image_urls: list[str], caption: str) -> str:
    ig_user = env("IG_USER_ID")
    token = env("META_ACCESS_TOKEN")
    version = env("META_GRAPH_VERSION", "v21.0")
    if not ig_user or not token:
        raise RuntimeError("IG_USER_ID / META_ACCESS_TOKEN required")
    base = f"https://graph.facebook.com/{version}"
    children: list[str] = []
    for url in image_urls:
        r = requests.post(
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

    parent = requests.post(
        f"{base}/{ig_user}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption[:2100],
            "access_token": token,
        },
        timeout=60,
    )
    parent.raise_for_status()
    creation_id = parent.json()["id"]

    for _ in range(20):
        st = requests.get(
            f"{base}/{creation_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=30,
        )
        st.raise_for_status()
        code = st.json().get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise RuntimeError(f"IG container error: {st.json()}")
        time.sleep(3)

    pub = requests.post(
        f"{base}/{ig_user}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=60,
    )
    pub.raise_for_status()
    return pub.json().get("id", creation_id)


def preview_text(briefing: dict[str, Any], picked: list[dict[str, Any]]) -> str:
    lines = [
        f"[초안] {briefing.get('title', '')}",
        briefing.get("market_one_liner", ""),
        "",
        "선정 뉴스:",
    ]
    for a in picked:
        lines.append(f"- ({a.get('score')}) {a['title']}")
    lines.append("")
    lines.append("슬라이드:")
    for s in briefing.get("slides") or []:
        lines.append(f"- [{s.get('type')}] {s.get('headline')}")
    lines.append("")
    lines.append("Approve / Skip 버튼 또는 /approve /skip")
    return "\n".join(lines)


def run_publish(
    briefing: dict[str, Any],
    picked: list[dict[str, Any]],
    now: datetime,
    run_dir: Path,
    store: SeenUrlsStore,
) -> None:
    print("==> Tistory write")
    tags = briefing.get("blog_tags") or []
    tistory_res = tistory_write(briefing.get("title") or "오늘의 경제 브리핑", briefing["blog_html"], tags)
    (run_dir / "tistory.json").write_text(json.dumps(tistory_res, ensure_ascii=False, indent=2), encoding="utf-8")
    tistory_post_id = extract_tistory_post_id(tistory_res)
    print(f"   tistory ok post_id={tistory_post_id}")

    ig_media_id: str | None = None
    print("==> Render cards via Browserless")
    cards_dir = run_dir / "cards"
    cards_dir.mkdir(exist_ok=True)
    try:
        paths = render_cards(briefing, cards_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"   !! card render skipped: {exc}")
        paths = []

    image_urls: list[str] = []
    if paths and env("R2_ACCESS_KEY_ID"):
        print("==> Upload R2")
        prefix = f"briefs/{now.strftime('%Y-%m-%d')}"
        image_urls = upload_r2(paths, prefix)
        (run_dir / "image_urls.json").write_text(json.dumps(image_urls, ensure_ascii=False, indent=2), encoding="utf-8")
    elif not env("R2_ACCESS_KEY_ID"):
        print("R2 not configured — skip Instagram (need public image URLs)")

    if image_urls and env("IG_USER_ID") and env("META_ACCESS_TOKEN"):
        caption = briefing.get("caption") or ""
        tags_h = " ".join(f"#{t.lstrip('#')}" for t in (briefing.get("hashtags") or []))
        print("==> Instagram carousel")
        ig_media_id = instagram_carousel(image_urls, f"{caption}\n\n{tags_h}".strip())
        print(f"   ig media id: {ig_media_id}")
        telegram_send(f"[발행완료]\n{briefing.get('title')}\nIG: {ig_media_id}")
    else:
        telegram_send(f"[부분발행] 티스토리 완료 / 인스타 스킵\n{briefing.get('title')}")

    n = store.record_published(picked, tistory_post_id=tistory_post_id, ig_media_id=ig_media_id)
    print(f"==> seen_urls recorded: {n} (backend={store.backend})")
    print("Done publish.")


def main() -> int:
    mode = env("MVP_MODE", "dry_run").lower()
    now = datetime.now(TZ)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    run_dir = OUTPUT / now.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    store = SeenUrlsStore()
    print(f"==> mode={mode} date={now.date()} tz={TZ} seen_urls={store.backend}")
    print(
        f"==> ollama threads={env('OLLAMA_NUM_THREAD', '4')} "
        f"rank_mode={env('RANK_MODE', 'llm')} "
        f"llm_candidates={env('NEWS_LLM_CANDIDATES', '10')}"
    )
    print("==> fetching Google News RSS")
    candidates = fetch_candidates(now)
    candidates = store.filter_new(candidates)
    print(f"   candidates today (capped, after seen_urls): {len(candidates)}")
    (run_dir / "candidates.json").write_text(
        json.dumps([{k: v for k, v in a.items() if k != "published_dt"} for a in candidates], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not candidates:
        print("No candidates for today. Exit.")
        if mode in {"draft", "publish"}:
            telegram_send(f"[경제브리핑] {now.date()} 당일 후보 0건 — 스킵")
        store.close()
        return 0

    print("==> Ollama importance ranking")
    picked = rank_articles(candidates, now, run_dir=run_dir)
    print(f"   picked: {len(picked)}")
    (run_dir / "ranked.json").write_text(
        json.dumps([{k: v for k, v in a.items() if k != "published_dt"} for a in picked], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not picked:
        print("No articles after ranking. Exit.")
        store.close()
        return 1

    print("==> Ollama briefing")
    briefing = build_briefing(picked, now)
    briefing["blog_html"] = assemble_blog_html(briefing)
    (run_dir / "briefing.json").write_text(
        json.dumps(briefing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"   title: {briefing.get('title')}")
    print(f"   wrote {run_dir}")

    try:
        if mode == "dry_run":
            print("Done (dry_run). Set MVP_MODE=draft for Approve→publish, or publish to post.")
            return 0

        if mode == "draft":
            preview = preview_text(briefing, picked)
            if not wait_for_approve(preview):
                print("Done (draft skipped). seen_urls not updated.")
                return 0
            run_publish(briefing, picked, now, run_dir, store)
            return 0

        if mode == "publish":
            run_publish(briefing, picked, now, run_dir, store)
            return 0

        print(f"Unknown MVP_MODE={mode}", file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        try:
            telegram_send(f"[경제브리핑 실패] {exc}")
        except Exception:  # noqa: BLE001
            pass
        raise SystemExit(1)
