#!/usr/bin/env python3
"""MVP pipeline: Google News → filter → Ollama rank/brief → Approve → markdown export.

Modes (MVP_MODE):
  dry_run  - fetch + LLM, write output/*.json (default)
  draft    - messenger preview + Approve/Skip; Approve → briefing.md (manual paste)
  publish  - write briefing.md without Approve wait
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import feedparser
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

from notify import get_notifier, resolve_channel  # noqa: E402
from seen_urls import SeenUrlsStore  # noqa: E402

TZ = ZoneInfo(os.getenv("NEWS_TIMEZONE", "Asia/Seoul"))
PROMPTS = ROOT / "prompts"
TEMPLATES = ROOT / "templates" / "cards"
OUTPUT = Path(os.getenv("OUTPUT_DIR", str(ROOT / "output")))


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def parse_notify_send_at(raw: str) -> tuple[int, int] | None:
    """Parse NOTIFY_SEND_AT as HH:MM (Asia/Seoul wall clock). Empty → None."""
    text = (raw or "").strip()
    if not text:
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not m:
        raise ValueError(f"NOTIFY_SEND_AT must be HH:MM, got {raw!r}")
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"NOTIFY_SEND_AT out of range: {raw!r}")
    return hour, minute


def notify_send_at_target(now: datetime, raw: str | None = None) -> datetime | None:
    """Today's send deadline in NEWS_TIMEZONE, or None if unset."""
    parsed = parse_notify_send_at(raw if raw is not None else env("NOTIFY_SEND_AT"))
    if parsed is None:
        return None
    hour, minute = parsed
    local = now.astimezone(TZ)
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0)


def wait_until_notify_send_at(now: datetime | None = None) -> None:
    """Block until NOTIFY_SEND_AT (KST). If already past, return immediately."""
    clock = now or datetime.now(TZ)
    target = notify_send_at_target(clock)
    if target is None:
        return
    remaining = (target - clock).total_seconds()
    if remaining <= 0:
        print(f"==> NOTIFY_SEND_AT={target.strftime('%H:%M')} already passed — send now")
        return
    print(
        f"==> waiting until NOTIFY_SEND_AT={target.strftime('%H:%M')} "
        f"({int(remaining)}s, tz={TZ})"
    )
    while True:
        clock = datetime.now(TZ)
        remaining = (target - clock).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 30.0))
    print(f"==> NOTIFY_SEND_AT reached — sending Approve preview")


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


def news_window_start(now: datetime) -> datetime:
    """Start of news inclusion window (Asia/Seoul local).

    NEWS_WINDOW_MODE:
      since_prev_day_hour (default) — previous calendar day at NEWS_WINDOW_PREV_DAY_HOUR
      today — calendar day 00:00 (legacy)
    """
    mode = env("NEWS_WINDOW_MODE").lower() or "since_prev_day_hour"
    local_now = now.astimezone(TZ)
    if mode == "today":
        return local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    hour = int(env("NEWS_WINDOW_PREV_DAY_HOUR", "15"))
    return (local_now - timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)


def in_news_window(dt: datetime | None, now: datetime, start: datetime) -> bool:
    if dt is None:
        return True
    local = dt.astimezone(TZ)
    return start <= local <= now.astimezone(TZ)


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
    start = news_window_start(now)
    print(f"   news window: {start.isoformat()} → {now.astimezone(TZ).isoformat()}")
    windowed = [a for a in merged if in_news_window(a.get("published_dt"), now, start)]
    print(f"   after window filter: {len(windowed)} (raw merge={len(merged)})")
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for a in windowed:
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


def ollama_chat(
    system: str,
    user: str,
    *,
    timeout_ms: int | None = None,
) -> tuple[Any, str]:
    model = env("OLLAMA_MODEL", "qwen2.5:14b")
    if timeout_ms is None:
        timeout_ms = int(env("OLLAMA_TIMEOUT_MS", "180000"))
    timeout = timeout_ms / 1000
    url = f"{ollama_base()}/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": ollama_options(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    keep_alive = env("OLLAMA_KEEP_ALIVE", "30m")
    if keep_alive:
        payload["keep_alive"] = keep_alive
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


def heuristic_score_all(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score every article with feed/cluster/watchlist heuristics (no truncate)."""
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
    return scored


def heuristic_rank(articles: list[dict[str, Any]], pick: int) -> list[dict[str, Any]]:
    return heuristic_score_all(articles)[:pick]


def normalize_importance_item(parsed: Any) -> dict[str, Any] | None:
    """Accept a single importance object (or legacy ranked[0])."""
    row: Any = None
    if isinstance(parsed, dict):
        ranked = parsed.get("ranked")
        if isinstance(ranked, list) and ranked and isinstance(ranked[0], dict):
            row = ranked[0]
        elif "score" in parsed or "id" in parsed:
            row = parsed
    elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        row = parsed[0]
    return row if isinstance(row, dict) else None


def apply_importance_row(base: dict[str, Any], row: dict[str, Any]) -> dict[str, Any] | None:
    if as_bool_drop(row.get("drop")):
        return None
    item = dict(base)
    try:
        item["score"] = int(row.get("score") or 0)
    except (TypeError, ValueError):
        item["score"] = int(base.get("score") or 0)
    item["audience"] = row.get("audience") or base.get("audience") or "general"
    item["reason"] = row.get("reason") or base.get("reason") or ""
    item["drop"] = False
    return item


def select_llm_candidates(
    scored: list[dict[str, Any]],
    min_score: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Heuristic score >= min_score, already sorted high→low, capped at limit."""
    above = [a for a in scored if int(a.get("score") or 0) >= min_score]
    return above[: max(0, limit)]


def rank_articles(
    articles: list[dict[str, Any]],
    now: datetime,
    run_dir: Path | None = None,
) -> list[dict[str, Any]]:
    pick = int(env("NEWS_PICK_COUNT", "5"))
    llm_limit = int(env("NEWS_LLM_CANDIDATES", "10"))
    min_score = int(env("HEURISTIC_MIN_SCORE", "8"))
    all_scored = heuristic_score_all(articles)
    use_llm = env("RANK_MODE", "llm").lower() != "heuristic"

    if not use_llm:
        print(f"   rank mode=heuristic → top {pick}")
        return all_scored[:pick]

    candidates = select_llm_candidates(all_scored, min_score, llm_limit)
    above_n = sum(1 for a in all_scored if int(a.get("score") or 0) >= min_score)
    print(
        f"   heuristic>={min_score}: {above_n} eligible → LLM {len(candidates)} "
        f"(cap={llm_limit})"
    )

    scored: list[dict[str, Any]] = []
    per_raw: list[dict[str, Any]] = []
    system = read_prompt("importance_system.md")
    watchlist = env("WATCHLIST", "")
    date_s = now.strftime("%Y-%m-%d")

    for idx, base in enumerate(candidates, start=1):
        payload = {
            "id": base["id"],
            "title": base["title"],
            "snippet": (base.get("snippet") or "")[:400],
            "source": base.get("source"),
            "topic": base.get("topic"),
            "feed_rank": base.get("feed_rank"),
            "cluster_size": base.get("cluster_size"),
        }
        user = (
            read_prompt("importance_user.md")
            .replace("{{date}}", date_s)
            .replace("{{watchlist}}", watchlist)
            .replace("{{article_json}}", json.dumps(payload, ensure_ascii=False, indent=2))
        )
        print(f"   LLM importance {idx}/{len(candidates)} id={base['id'][:8]}…")
        try:
            parsed, raw = ollama_chat(system, user)
            per_raw.append({"id": base["id"], "raw": raw, "parsed": parsed})
            row = normalize_importance_item(parsed)
            if row is None:
                print(f"   !! bad JSON for {base['id'][:8]} — keep heuristic")
                scored.append(dict(base))
                continue
            item = apply_importance_row(base, row)
            if item is None:
                print(f"   drop id={base['id'][:8]}")
                continue
            scored.append(item)
        except Exception as exc:  # noqa: BLE001
            print(f"   !! LLM fail {base['id'][:8]}: {exc} — keep heuristic")
            scored.append(dict(base))

    if run_dir is not None and per_raw:
        (run_dir / "importance_raw.json").write_text(
            json.dumps(per_raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    scored.sort(key=lambda x: (-int(x.get("score") or 0), x.get("feed_rank") or 99))
    picked = scored[:pick]
    if not picked:
        print("   !! no LLM ranks usable — heuristic top")
        return all_scored[:pick]
    return picked


def _clean_rss_snippet(raw: str) -> str:
    """Strip Google News boilerplate; keep the first chunk only."""
    text = re.sub(r"Google\s*뉴스에서[^\n]*", "", raw or "", flags=re.IGNORECASE).strip()
    if not text:
        return ""
    # Split on multi-whitespace BEFORE collapsing, so cluster chunks survive.
    parts = re.split(r"\s{2,}", text)
    first = re.sub(r"\s+", " ", (parts[0] if parts else text)).strip()
    if first:
        return first
    return re.sub(r"\s+", " ", text).strip()


def build_briefing_heuristic(articles: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """LLM 없이 발행 경로 스모크·폴백용 브리핑."""
    date = now.strftime("%Y-%m-%d")
    stories: list[dict[str, Any]] = []
    slides: list[dict[str, str]] = [
        {
            "type": "cover",
            "headline": f"{date} 경제 브리핑",
            "body": "오늘의 주요 경제 뉴스",
        }
    ]
    for i, a in enumerate(articles, start=1):
        headline = a.get("title") or f"이슈 {i}"
        cleaned = _clean_rss_snippet(a.get("snippet") or "")
        # Avoid Google News cluster dumps: prefer a short title-based line.
        if not cleaned or len(cleaned) > 120 or cleaned.startswith(headline):
            what = headline
        else:
            what = cleaned
        stories.append(
            {
                "headline": headline,
                "what_happened": what,
                "why_important": (
                    f"「{headline}」은(는) 시장·정책 흐름에 영향을 줄 수 있는 이슈입니다."
                ),
                "watch_next": (
                    f"「{headline}」의 후속 보도와 시장 반응을 지켜볼 필요가 있습니다."
                ),
                "one_liner": headline,
                "source_name": a.get("source") or "",
                "source_url": a.get("link") or "",
            }
        )
        slides.append(
            {
                "type": "story",
                "headline": headline[:80],
                "body": what[:160],
            }
        )
    slides.append(
        {
            "type": "disclaimer",
            "headline": "면책",
            "body": "정보 안내용이며 투자 권유가 아닙니다.",
        }
    )
    n = len(articles)
    return {
        "title": f"오늘 주요 경제·시장 이슈를 정리합니다 | 오늘의 경제 브리핑 ({date})",
        "intro": (
            "오늘 아침 경제·시장에서 주목할 이슈를 정리했습니다. "
            "각 이슈의 배경과 앞으로 확인할 점을 함께 살펴봅니다."
        ),
        "core_summary": [f"오늘 선정 이슈 {n}건을 정리했습니다."] if n else ["오늘 주요 경제 뉴스를 정리했습니다."],
        "stories": stories,
        "market_impact": {
            "positive": ["주요 이슈가 시장 관심을 높이고 있습니다."],
            "neutral": ["단기 변동성은 지속될 수 있습니다."],
            "negative": ["불확실성이 남아 있어 주의가 필요합니다."],
        },
        "insight": (
            "오늘 소개한 이슈들은 경제·시장 흐름을 이해하는 데 "
            "서로 연결된 맥락을 갖고 있습니다. 개별 뉴스보다 전체 흐름을 "
            "함께 보는 것이 도움이 됩니다."
        ),
        "upcoming_events": [
            {
                "date": "",
                "title": "주요 경제 지표·기업 실적 발표",
                "description": "이번 주 예정된 발표 일정을 확인하세요.",
            }
        ],
        "closing_remark": (
            "오늘도 핵심만 담아 전해드렸습니다. 내일 아침 브리핑에서도 "
            "중요한 흐름을 이어가겠습니다."
        ),
        "related_keywords": ["경제", "증시", "브리핑", "시장", "뉴스"],
        "blog_tags": ["경제", "브리핑", "뉴스"],
        "slides": slides,
        "caption": f"{date} 경제 브리핑",
        "hashtags": ["경제", "뉴스", "브리핑"],
    }


def _core_summary(briefing: dict[str, Any]) -> list[str]:
    points = briefing.get("core_summary") or briefing.get("today_points") or []
    if points:
        return [str(p) for p in points]
    one = (briefing.get("market_one_liner") or "").strip()
    return [one] if one else []


def _story_what_happened(story: dict[str, Any]) -> str:
    return (story.get("what_happened") or story.get("summary") or "").strip()


def _story_why_important(story: dict[str, Any]) -> str:
    return (story.get("why_important") or story.get("why_it_matters") or "").strip()


def _story_watch_next(story: dict[str, Any]) -> str:
    return (story.get("watch_next") or "").strip()


def _story_one_liner(story: dict[str, Any]) -> str:
    return (story.get("one_liner") or "").strip()


def _market_impact_lists(briefing: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    impact = briefing.get("market_impact") or {}
    if not isinstance(impact, dict):
        return [], [], []
    pos = impact.get("positive") or []
    neu = impact.get("neutral") or []
    neg = impact.get("negative") or []
    return [str(x) for x in pos], [str(x) for x in neu], [str(x) for x in neg]


def _safe_source_url(value: Any) -> str:
    url = str(value or "").strip()
    if re.match(r"^https?://", url, re.IGNORECASE):
        return url
    return "#"


def _body_bullet_lines(text: str) -> list[str]:
    """Wrap body as bullets; split on newlines only (no NLP sentence split)."""
    text = (text or "").strip()
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines or [text]


_BLOG_DISCLAIMER = (
    "※ 본 글은 정보 제공을 목적으로 작성되었으며 "
    "투자 또는 의사결정을 위한 전문적인 조언이 아닙니다."
)


def assemble_blog_html(briefing: dict[str, Any]) -> str:
    parts: list[str] = []
    intro = (briefing.get("intro") or "").strip()
    if intro:
        parts.append(f"<p>{html.escape(intro)}</p>")
        parts.append("<hr>")

    summary = _core_summary(briefing)
    if summary:
        parts.append("<h2>📌 오늘의 핵심 요약</h2><ul>")
        for point in summary:
            parts.append(f"<li>{html.escape(point)}</li>")
        parts.append("</ul><hr>")

    for i, story in enumerate(briefing.get("stories") or [], start=1):
        headline = (story.get("headline") or "").strip()
        parts.append(f"<h2>{i}. {html.escape(headline)}</h2>")
        what = _story_what_happened(story)
        if what:
            parts.append("<h3>📰 무슨 일이 있었나?</h3><ul>")
            for line in _body_bullet_lines(what):
                parts.append(f"<li>{html.escape(line)}</li>")
            parts.append("</ul>")
        why = _story_why_important(story)
        if why:
            parts.append("<h3>💡 왜 중요한가?</h3><ul>")
            for line in _body_bullet_lines(why):
                parts.append(f"<li>{html.escape(line)}</li>")
            parts.append("</ul>")
        watch = _story_watch_next(story)
        if watch:
            parts.append("<h3>🔭 앞으로 주목할 점</h3><ul>")
            for line in _body_bullet_lines(watch):
                parts.append(f"<li>{html.escape(line)}</li>")
            parts.append("</ul>")
        one = _story_one_liner(story)
        if one:
            parts.append("<h3>✍️ 한 줄 요약</h3>")
            parts.append(f"<p>{html.escape(one)}</p>")
        name = html.escape(story.get("source_name") or "")
        url = html.escape(_safe_source_url(story.get("source_url")), quote=True)
        if name or story.get("source_url"):
            parts.append(f'<p>출처: <a href="{url}">{name or "링크"}</a></p>')
        parts.append("<hr>")

    pos, neu, neg = _market_impact_lists(briefing)
    if pos or neu or neg:
        parts.append("<h2>📈 오늘의 시장·산업 영향</h2>")
        if pos:
            parts.append("<p><strong>긍정적인 영향</strong></p><ul>")
            for item in pos:
                parts.append(f"<li>{html.escape(item)}</li>")
            parts.append("</ul>")
        if neu:
            parts.append("<p><strong>중립적인 영향</strong></p><ul>")
            for item in neu:
                parts.append(f"<li>{html.escape(item)}</li>")
            parts.append("</ul>")
        if neg:
            parts.append("<p><strong>부정적인 영향</strong></p><ul>")
            for item in neg:
                parts.append(f"<li>{html.escape(item)}</li>")
            parts.append("</ul>")

    insight = (briefing.get("insight") or "").strip()
    if insight:
        parts.append("<h2>🔍 오늘의 인사이트</h2>")
        parts.append(f"<p>{html.escape(insight)}</p>")

    events = briefing.get("upcoming_events") or []
    if events:
        parts.append("<h2>📅 앞으로 주목할 일정</h2><ul>")
        for ev in events:
            if not isinstance(ev, dict):
                parts.append(f"<li>{html.escape(str(ev))}</li>")
                continue
            date = (ev.get("date") or "").strip()
            title = (ev.get("title") or "").strip()
            desc = (ev.get("description") or "").strip()
            label = " — ".join(x for x in [date, title] if x) or title
            if desc:
                label = f"{label}: {desc}" if label else desc
            parts.append(f"<li>{html.escape(label)}</li>")
        parts.append("</ul>")

    closing = (briefing.get("closing_remark") or "").strip()
    if closing:
        parts.append("<h2>✨ 오늘의 한마디</h2>")
        parts.append(f"<p>{html.escape(closing)}</p>")

    parts.append("<hr>")
    keywords = briefing.get("related_keywords") or []
    if keywords:
        parts.append("<h3>관련 키워드</h3>")
        parts.append(f"<p>{html.escape(', '.join(str(k) for k in keywords))}</p>")
    parts.append(f"<p>{html.escape(_BLOG_DISCLAIMER)}</p>")
    return "\n".join(parts)


def assemble_blog_markdown(briefing: dict[str, Any]) -> str:
    """티스토리 등 에디터에 수동 붙여넣기용 Markdown."""
    title = (briefing.get("title") or "오늘의 경제 브리핑").strip()
    tags = briefing.get("blog_tags") or []
    lines: list[str] = [f"# {title}", ""]

    intro = (briefing.get("intro") or "").strip()
    if intro:
        lines.append(intro)
        lines.append("")
        lines.append("---")
        lines.append("")

    summary = _core_summary(briefing)
    if summary:
        lines.append("## 📌 오늘의 핵심 요약")
        lines.append("")
        for point in summary:
            lines.append(f"- {point}")
        lines.append("")
        lines.append("---")
        lines.append("")

    for i, story in enumerate(briefing.get("stories") or [], start=1):
        headline = (story.get("headline") or "").strip()
        lines.append(f"## {i}. {headline}" if headline else f"## {i}.")
        lines.append("")
        what = _story_what_happened(story)
        if what:
            lines.append("### 📰 무슨 일이 있었나?")
            for line in _body_bullet_lines(what):
                lines.append(f"- {line}")
            lines.append("")
        why = _story_why_important(story)
        if why:
            lines.append("### 💡 왜 중요한가?")
            for line in _body_bullet_lines(why):
                lines.append(f"- {line}")
            lines.append("")
        watch = _story_watch_next(story)
        if watch:
            lines.append("### 🔭 앞으로 주목할 점")
            for line in _body_bullet_lines(watch):
                lines.append(f"- {line}")
            lines.append("")
        one = _story_one_liner(story)
        if one:
            lines.append("### ✍️ 한 줄 요약")
            lines.append(one)
            lines.append("")
        name = (story.get("source_name") or "").strip()
        raw_url = (story.get("source_url") or "").strip()
        url = _safe_source_url(raw_url)
        if raw_url:
            label = name or "출처"
            lines.append(f"출처: [{label}]({url})")
            lines.append("")
        elif name:
            lines.append(f"출처: {name}")
            lines.append("")
        lines.append("---")
        lines.append("")

    pos, neu, neg = _market_impact_lists(briefing)
    if pos or neu or neg:
        lines.append("## 📈 오늘의 시장·산업 영향")
        lines.append("")
        if pos:
            lines.append("**긍정적인 영향**")
            for item in pos:
                lines.append(f"- {item}")
            lines.append("")
        if neu:
            lines.append("**중립적인 영향**")
            for item in neu:
                lines.append(f"- {item}")
            lines.append("")
        if neg:
            lines.append("**부정적인 영향**")
            for item in neg:
                lines.append(f"- {item}")
            lines.append("")

    insight = (briefing.get("insight") or "").strip()
    if insight:
        lines.append("## 🔍 오늘의 인사이트")
        lines.append("")
        lines.append(insight)
        lines.append("")

    events = briefing.get("upcoming_events") or []
    if events:
        lines.append("## 📅 앞으로 주목할 일정")
        lines.append("")
        for ev in events:
            if not isinstance(ev, dict):
                lines.append(f"- {ev}")
                continue
            date = (ev.get("date") or "").strip()
            ev_title = (ev.get("title") or "").strip()
            desc = (ev.get("description") or "").strip()
            label = " — ".join(x for x in [date, ev_title] if x) or ev_title
            if desc:
                label = f"{label}: {desc}" if label else desc
            lines.append(f"- {label}")
        lines.append("")

    closing = (briefing.get("closing_remark") or "").strip()
    if closing:
        lines.append("## ✨ 오늘의 한마디")
        lines.append("")
        lines.append(closing)
        lines.append("")

    lines.append("---")
    lines.append("")
    keywords = briefing.get("related_keywords") or []
    if keywords:
        lines.append("### 관련 키워드")
        lines.append("")
        lines.append(", ".join(str(k) for k in keywords))
        lines.append("")
    lines.append(_BLOG_DISCLAIMER)
    if tags:
        lines.append("")
        lines.append("태그: " + ", ".join(str(t) for t in tags))
    return "\n".join(lines).rstrip() + "\n"


def build_briefing(articles: list[dict[str, Any]], now: datetime) -> tuple[dict[str, Any], str]:
    if env("BRIEFING_MODE", "llm").lower() == "heuristic":
        print("   briefing mode=heuristic")
        return build_briefing_heuristic(articles, now), "heuristic"

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
    briefing_timeout_ms = int(
        env("OLLAMA_BRIEFING_TIMEOUT_MS") or env("OLLAMA_TIMEOUT_MS", "600000")
    )
    try:
        parsed, raw = ollama_chat(
            read_prompt("briefing_system.md"),
            user,
            timeout_ms=briefing_timeout_ms,
        )
        if not isinstance(parsed, dict):
            raise RuntimeError(f"briefing JSON must be object, got {type(parsed)}: {raw[:500]}")
        return parsed, "llm"
    except Exception as exc:  # noqa: BLE001
        if env("ALLOW_BRIEFING_FALLBACK", "1").lower() in {"1", "true", "yes"}:
            print(f"   !! LLM briefing failed: {exc} — heuristic fallback")
            return build_briefing_heuristic(articles, now), "heuristic"
        raise


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
    brand = env("CARD_BRAND") or "경제 브리핑"
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


def preview_text(
    briefing: dict[str, Any],
    picked: list[dict[str, Any]],
    generation_mode: str = "llm",
) -> str:
    mode_label = "heuristic" if generation_mode == "heuristic" else "llm"
    lines = [
        f"[초안] {briefing.get('title', '')}",
        f"생성: {mode_label}",
        "",
    ]
    for point in _core_summary(briefing)[:3]:
        lines.append(f"- {point}")
    insight = (briefing.get("insight") or "").strip()
    if insight:
        lines.append("")
        lines.append(insight[:120] + ("…" if len(insight) > 120 else ""))
    lines.extend(["", "선정 뉴스:"])
    for a in picked:
        lines.append(f"- ({a.get('score')}) {a['title']}")
    lines.append("")
    lines.append("슬라이드:")
    for s in briefing.get("slides") or []:
        lines.append(f"- [{s.get('type')}] {s.get('headline')}")
    lines.append("")
    lines.append("Approve 시 briefing.md 저장 (수동 붙여넣기용)")
    lines.append("Discord: ✅ / ⏭  ·  Telegram: 버튼 또는 /approve /skip")
    return "\n".join(lines)


def run_publish(
    briefing: dict[str, Any],
    picked: list[dict[str, Any]],
    now: datetime,
    run_dir: Path,
    store: SeenUrlsStore,
    notifier: Any,
    generation_mode: str = "llm",
) -> None:
    """Approve 후: 마크다운 저장(+선택 카드/인스타) → seen_urls 기록."""
    print("==> Write briefing markdown (manual paste)")
    md = assemble_blog_markdown(briefing)
    md_path = run_dir / "briefing.md"
    md_path.write_text(md, encoding="utf-8")
    (run_dir / "briefing.html").write_text(briefing.get("blog_html") or assemble_blog_html(briefing), encoding="utf-8")
    export_ref = str(md_path.resolve())
    print(f"   wrote {md_path}")

    ig_media_id: str | None = None
    if env("PUBLISH_CARDS", "0").lower() in {"1", "true", "yes"}:
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
            (run_dir / "image_urls.json").write_text(
                json.dumps(image_urls, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        elif not env("R2_ACCESS_KEY_ID"):
            print("R2 not configured — skip Instagram")

        if image_urls and env("IG_USER_ID") and env("META_ACCESS_TOKEN"):
            caption = briefing.get("caption") or ""
            tags_h = " ".join(f"#{t.lstrip('#')}" for t in (briefing.get("hashtags") or []))
            print("==> Instagram carousel")
            ig_media_id = instagram_carousel(image_urls, f"{caption}\n\n{tags_h}".strip())
            print(f"   ig media id: {ig_media_id}")

    mode_label = "heuristic" if generation_mode == "heuristic" else "llm"
    caption = (
        f"[마크다운 준비됨]\n생성: {mode_label}\n{briefing.get('title')}\n"
        f"경로: {md_path}\n에디터에 붙여넣기 하세요."
    )
    send_file = getattr(notifier, "send_file", None)
    if callable(send_file):
        try:
            send_file(md_path, caption=caption)
        except Exception as exc:  # noqa: BLE001
            print(f"   !! send_file failed: {exc}")
            notifier.send_text(f"{caption}\n\n---\n{md[:1500]}")
    else:
        notifier.send_text(f"{caption}\n\n---\n{md[:1500]}")

    n = store.record_published(picked, tistory_post_id=export_ref, ig_media_id=ig_media_id)
    print(f"==> seen_urls recorded: {n} (backend={store.backend})")
    print("Done (markdown export).")


def main() -> int:
    mode = env("MVP_MODE", "dry_run").lower()
    now = datetime.now(TZ)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    run_dir = OUTPUT / now.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    notifier = get_notifier()
    channel = resolve_channel()
    store = SeenUrlsStore()
    print(
        f"==> mode={mode} date={now.date()} tz={TZ} "
        f"seen_urls={store.backend} notify={channel}"
    )
    print(
        f"==> ollama threads={env('OLLAMA_NUM_THREAD', '4')} "
        f"rank_mode={env('RANK_MODE', 'llm')} "
        f"heuristic_min={env('HEURISTIC_MIN_SCORE', '8')} "
        f"llm_candidates={env('NEWS_LLM_CANDIDATES', '10')}"
    )
    print("==> fetching Google News RSS")
    candidates = fetch_candidates(now)
    candidates = store.filter_new(candidates)
    print(f"   candidates in window (capped, after seen_urls): {len(candidates)}")
    (run_dir / "candidates.json").write_text(
        json.dumps([{k: v for k, v in a.items() if k != "published_dt"} for a in candidates], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not candidates:
        print("No candidates in news window. Exit.")
        if mode in {"draft", "publish"}:
            notifier.send_text(f"[경제브리핑] {now.date()} 창 내 후보 0건 — 스킵")
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
    briefing, generation_mode = build_briefing(picked, now)
    briefing["blog_html"] = assemble_blog_html(briefing)
    (run_dir / "briefing.json").write_text(
        json.dumps(briefing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"   title: {briefing.get('title')}")
    print(f"   generation: {generation_mode}")
    print(f"   wrote {run_dir}")

    try:
        if mode == "dry_run":
            print("Done (dry_run). Set MVP_MODE=draft for Approve→markdown, or publish to export.md.")
            return 0

        if mode == "draft":
            preview = preview_text(briefing, picked, generation_mode=generation_mode)
            wait_until_notify_send_at()
            print(f"==> Approve gate channel={channel}")
            if not notifier.wait_for_approve(preview):
                print("Done (draft skipped). seen_urls not updated.")
                return 0
            run_publish(
                briefing, picked, now, run_dir, store, notifier, generation_mode=generation_mode
            )
            return 0

        if mode == "publish":
            run_publish(
                briefing, picked, now, run_dir, store, notifier, generation_mode=generation_mode
            )
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
            get_notifier().send_text(f"[경제브리핑 실패] {exc}")
        except Exception:  # noqa: BLE001
            pass
        raise SystemExit(1)
