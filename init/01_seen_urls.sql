-- seen_urls: 발행에 사용한 기사 URL 중복 방지
-- n8n Postgres와 동일 인스턴스에 생성 (init 시 1회)

CREATE TABLE IF NOT EXISTS seen_urls (
  url_hash CHAR(64) PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT,
  used_in_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  tistory_post_id TEXT,
  ig_media_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_seen_urls_used_at ON seen_urls (used_in_run_at DESC);
