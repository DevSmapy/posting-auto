"""Read-only dashboard state from run JSON / lock, plus fail-safe emit."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ENV_DIR = "POSTING_MONITOR_DIR"
MONITOR_NAME = "monitor.json"
_RUN_DIR_RE = re.compile(r"^\d{8}_\d{6}$")
_RUNTIME_TTL_SEC = 15.0
_runtime_cache: tuple[float, list[dict[str, str]]] = (0.0, [])
_STALE_SEC = {"RANK": 300, "WRITE": 900, "REVIEW": 1200, "PUBLISH": 600}
_HANG_SEC = {"RANK": 600, "WRITE": 1800, "REVIEW": 2400, "PUBLISH": 1800}
_PUBLISH_ARTIFACTS = (
    "monitor.json",
    "briefing.md",
    "publish_guard.json",
    "image_urls.json",
    "creation_id.json",
    "publish_result.json",
    "website_result.json",
)

TZ = ZoneInfo(os.getenv("NEWS_TIMEZONE", "Asia/Seoul"))


def output_dir() -> Path:
    raw = os.getenv("OUTPUT_DIR", str(ROOT / "output")).strip()
    path = Path(raw)
    return path if path.is_absolute() else (ROOT / path).resolve()


def lock_path() -> Path:
    from runtime.run_lock import DEFAULT_LOCK_PATH

    return DEFAULT_LOCK_PATH


def set_run_dir(path: Path | str | None) -> None:
    if path is None:
        os.environ.pop(ENV_DIR, None)
        return
    os.environ[ENV_DIR] = str(path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path | None) -> Any:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _monitor_file(run_dir: Path | None) -> Path | None:
    if run_dir is None:
        return None
    return Path(run_dir) / MONITOR_NAME


def _run_dir_from_env() -> Path | None:
    raw = os.getenv(ENV_DIR, "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def emit(*, run_dir: Path | str | None = None, event: Any = None, **patch: Any) -> None:
    """Merge fields into monitor.json. Never raises."""
    try:
        base = Path(run_dir) if run_dir is not None else _run_dir_from_env()
        path = _monitor_file(base)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        current = _read_json(path)
        if not isinstance(current, dict):
            current = {}
        if "llm" in patch and isinstance(patch["llm"], dict):
            llm = dict(current.get("llm") or {}) if isinstance(current.get("llm"), dict) else {}
            llm.update(patch["llm"])
            patch = {**patch, "llm": llm}
        events = list(current.get("events") or [])
        current.update(patch)
        if event is not None:
            row = event if isinstance(event, dict) else {"message": str(event)}
            row.setdefault("timestamp", _now_iso())
            events.append(row)
            current["events"] = events[-5:]
        fd, tmp_name = tempfile.mkstemp(prefix="monitor.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(current, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            Path(tmp_name).replace(path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except Exception:  # noqa: BLE001
        return


def llm_begin(role: str = "llm") -> None:
    emit(
        llm={
            "in_flight": True,
            "role": role or "llm",
            "started_at": _now_iso(),
            "model": os.getenv("OLLAMA_MODEL", "").strip(),
        }
    )


def llm_end(*, ok: bool = True) -> None:
    try:
        data = _read_json(_monitor_file(_run_dir_from_env()))
        llm = dict(data.get("llm") or {}) if isinstance(data, dict) else {}
        calls = int(llm.get("calls") or 0) + 1
        failures = int(llm.get("failures") or 0) + (0 if ok else 1)
        emit(
            llm={
                "in_flight": False,
                "role": None,
                "started_at": None,
                "calls": calls,
                "failures": failures,
            }
        )
    except Exception:  # noqa: BLE001
        return


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock(path: Path) -> dict[str, Any] | None:
    data = _read_json(path)
    if not isinstance(data, dict):
        return None
    try:
        pid = int(data.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    return {
        "present": True,
        "pid": pid,
        "pid_alive": _pid_alive(pid),
        "started_at": data.get("started_at"),
        "run_id": data.get("run_id"),
    }


def _run_dirs(out: Path) -> list[Path]:
    if not out.is_dir():
        return []
    dirs = [p for p in out.iterdir() if p.is_dir() and _RUN_DIR_RE.match(p.name)]
    dirs.sort(key=lambda p: p.name, reverse=True)
    return dirs


def _attempt_dir(run_dir: Path) -> Path:
    attempts = run_dir / "attempts"
    manifest = _read_json(run_dir / "manifest.json")
    if isinstance(manifest, dict):
        for key in ("current_content", "selected_content"):
            name = manifest.get(key)
            if name:
                cand = attempts / str(name)
                if cand.is_dir():
                    return cand
    if attempts.is_dir():
        kids = sorted([p for p in attempts.iterdir() if p.is_dir()], key=lambda p: p.name)
        if kids:
            return kids[-1]
    return run_dir


def _find(run_dir: Path, name: str) -> Path | None:
    for base in (_attempt_dir(run_dir), run_dir):
        path = base / name
        if path.is_file():
            return path
    return None


def _len_payload(data: Any, *, key: str | None = None) -> int | None:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and key:
        rows = data.get(key)
        if isinstance(rows, list):
            return len(rows)
    return None


def probe_runtime(*, force: bool = False) -> list[dict[str, str]]:
    global _runtime_cache
    now = time.monotonic()
    cached_at, cached = _runtime_cache
    if not force and cached and now - cached_at < _RUNTIME_TTL_SEC:
        return cached
    rows: list[dict[str, str]] = []
    try:
        from runtime.preflight import check_network, check_ollama

        net = check_network()
        oll = check_ollama()
        rows = [
            {"name": "Network", "status": "healthy" if net.get("ok") else "unavailable"},
            {"name": "Ollama", "status": "healthy" if oll.get("ok") else "unavailable"},
        ]
    except Exception:  # noqa: BLE001
        rows = [
            {"name": "Network", "status": "unknown"},
            {"name": "Ollama", "status": "unknown"},
        ]
    _runtime_cache = (now, rows)
    return rows


def reset_runtime_cache() -> None:
    global _runtime_cache
    _runtime_cache = (0.0, [])


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _elapsed_sec(started: datetime | None, now: datetime) -> float | None:
    if started is None:
        return None
    return max(0.0, (now - started).total_seconds())


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _last_artifact_mtime(run_dir: Path | None) -> float | None:
    if run_dir is None:
        return None
    times: list[float] = []
    for name in _PUBLISH_ARTIFACTS:
        stamp = _mtime(run_dir / name)
        if stamp is not None:
            times.append(stamp)
    cards = run_dir / "cards"
    if cards.is_dir():
        for png in cards.glob("*.png"):
            stamp = _mtime(png)
            if stamp is not None:
                times.append(stamp)
    return max(times) if times else None


def _last_event_dt(events: list[Any]) -> datetime | None:
    if not events:
        return None
    last = events[-1]
    if isinstance(last, dict):
        return _parse_dt(last.get("timestamp"))
    return None


def _stale_thresholds(stage: str) -> tuple[int, int]:
    key = (stage or "").upper()
    stale = _STALE_SEC.get(key, 600)
    hang = _HANG_SEC.get(key, stale * 2)
    raw = os.getenv("DASHBOARD_STALE_SEC", "").strip()
    if raw and key not in _STALE_SEC:
        try:
            stale = max(60, int(raw))
            hang = stale * 2
        except ValueError:
            pass
    return stale, hang


def _stale_level(age: float | None, stage: str) -> str:
    if age is None:
        return ""
    stale, hang = _stale_thresholds(stage)
    if age >= hang:
        return "hang"
    if age >= stale:
        return "stale"
    return ""


def _ops_run_at() -> str:
    try:
        from ops_config import load_ops_config

        ops = load_ops_config()
        value = str((ops.get("schedule") or {}).get("run_at") or "").strip()
        return value or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _story_rows(
    briefing: dict[str, Any] | None,
    editorial: dict[str, Any] | None,
    monitor: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if isinstance(monitor, dict) and isinstance(monitor.get("stories"), list) and monitor["stories"]:
        rows = []
        for item in monitor["stories"]:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "index": item.get("index"),
                    "headline": str(item.get("headline") or ""),
                    "status": str(item.get("status") or item.get("decision") or ""),
                }
            )
        if rows:
            return rows
    headlines: list[str] = []
    if isinstance(briefing, dict):
        for i, story in enumerate(briefing.get("stories") or []):
            if isinstance(story, dict):
                headlines.append(str(story.get("headline") or ""))
            else:
                headlines.append("")
    review_map: dict[int, str] = {}
    excluded: set[int] = set()
    if isinstance(editorial, dict):
        for item in (editorial.get("review") or {}).get("stories") or []:
            if isinstance(item, dict) and "index" in item:
                try:
                    review_map[int(item["index"])] = str(item.get("decision") or "")
                except (TypeError, ValueError):
                    continue
        decision = editorial.get("editor_decision") or {}
        for idx in decision.get("excluded_story_ids") or []:
            try:
                excluded.add(int(idx))
            except (TypeError, ValueError):
                continue
    if not headlines and not review_map:
        return []
    n = max(len(headlines), max(review_map, default=-1) + 1)
    rows = []
    for i in range(n):
        status = review_map.get(i, "")
        if i in excluded:
            status = "excluded"
        rows.append({"index": i, "headline": headlines[i] if i < len(headlines) else "", "status": status})
    return rows


def _publish_rows(run_dir: Path, *, running: bool) -> list[dict[str, Any]]:
    md = (run_dir / "briefing.md").is_file()
    result = _read_json(run_dir / "publish_result.json")
    guard = _read_json(run_dir / "publish_guard.json")
    site = _read_json(run_dir / "website_result.json")
    ig_id = None
    if isinstance(result, dict):
        ig_id = result.get("ig_media_id")
    md_status = "success" if md else ("pending" if running else "skipped")
    if ig_id:
        ig_status = "success"
    elif isinstance(guard, dict) and guard.get("ok") is False:
        ig_status = "failed"
    elif running:
        ig_status = "pending"
    else:
        ig_status = "paused"
    if isinstance(site, dict):
        site_status = str(site.get("status") or "skipped")
        if site_status == "dry_run":
            site_status = "success"
        site_id = site.get("url")
    elif running:
        site_status = "pending"
        site_id = None
    else:
        site_status = "skipped"
        site_id = None
    return [
        {"channel": "Website", "status": site_status, "id": site_id},
        {"channel": "Markdown", "status": md_status, "id": None},
        {"channel": "Instagram", "status": ig_status, "id": ig_id},
        {"channel": "Tistory", "status": "skipped", "id": None},
    ]


def _publish_steps(run_dir: Path, *, running: bool) -> list[dict[str, Any]]:
    pngs = list((run_dir / "cards").glob("*.png")) if (run_dir / "cards").is_dir() else []
    guard = _read_json(run_dir / "publish_guard.json")
    guard_failed = isinstance(guard, dict) and guard.get("ok") is False
    site = _read_json(run_dir / "website_result.json")
    site_done = isinstance(site, dict) and site.get("status") in {"success", "dry_run"}
    site_failed = isinstance(site, dict) and site.get("status") == "failed"
    site_skipped = isinstance(site, dict) and site.get("status") == "skipped"
    checks = [
        ("MD", (run_dir / "briefing.md").is_file()),
        ("Cards", bool(pngs)),
        ("Guard", (run_dir / "publish_guard.json").is_file()),
        ("R2", (run_dir / "image_urls.json").is_file()),
        ("IG", (run_dir / "publish_result.json").is_file()),
        ("Website", site_done),
    ]
    rows: list[dict[str, Any]] = []
    saw_running = False
    for name, done in checks:
        status = "pending"
        if name == "Guard" and guard_failed:
            status = "failed"
        elif name == "Website" and site_failed:
            status = "failed"
        elif name == "Website" and site_skipped:
            status = "skipped"
        elif done:
            status = "success"
        elif running and not saw_running:
            status = "running"
            saw_running = True
        extra = len(pngs) if name == "Cards" and pngs else None
        rows.append({"name": name, "status": status, "count": extra})
    return rows


def _pipeline(
    run_dir: Path | None,
    monitor: dict[str, Any] | None,
    *,
    running: bool,
) -> tuple[str, list[dict[str, Any]]]:
    files = {
        "Collect": ("candidates.json", None),
        "Rank": ("ranked.json", None),
        "Write": ("briefing.json", "stories"),
        "Review": ("editorial_result.json", None),
        "Publish": ("briefing.md", None),
    }
    live_stage = str((monitor or {}).get("stage") or "").upper()
    stage_map = {
        "COLLECT": "Collect",
        "RANK": "Rank",
        "WRITE": "Write",
        "REVIEW": "Review",
        "REVISE": "Review",
        "EDITOR": "Review",
        "PUBLISH": "Publish",
        "COMPLETE": "",
        "FAILED": "",
    }
    current_name = stage_map.get(live_stage, "")
    rows: list[dict[str, Any]] = []
    saw_running = False
    for name, (fname, count_key) in files.items():
        path = _find(run_dir, fname) if run_dir else None
        exists = path is not None
        count = None
        if exists and fname.endswith(".json"):
            count = _len_payload(_read_json(path), key=count_key)
        if name == "Review" and isinstance(monitor, dict) and monitor.get("review_overall"):
            exists = True
        status = "pending"
        if exists:
            status = "success"
        if running and current_name == name and not saw_running:
            status = "running"
            saw_running = True
        if live_stage == "REVISE" and name == "Review":
            status = "running" if running else status
        rows.append({"name": name, "status": status, "count": count})
    current = current_name or next((r["name"] for r in rows if r["status"] == "running"), "")
    if not current:
        for row in reversed(rows):
            if row["status"] == "success":
                current = row["name"]
                break
    return current, rows


def _fail_reason(run_dir: Path | None, editorial: Any, monitor: dict[str, Any] | None) -> str:
    if run_dir is not None:
        pre = _read_json(run_dir / "preflight.json")
        if isinstance(pre, dict) and pre.get("ok") is False:
            return "preflight failed"
        guard = _read_json(run_dir / "publish_guard.json")
        if isinstance(guard, dict) and guard.get("ok") is False:
            blockers = guard.get("blockers") or []
            return "publish_guard: " + ", ".join(str(b) for b in blockers[:4])
        site = _read_json(run_dir / "website_result.json")
        if isinstance(site, dict) and site.get("status") == "failed":
            return "website: " + str(site.get("error_type") or site.get("detail") or "failed")
        manifest = _read_json(run_dir / "manifest.json")
        if isinstance(manifest, dict) and manifest.get("status") == "parked":
            return f"parked:{manifest.get('parked_stage') or '?'}"
    if isinstance(editorial, dict):
        decision = editorial.get("editor_decision") or {}
        if decision.get("decision") == "reject":
            return str(decision.get("reason") or "editorial_reject")
    if isinstance(monitor, dict) and monitor.get("reason"):
        return str(monitor.get("reason"))
    return ""


def _draft_mode(monitor: dict[str, Any] | None) -> bool:
    mode = str((monitor or {}).get("mode") or os.getenv("MVP_MODE") or "").strip().lower()
    return mode == "draft"


def _classify(
    *,
    lock: dict[str, Any] | None,
    run_dir: Path | None,
    monitor: dict[str, Any] | None,
    editorial: Any,
) -> str:
    reason = _fail_reason(run_dir, editorial, monitor)
    live = bool(lock and lock.get("pid_alive"))
    if live:
        if reason:
            return "FAILED"
        return "RUNNING"
    ended = bool(isinstance(monitor, dict) and monitor.get("ended"))
    dead = bool(lock and lock.get("present") and not lock.get("pid_alive"))
    if dead and not ended:
        return "FAILED"
    if not ended and monitor:
        if reason:
            return "FAILED"
        if _draft_mode(monitor):
            return "RUNNING"
        return "FAILED"
    if reason:
        return "FAILED"
    if isinstance(monitor, dict) and monitor.get("ended") and monitor.get("ok") is False:
        return "FAILED"
    if run_dir is None:
        return "IDLE"
    has_artifact = any(
        _find(run_dir, name) is not None
        for name in ("candidates.json", "briefing.json", "editorial_result.json", "briefing.md")
    )
    if has_artifact or ended:
        return "COMPLETE"
    manifest = _read_json(run_dir / "manifest.json")
    if isinstance(manifest, dict) and manifest.get("status") == "active":
        return "RUNNING"
    if (run_dir / MONITOR_NAME).is_file() and not ended:
        return "RUNNING"
    return "IDLE" if not has_artifact else "COMPLETE"


def resolve_run_dir(
    *,
    output: Path | None = None,
    lock: dict[str, Any] | None = None,
) -> Path | None:
    out = output if output is not None else output_dir()
    if lock and lock.get("run_id"):
        cand = out / str(lock["run_id"])
        if cand.is_dir():
            return cand
    env_dir = _run_dir_from_env()
    if env_dir is not None:
        return env_dir
    dirs = _run_dirs(out)
    return dirs[0] if dirs else None


def read_state(
    *,
    output: Path | None = None,
    lock_file: Path | None = None,
    probe: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Normalize disk artifacts into one dashboard dict. Never raises."""
    clock = now or datetime.now(TZ)
    out = output if output is not None else output_dir()
    try:
        lock = _read_lock(lock_file if lock_file is not None else lock_path())
    except Exception:  # noqa: BLE001
        lock = None
    try:
        run_dir = resolve_run_dir(output=out, lock=lock)
    except Exception:  # noqa: BLE001
        run_dir = None
    monitor = _read_json(_monitor_file(run_dir)) if run_dir else None
    if not isinstance(monitor, dict):
        monitor = None
    briefing = _read_json(_find(run_dir, "briefing.json")) if run_dir else None
    if not isinstance(briefing, dict):
        briefing = None
    editorial = _read_json(_find(run_dir, "editorial_result.json")) if run_dir else None
    if not isinstance(editorial, dict):
        editorial = None

    status = _classify(lock=lock, run_dir=run_dir, monitor=monitor, editorial=editorial)
    running = status == "RUNNING"
    ended = bool(isinstance(monitor, dict) and monitor.get("ended"))
    fail_reason = _fail_reason(run_dir, editorial, monitor) if status == "FAILED" else ""
    if status == "FAILED" and not fail_reason and not ended:
        fail_reason = (
            "ended missing (pid dead)"
            if lock and not lock.get("pid_alive")
            else "ended missing (no live lock)"
        )
    started = _parse_dt((lock or {}).get("started_at") or (monitor or {}).get("started_at"))
    if started is None and run_dir is not None and run_dir.exists():
        started = datetime.fromtimestamp(run_dir.stat().st_ctime, tz=TZ)
    mode = str((monitor or {}).get("mode") or os.getenv("MVP_MODE") or "").strip()
    run_id = str((lock or {}).get("run_id") or (monitor or {}).get("run_id") or (run_dir.name if run_dir else ""))
    stage, pipeline = _pipeline(run_dir, monitor, running=running)
    stories = _story_rows(briefing, editorial, monitor)
    llm = dict((monitor or {}).get("llm") or {}) if isinstance((monitor or {}).get("llm"), dict) else {}
    if not llm.get("model"):
        llm["model"] = os.getenv("OLLAMA_MODEL", "").strip()
    if llm.get("in_flight") and llm.get("started_at"):
        began = _parse_dt(llm.get("started_at"))
        llm["duration_sec"] = round(_elapsed_sec(began, clock) or 0.0, 1)
    else:
        llm.pop("duration_sec", None)
        if not llm.get("in_flight"):
            llm["role"] = llm.get("role") or None
    events = list((monitor or {}).get("events") or []) if monitor else []
    revision_count = (monitor or {}).get("revision_count")
    if revision_count is None and editorial:
        revision_count = editorial.get("revision_count")

    event_age = _elapsed_sec(_last_event_dt(events), clock)
    artifact_mtime = _last_artifact_mtime(run_dir)
    artifact_age = (
        max(0.0, clock.timestamp() - artifact_mtime) if artifact_mtime is not None else None
    )
    ages = [a for a in (event_age, artifact_age) if a is not None]
    activity_age = min(ages) if ages else None
    live_stage = str((monitor or {}).get("stage") or "")
    stale_level = _stale_level(activity_age, live_stage) if running else ""

    runtime = probe_runtime() if probe else list(_runtime_cache[1])

    return {
        "status": status,
        "run_id": run_id,
        "mode": mode,
        "started_at": started.isoformat() if started else "",
        "elapsed_sec": _elapsed_sec(started, clock) if status == "RUNNING" and started else None,
        "pipeline_stage": stage,
        "pipeline": pipeline,
        "runtime": runtime,
        "stories": stories,
        "llm": llm,
        "publish": _publish_rows(run_dir, running=running) if run_dir else [],
        "publish_steps": _publish_steps(run_dir, running=running) if run_dir else [],
        "events": events,
        "revision_count": revision_count,
        "review_overall": (monitor or {}).get("review_overall")
        or ((editorial or {}).get("review") or {}).get("overall"),
        "run_at": _ops_run_at(),
        "failure_reason": fail_reason,
        "run_dir": str(run_dir) if run_dir else "",
        "clock": clock.strftime("%H:%M:%S %Z"),
        "lock": lock or {},
        "last_event_age_sec": event_age,
        "last_artifact_age_sec": artifact_age,
        "activity_age_sec": activity_age,
        "stale_level": stale_level,
    }
