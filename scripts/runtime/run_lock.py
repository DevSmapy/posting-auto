"""Single-run lock for MVP_MODE=autonomous."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK_PATH = ROOT / "data" / "locks" / "autonomous.lock"


def _lock_timeout_sec() -> int:
    raw = os.getenv("AUTONOMOUS_LOCK_TIMEOUT_SEC", "7200").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 7200


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


class RunLock:
    def __init__(self, path: Path, *, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self._held = False

    def acquire(self) -> tuple[bool, str]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "pid": os.getpid(),
            "started_at": now,
            "run_id": self.run_id,
        }
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        for _ in range(3):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    raw = self.path.read_text(encoding="utf-8")
                    existing = json.loads(raw) if raw.strip() else {}
                except (OSError, json.JSONDecodeError):
                    existing = {}
                pid = int(existing.get("pid") or 0)
                started = str(existing.get("started_at") or "")
                # Incomplete write from a concurrent creator — do not steal.
                if not existing or pid <= 0:
                    return False, "active lock (incomplete)"
                stale = False
                if started:
                    try:
                        started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                        age = (datetime.now(timezone.utc) - started_dt).total_seconds()
                        stale = age > _lock_timeout_sec()
                    except ValueError:
                        stale = True
                if _pid_alive(pid) and not stale:
                    return (
                        False,
                        f"active lock pid={pid} run_id={existing.get('run_id')} started={started}",
                    )
                try:
                    self.path.unlink(missing_ok=True)
                except OSError:
                    pass
                continue

            try:
                os.write(fd, encoded)
            finally:
                os.close(fd)
            self._held = True
            return True, ""

        return False, "lock acquire failed after retries"

    def release(self) -> None:
        if not self._held or not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if int(data.get("pid") or 0) == os.getpid():
                self.path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            self.path.unlink(missing_ok=True)
        self._held = False


@contextmanager
def autonomous_run_lock(
    run_id: str,
    *,
    lock_path: Path | None = None,
) -> Iterator[tuple[bool, str]]:
    lock = RunLock(lock_path or DEFAULT_LOCK_PATH, run_id=run_id)
    acquired, reason = lock.acquire()
    try:
        yield acquired, reason
    finally:
        if acquired:
            lock.release()
