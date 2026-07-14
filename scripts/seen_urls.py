"""seen_urls store: Postgres preferred, SQLite fallback when DB is down."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def url_hash(url: str) -> str:
    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()


def _pg_dsn() -> dict[str, Any] | None:
    if env("SEEN_URLS_BACKEND", "auto").lower() == "sqlite":
        return None
    database_url = env("DATABASE_URL")
    if database_url.startswith("postgres"):
        return {"dsn": database_url}
    host = env("POSTGRES_HOST", "127.0.0.1")
    port = env("POSTGRES_PORT", "5433")
    user = env("POSTGRES_USER", "n8n")
    password = env("POSTGRES_PASSWORD", "change_me")
    db = env("POSTGRES_DB", "n8n")
    if not user or not db:
        return None
    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "dbname": db,
    }


def _sqlite_path() -> Path:
    raw = env("SEEN_URLS_SQLITE", str(ROOT / "output" / "seen_urls.sqlite"))
    path = Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _init_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_urls (
          url_hash TEXT PRIMARY KEY,
          url TEXT NOT NULL,
          title TEXT,
          used_in_run_at TEXT NOT NULL DEFAULT (datetime('now')),
          tistory_post_id TEXT,
          ig_media_id TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_seen_urls_used_at ON seen_urls (used_in_run_at DESC)"
    )
    conn.commit()


class SeenUrlsStore:
    """Filter and record published article URLs."""

    def __init__(self) -> None:
        self.backend = "none"
        self._pg = None
        self._sqlite_path = _sqlite_path()
        self._connect()

    def _connect(self) -> None:
        cfg = _pg_dsn()
        if cfg is not None and env("SEEN_URLS_BACKEND", "auto").lower() != "sqlite":
            try:
                import psycopg

                if "dsn" in cfg:
                    conn = psycopg.connect(cfg["dsn"], connect_timeout=3)
                else:
                    conn = psycopg.connect(connect_timeout=3, **cfg)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS seen_urls (
                      url_hash CHAR(64) PRIMARY KEY,
                      url TEXT NOT NULL,
                      title TEXT,
                      used_in_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                      tistory_post_id TEXT,
                      ig_media_id TEXT
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_seen_urls_used_at ON seen_urls (used_in_run_at DESC)"
                )
                conn.commit()
                self._pg = conn
                self.backend = "postgres"
                return
            except Exception as exc:  # noqa: BLE001
                print(f"   !! Postgres seen_urls unavailable ({exc}); using SQLite fallback")

        conn = sqlite3.connect(self._sqlite_path)
        _init_sqlite(conn)
        conn.close()
        self.backend = "sqlite"

    def close(self) -> None:
        if self._pg is not None:
            self._pg.close()
            self._pg = None

    @contextmanager
    def _sqlite(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._sqlite_path)
        try:
            _init_sqlite(conn)
            yield conn
            conn.commit()
        finally:
            conn.close()

    def fetch_hashes(self) -> set[str]:
        if self.backend == "postgres" and self._pg is not None:
            rows = self._pg.execute("SELECT url_hash FROM seen_urls").fetchall()
            return {str(r[0]).strip() for r in rows}
        with self._sqlite() as conn:
            rows = conn.execute("SELECT url_hash FROM seen_urls").fetchall()
            return {str(r[0]) for r in rows}

    def filter_new(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = self.fetch_hashes()
        if not seen:
            return articles
        out: list[dict[str, Any]] = []
        for a in articles:
            link = a.get("link") or ""
            if url_hash(link) in seen:
                continue
            out.append(a)
        skipped = len(articles) - len(out)
        if skipped:
            print(f"   seen_urls filtered: {skipped} (backend={self.backend})")
        return out

    def record_published(
        self,
        articles: list[dict[str, Any]],
        *,
        tistory_post_id: str | None = None,
        ig_media_id: str | None = None,
    ) -> int:
        rows = []
        for a in articles:
            link = (a.get("link") or "").strip()
            if not link:
                continue
            rows.append(
                (
                    url_hash(link),
                    link,
                    a.get("title") or "",
                    tistory_post_id,
                    ig_media_id,
                )
            )
        if not rows:
            return 0

        if self.backend == "postgres" and self._pg is not None:
            with self._pg.cursor() as cur:
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO seen_urls (url_hash, url, title, tistory_post_id, ig_media_id)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (url_hash) DO UPDATE SET
                          used_in_run_at = NOW(),
                          tistory_post_id = COALESCE(EXCLUDED.tistory_post_id, seen_urls.tistory_post_id),
                          ig_media_id = COALESCE(EXCLUDED.ig_media_id, seen_urls.ig_media_id)
                        """,
                        row,
                    )
            self._pg.commit()
            return len(rows)

        with self._sqlite() as conn:
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO seen_urls (url_hash, url, title, used_in_run_at, tistory_post_id, ig_media_id)
                    VALUES (?, ?, ?, datetime('now'), ?, ?)
                    ON CONFLICT(url_hash) DO UPDATE SET
                      used_in_run_at = datetime('now'),
                      tistory_post_id = COALESCE(excluded.tistory_post_id, seen_urls.tistory_post_id),
                      ig_media_id = COALESCE(excluded.ig_media_id, seen_urls.ig_media_id)
                    """,
                    row,
                )
        return len(rows)
