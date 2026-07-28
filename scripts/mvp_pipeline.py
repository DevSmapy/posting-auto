#!/usr/bin/env python3
"""MVP pipeline: Google News → filter → Ollama rank/brief → gates → markdown export.

Modes (MVP_MODE):
  dry_run  - fetch + LLM, write output/*.json (default)
  draft    - 2-stage gates (content → render) + cleanup ask → briefing.md
  publish  - write briefing.md without Approve wait
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
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

from cards import (  # noqa: E402
    CardAssembler,
    CardBundle,
    CardFormatConfig,
    CardRenderer,
    InstagramPost,
    Slide,
)
from notify import GateAction, GateStage, get_notifier, resolve_channel  # noqa: E402
from notify.approve_copy import (  # noqa: E402
    cleanup_prompt,
    cleanup_timeout_notice,
    exhausted_message,
    regenerating_ack,
    render_stage_start_ack,
)
from draft_run import DraftRunStore  # noqa: E402
from publish import (  # noqa: E402
    PublishCardsPipeline,
    PublishConfig,
)
from seen_urls import SeenUrlsStore  # noqa: E402
from story_quality import (  # noqa: E402
    deterministic_story_repair,
    issues_summary,
    normalize_story_fields,
    target_language,
    target_locale,
    validate_story_fields,
)

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


def release_ollama_only() -> None:
    """Stop managed ollama after content stage (keeps aux untouched)."""
    if not as_bool_drop(env("OLLAMA_AUTO_CONTAINER", "0")):
        return
    _run_draft_lifecycle("draft_release_ollama")


def release_aux_only() -> None:
    """Stop postgres/browserless after render stage."""
    if not as_bool_drop(env("DRAFT_AUTO_AUX", "0")):
        return
    _run_draft_lifecycle("draft_stop_aux_containers")


def release_ollama_after_llm() -> None:
    """Unload model and stop ollama (+ aux when managed) after LLM work.

    Default off so bare `python scripts/mvp_pipeline.py` does not stop a
    manually started container. `run_draft.sh` exports OLLAMA_AUTO_CONTAINER=1.
    Used by publish/dry_run single-pass flows — not between draft content retries.
    """
    auto_ollama = as_bool_drop(env("OLLAMA_AUTO_CONTAINER", "0"))
    auto_aux = as_bool_drop(env("DRAFT_AUTO_AUX", "0"))
    if not auto_ollama and not auto_aux:
        return
    _run_draft_lifecycle("draft_release_after_llm")


def ollama_is_ready() -> bool:
    """Best-effort health check for the host-side Ollama HTTP endpoint."""
    try:
        r = requests.get(f"{ollama_base()}/api/tags", timeout=2)
        return r.ok
    except requests.RequestException:
        return False


def ensure_runtime_before_llm(mode: str) -> None:
    """Align bare draft/publish runs with run_draft.sh startup behavior.

    If Ollama is already reachable, leave the current runtime alone.
    Otherwise, draft/publish should best-effort start the same managed
    containers that run_draft.sh uses so direct `uv run ... mvp_pipeline.py`
    behaves the same as the wrapper script.
    """
    if mode not in {"draft", "publish"}:
        return
    if ollama_is_ready():
        return

    if not as_bool_drop(env("OLLAMA_AUTO_CONTAINER", "0")):
        os.environ["OLLAMA_AUTO_CONTAINER"] = "1"
    if not as_bool_drop(env("DRAFT_AUTO_AUX", "0")):
        os.environ["DRAFT_AUTO_AUX"] = "1"

    print("==> Ollama not reachable — bootstrap LLM runtime (same as run_draft.sh)")
    _run_draft_lifecycle("draft_start_llm_runtime")


def ensure_aux_before_publish() -> None:
    """Bring postgres/browserless back up after Approve wait (if managed)."""
    if not as_bool_drop(env("DRAFT_AUTO_AUX", "0")):
        return
    _run_draft_lifecycle("draft_start_aux_containers")


def release_aux_after_approve_render() -> None:
    """Deprecated alias — stops aux only (ollama released after content stage)."""
    release_aux_only()


def _run_draft_lifecycle(fn_name: str) -> None:
    script = ROOT / "scripts" / "draft_lifecycle.sh"
    if not script.is_file():
        print(f"   !! missing {script.name}; skip {fn_name}")
        return
    env_prefix = {
        "OLLAMA_AUTO_CONTAINER": env("OLLAMA_AUTO_CONTAINER", "0") or "0",
        "DRAFT_AUTO_AUX": env("DRAFT_AUTO_AUX", "0") or "0",
        "OLLAMA_CONTAINER": env("OLLAMA_CONTAINER", "ollama"),
        "OLLAMA_MODEL": env("OLLAMA_MODEL", "qwen2.5:7b"),
        "ROOT": str(ROOT),
    }
    try:
        subprocess.run(
            ["bash", "-c", f'source "{script}" && {fn_name}'],
            check=False,
            env={**os.environ, **env_prefix},
            cwd=str(ROOT),
        )
    except OSError as exc:
        print(f"   !! {fn_name} failed: {exc}")


def story_timeout_ms() -> int:
    """OLLAMA_STORY_TIMEOUT_MS → OLLAMA_BRIEFING_TIMEOUT_MS → OLLAMA_TIMEOUT_MS → 120000."""
    return int(
        env("OLLAMA_STORY_TIMEOUT_MS")
        or env("OLLAMA_BRIEFING_TIMEOUT_MS")
        or env("OLLAMA_TIMEOUT_MS", "120000")
    )


def briefing_timeout_ms() -> int:
    """Deprecated alias — prefer story_timeout_ms() for per-article calls."""
    return story_timeout_ms()


def ollama_options() -> dict[str, Any]:
    """Match draft_lifecycle ollama_warm_model defaults (num_ctx/num_thread)."""
    return {
        "temperature": float(env("OLLAMA_TEMPERATURE", "0.3")),
        "num_thread": int(env("OLLAMA_NUM_THREAD", "4")),
        "num_ctx": int(env("OLLAMA_NUM_CTX", "4096")),
    }


def _generation_mode_label(generation_mode: str) -> str:
    return generation_mode if generation_mode in {"heuristic", "mixed", "llm"} else "llm"


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


def heuristic_story_fields(article: dict[str, Any], index: int = 1) -> dict[str, Any]:
    """Single-story fallback fields (no envelope)."""
    headline = article.get("title") or f"이슈 {index}"
    cleaned = _clean_rss_snippet(article.get("snippet") or "")
    if not cleaned or len(cleaned) > 120 or cleaned.startswith(headline):
        what = headline
    else:
        what = cleaned
    return {
        "headline": headline,
        "what_happened": what,
        "why_important": (
            f"「{headline}」은(는) 시장·정책 흐름에 영향을 줄 수 있는 이슈입니다."
        ),
        "watch_next": (
            f"「{headline}」의 후속 보도와 시장 반응을 지켜볼 필요가 있습니다."
        ),
        "one_liner": headline,
        "source_name": article.get("source") or "",
        "source_url": article.get("link") or "",
    }


def _card_bundle_from_stories(
    stories: list[dict[str, Any]],
    now: datetime,
    related_keywords: list[str] | None = None,
) -> CardBundle:
    """Assemble card slides + Instagram caption via scripts/cards."""
    config = CardFormatConfig.from_env()
    keywords = related_keywords or ["경제", "증시", "브리핑", "시장", "뉴스"]
    return CardAssembler(config).assemble(stories, now, related_keywords=keywords)


def assemble_briefing_from_stories(
    stories: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    """Build full briefing envelope from per-story objects (rule-based)."""
    date = now.strftime("%Y-%m-%d")
    n = len(stories)
    one_liners = [
        str(s.get("one_liner") or s.get("headline") or "").strip()
        for s in stories
        if (s.get("one_liner") or s.get("headline"))
    ]
    core = one_liners[:5] if one_liners else (
        [f"오늘 선정 이슈 {n}건을 정리했습니다."] if n else ["오늘 주요 경제 뉴스를 정리했습니다."]
    )
    related_keywords = ["경제", "증시", "브리핑", "시장", "뉴스"]
    card_bundle = _card_bundle_from_stories(stories, now, related_keywords)
    return {
        "title": f"오늘 주요 경제·시장 이슈를 정리합니다 | 오늘의 경제 브리핑 ({date})",
        "intro": (
            "오늘 아침 경제·시장에서 주목할 이슈를 정리했습니다. "
            "각 이슈의 배경과 앞으로 확인할 점을 함께 살펴봅니다."
        ),
        "core_summary": core,
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
        "related_keywords": related_keywords,
        "blog_tags": ["경제", "브리핑", "뉴스"],
        "slides": card_bundle.slides_as_dicts(),
        "caption": card_bundle.post.body,
        "hashtags": list(card_bundle.post.hashtags),
        "instagram_post": card_bundle.post.full_text,
    }


def build_briefing_heuristic(articles: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """LLM 없이 발행 경로 스모크·폴백용 브리핑."""
    stories = [
        heuristic_story_fields(a, index=i) for i, a in enumerate(articles, start=1)
    ]
    return assemble_briefing_from_stories(stories, now)


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


def summarize_story_fact_llm(article: dict[str, Any], now: datetime) -> tuple[dict[str, Any], str]:
    """One article -> fact-layer JSON."""
    snippet = _clean_rss_snippet(article.get("snippet") or "")
    if len(snippet) > 400:
        snippet = snippet[:400].rstrip() + "…"
    payload = {
        "title": article.get("title"),
        "snippet": snippet,
        "source": article.get("source"),
        "link": article.get("link"),
        "topic": article.get("topic"),
        "score": article.get("score"),
        "reason": article.get("reason"),
    }
    user = (
        read_prompt("story_fact_user.md")
        .replace("{{date}}", now.strftime("%Y-%m-%d"))
        .replace("{{article_json}}", json.dumps(payload, ensure_ascii=False, indent=2))
    )
    parsed, raw = ollama_chat(
        read_prompt("story_fact_system.md"),
        user,
        timeout_ms=story_timeout_ms(),
    )
    if not isinstance(parsed, dict):
        raise RuntimeError(f"bad fact JSON: {raw[:500]}")
    return parsed, raw


def _story_llm_call(
    *,
    system_prompt: str,
    user_prompt: str,
    article: dict[str, Any],
    error_label: str,
) -> tuple[dict[str, Any], str]:
    """Shared Ollama JSON call + story field normalization for translate/polish."""
    parsed, raw = ollama_chat(
        system_prompt,
        user_prompt,
        timeout_ms=story_timeout_ms(),
    )
    try:
        return normalize_story_fields(parsed, article), raw
    except RuntimeError:
        raise RuntimeError(f"bad {error_label} JSON: {raw[:500]}") from None


def translate_story_fact_llm(
    fact: dict[str, Any],
    article: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], str]:
    """Fact-layer JSON -> target-language story draft."""
    user = (
        read_prompt("story_translate_user.md")
        .replace("{{date}}", now.strftime("%Y-%m-%d"))
        .replace("{{target_language}}", target_language())
        .replace("{{target_locale}}", target_locale())
        .replace("{{fact_json}}", json.dumps(fact, ensure_ascii=False, indent=2))
    )
    return _story_llm_call(
        system_prompt=read_prompt("story_translate_system.md"),
        user_prompt=user,
        article=article,
        error_label="translated story",
    )


def polish_story_llm(
    story: dict[str, Any],
    issues: list[str],
    article: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], str]:
    """Repair language/style/length issues while preserving facts."""
    user = (
        read_prompt("story_polish_user.md")
        .replace("{{date}}", now.strftime("%Y-%m-%d"))
        .replace("{{target_language}}", target_language())
        .replace("{{target_locale}}", target_locale())
        .replace("{{issues}}", issues_summary(issues))
        .replace("{{story_json}}", json.dumps(story, ensure_ascii=False, indent=2))
    )
    return _story_llm_call(
        system_prompt=read_prompt("story_polish_system.md"),
        user_prompt=user,
        article=article,
        error_label="polished story",
    )


def _with_story_source(story: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    out = dict(story)
    out["source_name"] = article.get("source") or out.get("source_name") or ""
    out["source_url"] = article.get("link") or out.get("source_url") or ""
    return out


def _attach_story_debug(exc: BaseException, debug: dict[str, Any]) -> None:
    try:
        setattr(exc, "story_debug", debug)
    except Exception:  # noqa: BLE001
        pass


def summarize_story_layers(
    article: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """One article -> fact -> translate -> validate/repair -> final story."""
    debug: dict[str, Any] = {"id": article.get("id"), "target_language": target_language()}
    try:
        fact, fact_raw = summarize_story_fact_llm(article, now)
        debug["fact"] = {"parsed": fact, "raw": fact_raw}

        translated, translated_raw = translate_story_fact_llm(fact, article, now)
        debug["translated"] = {"parsed": translated, "raw": translated_raw}

        repaired = _with_story_source(deterministic_story_repair(translated), article)
        issues = validate_story_fields(repaired)
        debug["initial_issues"] = list(issues)
        if not issues:
            debug["final"] = dict(repaired)
            return repaired, debug

        polished, polish_raw = polish_story_llm(repaired, issues, article, now)
        debug["polished"] = {"parsed": polished, "raw": polish_raw}
        polished = _with_story_source(deterministic_story_repair(polished), article)
        final_issues = validate_story_fields(polished)
        debug["final_issues"] = list(final_issues)
        if final_issues:
            raise RuntimeError(
                "story quality failed after polish: " + ", ".join(final_issues[:6])
            )
        debug["final"] = dict(polished)
        return polished, debug
    except Exception as exc:  # noqa: BLE001
        _attach_story_debug(exc, debug)
        raise


def build_briefing(
    articles: list[dict[str, Any]],
    now: datetime,
    run_dir: Path | None = None,
) -> tuple[dict[str, Any], str]:
    if env("BRIEFING_MODE", "llm").lower() == "heuristic":
        print("   briefing mode=heuristic")
        return build_briefing_heuristic(articles, now), "heuristic"

    stories: list[dict[str, Any]] = []
    story_raw: list[dict[str, Any]] = []
    llm_ok = 0
    allow_fb = env("ALLOW_BRIEFING_FALLBACK", "1").lower() in {"1", "true", "yes"}
    n = len(articles)
    for idx, article in enumerate(articles, start=1):
        print(f"   LLM story {idx}/{n} id={(article.get('id') or '')[:8]}…")
        try:
            story, debug = summarize_story_layers(article, now)
            stories.append(story)
            story_raw.append(debug)
            llm_ok += 1
        except Exception as exc:  # noqa: BLE001
            if not allow_fb:
                raise
            print(f"   !! story LLM failed: {exc} — heuristic story fallback")
            stories.append(heuristic_story_fields(article, index=idx))
            failure: dict[str, Any] = {}
            layer_debug = getattr(exc, "story_debug", None)
            if isinstance(layer_debug, dict):
                failure.update(layer_debug)
            failure["id"] = article.get("id") or failure.get("id")
            failure["fallback"] = "heuristic"
            failure["error"] = str(exc)
            story_raw.append(failure)

    if run_dir is not None and story_raw:
        (run_dir / "story_raw.json").write_text(
            json.dumps(story_raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    briefing = assemble_briefing_from_stories(stories, now)
    if llm_ok == 0:
        mode = "heuristic"
    elif llm_ok == n:
        mode = "llm"
    else:
        mode = "mixed"
    print(f"   stories llm={llm_ok}/{n} → generation={mode}")
    return briefing, mode


def screenshot_html(html_doc: str, out_path: Path) -> None:
    """Screenshot HTML via CardRenderer (Browserless, then local Chrome)."""
    CardRenderer(CardFormatConfig.from_env()).screenshot_html(html_doc, out_path)


def bundle_from_briefing(
    briefing: dict[str, Any],
    now: datetime | None = None,
    config: CardFormatConfig | None = None,
) -> CardBundle:
    """Rebuild CardBundle preferring reviewed slides/caption over re-assembly."""
    cfg = config or CardFormatConfig.from_env()
    clock = now or datetime.now(TZ)
    keywords = [str(k) for k in (briefing.get("related_keywords") or [])]
    raw_slides = list(briefing.get("slides") or [])
    body = str(briefing.get("caption") or "")
    full = str(briefing.get("instagram_post") or "")
    hashtags = tuple(str(t).lstrip("#") for t in (briefing.get("hashtags") or []))

    # Prefer already-assembled/reviewed card content when present.
    if raw_slides and (body or full):
        slides = tuple(Slide.from_dict(s) for s in raw_slides)
        if not full:
            tags = " ".join(f"#{t}" for t in hashtags)
            full = f"{body}\n\n{tags}".strip() if tags else body
        return CardBundle(
            slides=slides,
            post=InstagramPost(body=body, hashtags=hashtags, full_text=full),
            related_keywords=tuple(keywords),
        )

    stories = list(briefing.get("stories") or [])
    if stories:
        return CardAssembler(cfg).assemble(
            stories, clock, related_keywords=keywords or None
        )

    slides = tuple(Slide.from_dict(s) for s in raw_slides)
    if not full:
        tags = " ".join(f"#{t}" for t in hashtags)
        full = f"{body}\n\n{tags}".strip() if tags else body
    return CardBundle(
        slides=slides,
        post=InstagramPost(body=body, hashtags=hashtags, full_text=full),
        related_keywords=tuple(keywords),
    )


def render_cards(
    briefing: dict[str, Any],
    out_dir: Path,
    now: datetime | None = None,
) -> list[Path]:
    """Export card HTML/PNG + Instagram caption files; return PNG paths."""
    config = CardFormatConfig.from_env()
    bundle = bundle_from_briefing(briefing, now=now, config=config)
    result = CardRenderer(config).export(
        bundle, out_dir, render_png=True
    )
    return list(result.get("png") or [])  # type: ignore[arg-type]


def preview_text(
    briefing: dict[str, Any],
    picked: list[dict[str, Any]],
    generation_mode: str = "llm",
    *,
    has_card_images: bool | None = None,
    include_approve_hints: bool = True,
) -> str:
    from notify.approve_copy import APPROVE_CONTROLS_HINT, APPROVE_IMAGE_HINT

    mode_label = _generation_mode_label(generation_mode)
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
        body = (s.get("body") or "").replace("\n", " ")
        if len(body) > 60:
            body = body[:59] + "…"
        lines.append(f"- [{s.get('type')}] {s.get('headline')} — {body}")
    ig_post = (briefing.get("instagram_post") or briefing.get("caption") or "").strip()
    if ig_post:
        lines.append("")
        lines.append(f"인스타 본문 ({len(ig_post)}자):")
        preview = ig_post if len(ig_post) <= 280 else ig_post[:279] + "…"
        lines.append(preview)
    if include_approve_hints:
        lines.append("")
        if has_card_images is False:
            lines.append(
                "카드 이미지 생성 실패 또는 없음 — 텍스트만으로 Approve 할 수 있습니다."
            )
        else:
            lines.append(APPROVE_IMAGE_HINT)
        lines.append("Approve 시 briefing.md 저장 (수동 붙여넣기) + 선택적 R2/인스타")
        lines.append(APPROVE_CONTROLS_HINT)
    return "\n".join(lines)


def render_cards_for_approve(
    briefing: dict[str, Any],
    run_dir: Path,
    now: datetime,
) -> list[Path]:
    """Render card PNG/HTML before Approve so operators can review slides."""
    cards_dir = run_dir / "cards"
    cards_dir.mkdir(exist_ok=True)
    print("==> Render cards for Approve preview (HTML/PNG + caption)")
    try:
        paths = render_cards(briefing, cards_dir, now)
    except Exception as exc:  # noqa: BLE001
        print(f"   !! card render failed: {exc}")
        return []
    print(f"   card pngs: {len(paths)} → {cards_dir}")
    return paths


def _notify_stage(notifier: Any, message: str) -> None:
    print(message)
    try:
        notifier.send_text(message)
    except Exception as exc:  # noqa: BLE001
        print(f"   !! stage notify failed: {exc}")


def run_publish(
    briefing: dict[str, Any],
    picked: list[dict[str, Any]],
    now: datetime,
    run_dir: Path,
    store: SeenUrlsStore,
    notifier: Any,
    generation_mode: str = "llm",
    card_png_paths: list[Path] | None = None,
) -> None:
    """Approve 후: 마크다운 저장(+선택 R2/인스타) → seen_urls 기록.

    ``card_png_paths`` — draft 게이트에서 이미 렌더한 PNG. 있으면 재렌더하지 않음.
    """
    print("==> Write briefing markdown (manual paste)")
    md = assemble_blog_markdown(briefing)
    md_path = run_dir / "briefing.md"
    md_path.write_text(md, encoding="utf-8")
    (run_dir / "briefing.html").write_text(
        briefing.get("blog_html") or assemble_blog_html(briefing), encoding="utf-8"
    )
    export_ref = str(md_path.resolve())
    print(f"   wrote {md_path}")

    ig_media_id: str | None = None
    publish_cfg = PublishConfig.from_env()
    paths = list(card_png_paths or [])
    if publish_cfg.publish_cards:
        if not paths:
            print("==> Render cards (HTML/PNG + Instagram caption)")
            cards_dir = run_dir / "cards"
            cards_dir.mkdir(exist_ok=True)
            try:
                paths = render_cards(briefing, cards_dir, now)
            except Exception as exc:  # noqa: BLE001
                _notify_stage(notifier, f"[카드렌더 실패] {exc}")
                paths = []
        else:
            print(f"==> Reuse Approve-preview cards ({len(paths)} png)")

        try:
            result = PublishCardsPipeline(
                publish_cfg,
                log=lambda msg: print(f"==> {msg}"),
            ).run(
                png_paths=paths,
                briefing=briefing,
                r2_prefix=f"briefs/{now.strftime('%Y-%m-%d')}",
                run_dir=run_dir,
            )
            ig_media_id = result.ig_media_id
            if result.skipped_reason:
                _notify_stage(
                    notifier,
                    f"[카드발행 부분스킵] {result.skipped_reason}",
                )
            elif ig_media_id:
                _notify_stage(notifier, f"[인스타 게시됨] media_id={ig_media_id}")
        except Exception as exc:  # noqa: BLE001
            _notify_stage(notifier, f"[R2/인스타 실패] {exc}")

    mode_label = _generation_mode_label(generation_mode)
    caption = (
        f"[마크다운 준비됨]\n생성: {mode_label}\n{briefing.get('title')}\n"
        f"경로: {md_path}\n에디터에 붙여넣기 하세요."
    )
    if ig_media_id:
        caption += f"\nInstagram media_id: {ig_media_id}"
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


def content_retry_max() -> int:
    raw = env("CONTENT_RETRY_MAX", "3") or "3"
    try:
        return max(0, int(raw))
    except ValueError:
        return 3


def render_retry_max() -> int:
    raw = env("RENDER_RETRY_MAX", "3") or "3"
    try:
        return max(0, int(raw))
    except ValueError:
        return 3


def _serialize_articles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in a.items() if k != "published_dt"} for a in rows]


def produce_content_attempt(
    draft_store: DraftRunStore,
    candidates: list[dict[str, Any]],
    now: datetime,
    *,
    rewrite_picked: list[dict[str, Any]] | None = None,
    exclude_prior: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any], str, Path]:
    """Rank (or reuse picks) + build briefing into a new content attempt dir."""
    attempt_dir = draft_store.new_content_attempt()
    ensure_runtime_before_llm("draft")
    if rewrite_picked is not None:
        picked = list(rewrite_picked)
        print(f"==> Rewrite briefing for {len(picked)} picked articles")
    else:
        pool = (
            draft_store.exclude_prior_picks(candidates)
            if exclude_prior
            else list(candidates)
        )
        print(f"==> Ollama importance ranking (pool={len(pool)})")
        if not pool:
            raise RuntimeError("no candidates left after excluding prior picks")
        picked = rank_articles(pool, now, run_dir=attempt_dir)
    if not picked:
        raise RuntimeError("no articles after ranking")
    (attempt_dir / "ranked.json").write_text(
        json.dumps(_serialize_articles(picked), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("==> Ollama briefing")
    briefing, generation_mode = build_briefing(picked, now, run_dir=attempt_dir)
    briefing["blog_html"] = assemble_blog_html(briefing)
    (attempt_dir / "briefing.json").write_text(
        json.dumps(briefing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"   title: {briefing.get('title')} generation={generation_mode}")
    return picked, briefing, generation_mode, attempt_dir


def run_draft_two_stage(
    *,
    candidates: list[dict[str, Any]],
    now: datetime,
    run_dir: Path,
    store: SeenUrlsStore,
    notifier: Any,
    channel: str,
) -> int:
    """Content gate → render gate → publish → mandatory cleanup ask."""
    draft_store = DraftRunStore(
        run_dir,
        content_max=content_retry_max(),
        render_max=render_retry_max(),
    )
    draft_store.init_layout()

    next_content: GateAction | None = None
    picked: list[dict[str, Any]] = []
    briefing: dict[str, Any] | None = None
    generation_mode = "heuristic"
    waited_notify = False
    attempt_dir: Path | None = None

    try:
        while True:
            if next_content in {GateAction.RERANK, GateAction.REWRITE}:
                if draft_store.manifest.content_remaining <= 0:
                    notifier.send_text(exhausted_message(GateStage.CONTENT))
                    print("Done (content retries exhausted).")
                    return 0
                left = draft_store.consume_content_retry()
                notifier.send_text(
                    regenerating_ack(
                        next_content.value,
                        left,
                        draft_store.manifest.content_max,
                    )
                )

            try:
                picked, briefing, generation_mode, attempt_dir = produce_content_attempt(
                    draft_store,
                    candidates,
                    now,
                    rewrite_picked=picked if next_content == GateAction.REWRITE else None,
                    exclude_prior=next_content == GateAction.RERANK,
                )
            except Exception as exc:  # noqa: BLE001
                notifier.send_text(f"[내용 생성 실패] {exc}")
                print(f"Done (content produce failed): {exc}")
                return 1

            preview = preview_text(
                briefing,
                picked,
                generation_mode=generation_mode,
                include_approve_hints=False,
            )
            (attempt_dir / "preview.txt").write_text(preview, encoding="utf-8")

            if not waited_notify:
                wait_until_notify_send_at()
                waited_notify = True

            print(
                f"==> Content gate channel={channel} "
                f"remaining={draft_store.manifest.content_remaining}/"
                f"{draft_store.manifest.content_max}"
            )
            action = notifier.wait_for_gate(
                GateStage.CONTENT,
                preview,
                remaining=draft_store.manifest.content_remaining,
                max_retries=draft_store.manifest.content_max,
                run_id=run_dir.name,
                attempt=draft_store.manifest.current_content or "",
            )
            draft_store.record_action("content", action.value)
            if action == GateAction.APPROVE:
                draft_store.set_selected_content()
                break
            if action == GateAction.TIMEOUT:
                print("Done (content timeout). seen_urls not updated.")
                return 0
            if action in {GateAction.RERANK, GateAction.REWRITE}:
                next_content = action
                continue
            print(f"Done (unexpected content action={action}).")
            return 0
    finally:
        release_ollama_only()

    assert briefing is not None

    notifier.send_text(
        render_stage_start_ack(
            run_id=run_dir.name,
            content_attempt=draft_store.manifest.selected_content or "",
        )
    )

    next_render: GateAction | None = None
    card_pngs: list[Path] = []
    ensure_aux_before_publish()
    try:
        while True:
            if next_render == GateAction.RERENDER:
                if draft_store.manifest.render_remaining <= 0:
                    notifier.send_text(exhausted_message(GateStage.RENDER))
                    print("Done (render retries exhausted).")
                    return 0
                left = draft_store.consume_render_retry()
                notifier.send_text(
                    regenerating_ack(
                        "rerender",
                        left,
                        draft_store.manifest.render_max,
                    )
                )

            render_dir = draft_store.new_render_attempt()
            card_pngs = render_cards_for_approve(briefing, render_dir, now)

            preview = preview_text(
                briefing,
                picked,
                generation_mode=generation_mode,
                has_card_images=bool(card_pngs),
                include_approve_hints=False,
            )
            print(
                f"==> Render gate channel={channel} images={len(card_pngs)} "
                f"remaining={draft_store.manifest.render_remaining}/"
                f"{draft_store.manifest.render_max}"
            )
            action = notifier.wait_for_gate(
                GateStage.RENDER,
                preview,
                image_paths=card_pngs,
                remaining=draft_store.manifest.render_remaining,
                max_retries=draft_store.manifest.render_max,
                run_id=run_dir.name,
                attempt=draft_store.manifest.current_render or "",
            )
            draft_store.record_action("render", action.value)
            if action == GateAction.APPROVE:
                break
            if action == GateAction.TIMEOUT:
                print("Done (render timeout). seen_urls not updated.")
                return 0
            if action == GateAction.RERENDER:
                next_render = GateAction.RERENDER
                continue
            print(f"Done (unexpected render action={action}).")
            return 0
    finally:
        release_aux_only()

    ensure_aux_before_publish()
    store.reopen()
    run_publish(
        briefing,
        picked,
        now,
        run_dir,
        store,
        notifier,
        generation_mode=generation_mode,
        card_png_paths=card_pngs,
    )
    draft_store.copy_into_final(
        briefing=briefing,
        md_path=run_dir / "briefing.md",
        html_path=run_dir / "briefing.html",
        card_pngs=card_pngs,
    )

    selected_label = (
        f"{draft_store.manifest.selected_content}+{draft_store.manifest.current_render}"
    )
    cleanup_body = cleanup_prompt(
        selected_label=selected_label,
        unselected=draft_store.unselected_labels(),
        run_id=run_dir.name,
    )
    print("==> Cleanup ask")
    cleanup_action = notifier.wait_for_gate(
        GateStage.CLEANUP,
        cleanup_body,
        run_id=run_dir.name,
    )
    if cleanup_action == GateAction.KEEP_ALL:
        draft_store.cleanup_keep_all()
        notifier.send_text("클린업: 전부 보관했습니다.")
    else:
        deleted = draft_store.cleanup_keep_final()
        if cleanup_action == GateAction.TIMEOUT:
            notifier.send_text(cleanup_timeout_notice(deleted))
        else:
            notifier.send_text(
                "클린업: 확정본만 유지했습니다."
                + (f" 삭제={', '.join(deleted)}" if deleted else "")
            )
    return 0


def main() -> int:
    mode = env("MVP_MODE", "dry_run").lower()
    now = datetime.now(TZ)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    run_dir = OUTPUT / now.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    ensure_runtime_before_llm(mode)

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
    try:
        print("==> fetching Google News RSS")
        candidates = fetch_candidates(now)
        candidates = store.filter_new(candidates)
        print(f"   candidates in window (capped, after seen_urls): {len(candidates)}")
        (run_dir / "candidates.json").write_text(
            json.dumps(
                _serialize_articles(candidates),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if not candidates:
            print("No candidates in news window. Exit.")
            if mode in {"draft", "publish"}:
                notifier.send_text(f"[경제브리핑] {now.date()} 창 내 후보 0건 — 스킵")
            return 0

        if mode == "draft":
            return run_draft_two_stage(
                candidates=candidates,
                now=now,
                run_dir=run_dir,
                store=store,
                notifier=notifier,
                channel=channel,
            )

        briefing: dict[str, Any] | None = None
        generation_mode = "heuristic"
        picked: list[dict[str, Any]] = []
        try:
            print("==> Ollama importance ranking")
            picked = rank_articles(candidates, now, run_dir=run_dir)
            print(f"   picked: {len(picked)}")
            (run_dir / "ranked.json").write_text(
                json.dumps(
                    _serialize_articles(picked),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            if not picked:
                print("No articles after ranking. Exit.")
                return 1

            print("==> Ollama briefing")
            briefing, generation_mode = build_briefing(picked, now, run_dir=run_dir)
            briefing["blog_html"] = assemble_blog_html(briefing)
            (run_dir / "briefing.json").write_text(
                json.dumps(briefing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"   title: {briefing.get('title')}")
            print(f"   generation: {generation_mode}")
            print(f"   wrote {run_dir}")
        finally:
            release_ollama_after_llm()

        if briefing is None:
            return 1

        if mode == "dry_run":
            # Also mirror one content attempt for debugging layout compatibility.
            draft_store = DraftRunStore(
                run_dir,
                content_max=content_retry_max(),
                render_max=render_retry_max(),
            )
            draft_store.init_layout()
            attempt_dir = draft_store.new_content_attempt()
            for name in ("ranked.json", "briefing.json", "story_raw.json", "importance_raw.json"):
                src = run_dir / name
                if src.is_file():
                    (attempt_dir / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            draft_store.set_selected_content()
            print("Done (dry_run). Set MVP_MODE=draft for Approve→markdown, or publish to export.md.")
            return 0

        if mode == "publish":
            ensure_aux_before_publish()
            store.reopen()
            card_pngs = render_cards_for_approve(briefing, run_dir, now)
            run_publish(
                briefing,
                picked,
                now,
                run_dir,
                store,
                notifier,
                generation_mode=generation_mode,
                card_png_paths=card_pngs,
            )
            return 0

        print(f"Unknown MVP_MODE={mode}", file=sys.stderr)
        return 1
    finally:
        store.close()
        release_ollama_after_llm()


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
