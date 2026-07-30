"""Load/save ops console settings (schedule, RSS feeds, card bundle)."""

from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPS_PATH = ROOT / "config" / "ops.json"
EXAMPLE_OPS_PATH = ROOT / "config" / "ops.example.json"
LAST_RUN_PATH = ROOT / "output" / ".ops_last_run"

_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

DEFAULT_FEEDS: list[dict[str, str]] = [
    {
        "label": "BUSINESS",
        "url": (
            "https://news.google.com/rss/headlines/section/topic/BUSINESS"
            "?hl=ko&gl=KR&ceid=KR:ko"
        ),
    },
    {
        "label": "NATION",
        "url": (
            "https://news.google.com/rss/headlines/section/topic/NATION"
            "?hl=ko&gl=KR&ceid=KR:ko"
        ),
    },
]

DEFAULT_OPS: dict[str, Any] = {
    "timezone": "Asia/Seoul",
    "schedule": {
        "weekdays": [1, 2, 3, 4, 5],
        "run_at": "07:00",
        "notify_at": "07:50",
    },
    "feeds": deepcopy(DEFAULT_FEEDS),
    "cards": {"bundle_id": "daily_briefing"},
}


def ops_path() -> Path:
    raw = (os.getenv("OPS_CONFIG_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_OPS_PATH


def _parse_hhmm(raw: str, *, field: str) -> tuple[int, int]:
    text = (raw or "").strip()
    m = _HHMM_RE.fullmatch(text)
    if not m:
        raise ValueError(f"{field} must be HH:MM, got {raw!r}")
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"{field} out of range: {raw!r}")
    return hour, minute


def normalize_ops(data: dict[str, Any] | None) -> dict[str, Any]:
    """Return a validated ops dict with defaults filled in."""
    src = data if isinstance(data, dict) else {}
    out = deepcopy(DEFAULT_OPS)

    tz = str(src.get("timezone") or out["timezone"]).strip() or "Asia/Seoul"
    out["timezone"] = tz

    schedule_in = src.get("schedule") if isinstance(src.get("schedule"), dict) else {}
    weekdays = schedule_in.get("weekdays", out["schedule"]["weekdays"])
    if not isinstance(weekdays, list) or not weekdays:
        weekdays = list(out["schedule"]["weekdays"])
    cleaned_days: list[int] = []
    for d in weekdays:
        try:
            n = int(d)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 7 and n not in cleaned_days:
            cleaned_days.append(n)
    if not cleaned_days:
        cleaned_days = list(out["schedule"]["weekdays"])

    run_at = str(schedule_in.get("run_at") or out["schedule"]["run_at"]).strip()
    notify_at = str(schedule_in.get("notify_at") or out["schedule"]["notify_at"]).strip()
    rh, rm = _parse_hhmm(run_at, field="run_at")
    nh, nm = _parse_hhmm(notify_at, field="notify_at")
    out["schedule"] = {
        "weekdays": cleaned_days,
        "run_at": f"{rh:02d}:{rm:02d}",
        "notify_at": f"{nh:02d}:{nm:02d}",
    }

    feeds_in = src.get("feeds")
    feeds: list[dict[str, str]] = []
    if isinstance(feeds_in, list):
        for row in feeds_in:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            label = str(row.get("label") or "FEED").strip() or "FEED"
            feeds.append({"label": label, "url": url})
    out["feeds"] = feeds if feeds else deepcopy(DEFAULT_FEEDS)

    cards_in = src.get("cards") if isinstance(src.get("cards"), dict) else {}
    bundle_id = str(cards_in.get("bundle_id") or out["cards"]["bundle_id"]).strip()
    out["cards"] = {"bundle_id": bundle_id or "daily_briefing"}
    return out


def load_ops_config(path: Path | None = None) -> dict[str, Any]:
    target = path or ops_path()
    if not target.is_file():
        return deepcopy(DEFAULT_OPS)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_OPS)
    if not isinstance(raw, dict):
        return deepcopy(DEFAULT_OPS)
    try:
        return normalize_ops(raw)
    except ValueError:
        return deepcopy(DEFAULT_OPS)


def save_ops_config(data: dict[str, Any], path: Path | None = None) -> Path:
    target = path or ops_path()
    normalized = normalize_ops(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            temp_path = Path(fh.name)
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, target)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return target


def ensure_ops_config(path: Path | None = None) -> dict[str, Any]:
    """Load ops.json, or seed from example/defaults and save."""
    target = path or ops_path()
    if target.is_file():
        return load_ops_config(target)
    if EXAMPLE_OPS_PATH.is_file():
        try:
            raw = json.loads(EXAMPLE_OPS_PATH.read_text(encoding="utf-8"))
            data = normalize_ops(raw if isinstance(raw, dict) else {})
        except (OSError, json.JSONDecodeError, ValueError):
            data = deepcopy(DEFAULT_OPS)
    else:
        data = deepcopy(DEFAULT_OPS)
    save_ops_config(data, target)
    return data


def resolve_notify_at(ops: dict[str, Any] | None = None) -> str:
    """NOTIFY_SEND_AT env wins; else ops schedule.notify_at."""
    env_val = (os.getenv("NOTIFY_SEND_AT") or "").strip()
    if env_val:
        return env_val
    cfg = ops if ops is not None else load_ops_config()
    return str(cfg.get("schedule", {}).get("notify_at") or "07:50")


def resolve_feeds(ops: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    """Return (label, url) pairs.

    Non-empty GNEWS_* env values take precedence over ops.json feeds.
    When either is set, the unset counterpart uses its built-in default.
    """
    business_env = (os.getenv("GNEWS_BUSINESS_RSS") or "").strip()
    nation_env = (os.getenv("GNEWS_NATION_RSS") or "").strip()
    if business_env or nation_env:
        business = business_env or DEFAULT_FEEDS[0]["url"]
        nation = nation_env or DEFAULT_FEEDS[1]["url"]
        return [("BUSINESS", business), ("NATION", nation)]

    cfg = ops if ops is not None else load_ops_config()
    feeds = cfg.get("feeds") or []
    out: list[tuple[str, str]] = []
    if isinstance(feeds, list):
        for row in feeds:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            label = str(row.get("label") or "FEED").strip() or "FEED"
            out.append((label, url))
    if out:
        return out

    business = (os.getenv("GNEWS_BUSINESS_RSS") or "").strip() or DEFAULT_FEEDS[0]["url"]
    nation = (os.getenv("GNEWS_NATION_RSS") or "").strip() or DEFAULT_FEEDS[1]["url"]
    return [("BUSINESS", business), ("NATION", nation)]


def resolve_bundle_id(ops: dict[str, Any] | None = None) -> str:
    env_val = (os.getenv("CARD_BUNDLE_ID") or "").strip()
    if env_val:
        return env_val
    cfg = ops if ops is not None else load_ops_config()
    return str(cfg.get("cards", {}).get("bundle_id") or "daily_briefing")


def last_run_path() -> Path:
    raw = (os.getenv("OPS_LAST_RUN_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return LAST_RUN_PATH


def read_last_run_date(path: Path | None = None) -> str | None:
    target = path or last_run_path()
    if not target.is_file():
        return None
    try:
        text = target.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def write_last_run_date(day: str | None = None, path: Path | None = None) -> None:
    target = path or last_run_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if day is not None:
        stamp = day
    else:
        cfg = load_ops_config()
        tz_name = str(cfg.get("timezone") or "Asia/Seoul")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("Asia/Seoul")
        stamp = datetime.now(tz).date().isoformat()
    target.write_text(stamp + "\n", encoding="utf-8")


def _should_run_details(
    now: datetime | None = None,
    *,
    ops: dict[str, Any] | None = None,
    last_run: str | None = None,
    window_minutes: int = 5,
) -> tuple[bool, str, str | None]:
    """Return whether to run, the reason, and the matched scheduled date.

    Matches configured weekday + run_at within [run_at, run_at+window_minutes).
    Cross-midnight windows retain the scheduled local date for duplicate checks.
    """
    cfg = ops if ops is not None else load_ops_config()
    tz_name = str(cfg.get("timezone") or "Asia/Seoul")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("Asia/Seoul")
    clock = (now or datetime.now(tz)).astimezone(tz)

    schedule = cfg.get("schedule") or {}
    weekdays = schedule.get("weekdays") or [1, 2, 3, 4, 5]
    try:
        days = {int(d) for d in weekdays}
    except (TypeError, ValueError):
        days = {1, 2, 3, 4, 5}
    try:
        hour, minute = _parse_hhmm(str(schedule.get("run_at") or "07:00"), field="run_at")
    except ValueError as exc:
        return False, str(exc), None

    window = timedelta(minutes=max(1, window_minutes))
    scheduled_date = None
    matched_weekday: int | None = None
    for candidate_date in (clock.date(), clock.date() - timedelta(days=1)):
        scheduled = datetime(
            candidate_date.year,
            candidate_date.month,
            candidate_date.day,
            hour,
            minute,
            tzinfo=tz,
        )
        if scheduled <= clock < scheduled + window:
            matched_weekday = candidate_date.isoweekday()
            if matched_weekday in days:
                scheduled_date = candidate_date
                break

    if scheduled_date is None:
        if matched_weekday is not None:
            return False, f"weekday {matched_weekday} not in {sorted(days)}", None
        return (
            False,
            f"outside run window {hour:02d}:{minute:02d}"
            f"+{window_minutes}m (now {clock.strftime('%H:%M')})",
            None,
        )

    scheduled_day = scheduled_date.isoformat()
    stamp = last_run if last_run is not None else read_last_run_date()
    if stamp == scheduled_day:
        return False, f"already ran scheduled date ({scheduled_day})", scheduled_day
    return True, "ok", scheduled_day


def should_run_now(
    now: datetime | None = None,
    *,
    ops: dict[str, Any] | None = None,
    last_run: str | None = None,
    window_minutes: int = 5,
) -> tuple[bool, str]:
    """Whether cron should start a draft run."""
    ok, reason, _scheduled_day = _should_run_details(
        now,
        ops=ops,
        last_run=last_run,
        window_minutes=window_minutes,
    )
    return ok, reason


def main_should_run(*, scheduled_day_only: bool = False) -> int:
    """CLI for cron_run_draft.sh — exit 0 run, 1 skip."""
    ok, reason, scheduled_day = _should_run_details()
    if ok:
        if scheduled_day_only:
            print(scheduled_day)
        else:
            print(f"==> ops schedule: run ({reason}, scheduled date {scheduled_day})")
        return 0
    if not scheduled_day_only:
        print(f"==> ops schedule: skip ({reason})")
    return 1


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--mark-run":
        scheduled_day = sys.argv[2] if len(sys.argv) > 2 else None
        write_last_run_date(day=scheduled_day)
        print(f"==> ops last_run stamped → {last_run_path()}")
        raise SystemExit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--scheduled-day":
        raise SystemExit(main_should_run(scheduled_day_only=True))
    raise SystemExit(main_should_run())
