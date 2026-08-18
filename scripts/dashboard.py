#!/usr/bin/env python3
"""Read-only Terminal Monitoring Dashboard.

Run:
  uv run python scripts/dashboard.py
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(ROOT / ".env")

from monitor import read_state  # noqa: E402
from rich.console import Console, Group  # noqa: E402
from rich.live import Live  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402

TZ = ZoneInfo(os.getenv("NEWS_TIMEZONE", "Asia/Seoul"))


def _sym(status: str) -> str:
    key = (status or "").strip().lower()
    if key in {"success", "pass", "healthy", "complete"}:
        return "✓"
    if key in {"running", "review"}:
        return "→"
    if key in {"revise", "revising"}:
        return "↻"
    if key in {"failed", "fail", "reject", "excluded", "unavailable"}:
        return "✗"
    if key in {"warning", "degraded"}:
        return "!"
    return "·"


def _trunc(text: str, width: int) -> str:
    raw = " ".join(str(text or "").split())
    if width <= 1 or len(raw) <= width:
        return raw
    return raw[: width - 1] + "…"


def _hhmmss(seconds: float | None) -> str:
    if seconds is None:
        return ""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _event_clock(raw: Any) -> str:
    if not raw:
        return ""
    text = str(raw).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ).strftime("%H:%M:%S")


def _story_label(status: str) -> str:
    raw = (status or "").strip()
    if not raw:
        return ""
    return raw.upper() if raw.islower() else raw


def render(state: dict[str, Any], *, width: int = 80) -> Group:
    """Build the V1 single screen. Missing values are omitted or unknown."""
    status = str(state.get("status") or "IDLE")
    run_id = str(state.get("run_id") or "—")
    mode = str(state.get("mode") or "")
    clock = str(state.get("clock") or "")
    elapsed = _hhmmss(state.get("elapsed_sec"))
    stage = str(state.get("pipeline_stage") or "")
    inner = max(40, width - 4)

    header = Table.grid(expand=True)
    header.add_column(justify="left")
    header.add_column(justify="right")
    header.add_row(
        Text("Posting Auto 2.0", style="bold"),
        Text(clock),
    )
    meta = f"STATUS  {status}"
    if run_id and run_id != "—":
        meta += f"    RUN  {run_id}"
    if mode:
        meta += f"    MODE  {mode}"
    if stage and status == "RUNNING":
        meta += f"    STAGE  {stage}"
    if elapsed and status == "RUNNING":
        meta += f"    ELAPSED  {elapsed}"
    header.add_row(Text(meta), Text(""))
    reason = str(state.get("failure_reason") or "")
    if status == "FAILED" and reason:
        header.add_row(Text(f"Reason: {_trunc(reason, inner)}"), Text(""))
    if status == "IDLE":
        last = run_id if run_id != "—" else "none"
        header.add_row(
            Text(f"Last run: {last}    run_at: {state.get('run_at') or 'unknown'}    next: unknown"),
            Text(""),
        )

    runtime_tbl = Table(show_header=False, box=None, pad_edge=False, expand=True)
    runtime_tbl.add_column("k", ratio=1)
    runtime_tbl.add_column("v", ratio=1)
    runtime_rows = list(state.get("runtime") or [])
    if not runtime_rows:
        runtime_tbl.add_row("Network", "unknown")
        runtime_tbl.add_row("Ollama", "unknown")
    else:
        for row in runtime_rows:
            name = str(row.get("name") or "")
            st = str(row.get("status") or "unknown")
            runtime_tbl.add_row(f"{_sym(st)} {name}", st)

    pipe_tbl = Table(show_header=False, box=None, pad_edge=False, expand=True)
    pipe_tbl.add_column("step", ratio=2)
    pipe_tbl.add_column("extra", ratio=1)
    for row in state.get("pipeline") or []:
        name = str(row.get("name") or "")
        st = str(row.get("status") or "pending")
        extra = ""
        if row.get("count") is not None:
            extra = str(row["count"])
        pipe_tbl.add_row(f"{_sym(st)} {name}", extra)
    if not state.get("pipeline"):
        pipe_tbl.add_row("· pending", "")

    mid = Table.grid(expand=True, padding=(0, 1))
    mid.add_column(ratio=1)
    mid.add_column(ratio=1)
    mid.add_row(
        Panel(runtime_tbl, title="RUNTIME", border_style="dim"),
        Panel(pipe_tbl, title="PIPELINE", border_style="dim"),
    )

    story_tbl = Table(show_header=False, box=None, pad_edge=False, expand=True)
    story_tbl.add_column("idx", width=4)
    story_tbl.add_column("st", width=10)
    story_tbl.add_column("hdl", ratio=1)
    stories = list(state.get("stories") or [])
    if not stories:
        story_tbl.add_row("·", "", "no stories yet" if status == "RUNNING" else "—")
    else:
        h_width = max(12, inner - 22)
        for row in stories:
            idx = row.get("index")
            st = _story_label(str(row.get("status") or ""))
            story_tbl.add_row(
                str(idx) if idx is not None else "·",
                f"{_sym(st)} {st}" if st else "·",
                _trunc(str(row.get("headline") or ""), h_width),
            )
    rev = state.get("revision_count")
    story_title = "STORIES"
    if rev not in (None, ""):
        story_title += f"  rev {rev}"
    overall = state.get("review_overall")
    if overall:
        story_title += f"  {overall}"

    llm = dict(state.get("llm") or {})
    llm_lines: list[str] = []
    model = str(llm.get("model") or "").strip()
    if model:
        llm_lines.append(f"model: {model}")
    if llm.get("in_flight"):
        role = str(llm.get("role") or "llm")
        llm_lines.append(f"current role: {role}")
        if llm.get("duration_sec") is not None:
            llm_lines.append(f"current duration: {llm.get('duration_sec')}s")
    calls = llm.get("calls")
    failures = llm.get("failures")
    extras = []
    if calls:
        extras.append(f"calls: {calls}")
    if failures:
        extras.append(f"failures: {failures}")
    if extras:
        llm_lines.append("    ".join(extras))
    llm_body = "\n".join(llm_lines) if llm_lines else "—"

    pub_tbl = Table(show_header=False, box=None, pad_edge=False, expand=True)
    pub_tbl.add_column("ch", width=12)
    pub_tbl.add_column("st", ratio=1)
    for row in state.get("publish") or []:
        ch = str(row.get("channel") or "")
        st = str(row.get("status") or "pending")
        ident = row.get("id")
        extra = f" · media_id={ident}" if ident and st == "success" else ""
        pub_tbl.add_row(ch, f"{_sym(st)} {st}{extra}")
    if not state.get("publish"):
        pub_tbl.add_row("—", "")

    ev_lines: list[str] = []
    for item in state.get("events") or []:
        if isinstance(item, dict):
            ts = _event_clock(item.get("timestamp"))
            msg = str(item.get("message") or "")
            ev_lines.append(f"{ts} {msg}".strip() if ts else msg)
        else:
            ev_lines.append(str(item))
    ev_body = "\n".join(ev_lines[-5:]) if ev_lines else "—"

    return Group(
        Panel(header, border_style="bold"),
        mid,
        Panel(story_tbl, title=story_title, border_style="dim"),
        Panel(Text(llm_body), title="LLM", border_style="dim"),
        Panel(pub_tbl, title="PUBLISH", border_style="dim"),
        Panel(Text(ev_body), title="LAST EVENT", border_style="dim"),
    )


def render_text(state: dict[str, Any], *, width: int = 80) -> str:
    console = Console(file=StringIO(), width=width, color_system=None, force_terminal=False)
    console.print(render(state, width=width))
    return str(console.file.getvalue())


def main() -> int:
    console = Console()
    try:
        with Live(console=console, refresh_per_second=1, screen=True) as live:
            while True:
                state = read_state(probe=True)
                live.update(render(state, width=console.width))
                time.sleep(1)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
