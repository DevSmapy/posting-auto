#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "$ROOT/.env"
  set +a
fi

OLLAMA_HOST="${OLLAMA_HOST_URL:-${OLLAMA_BASE_URL:-http://127.0.0.1:11434}}"
OLLAMA_HOST="${OLLAMA_HOST/http:\/\/ollama:/http://127.0.0.1:}"
OLLAMA_HOST="${OLLAMA_HOST/https:\/\/ollama:/https://127.0.0.1:}"
OLLAMA_HOST="${OLLAMA_HOST/host.docker.internal/127.0.0.1}"
OLLAMA_HOST="${OLLAMA_HOST%/}"
MODEL="${OLLAMA_MODEL:-qwen2.5:14b}"

echo "==> GET $OLLAMA_HOST/api/tags"
TAGS_JSON="$(curl -fsS "$OLLAMA_HOST/api/tags")"
echo "$TAGS_JSON" | head -c 800
echo
echo

if ! echo "$TAGS_JSON" | grep -q "\"name\":\"${MODEL}\""; then
  echo "!! model '$MODEL' not found on this Ollama."
  echo "   Pull it (existing Docker Ollama on :11434):"
  echo "   curl -N $OLLAMA_HOST/api/pull -d '{\"name\":\"$MODEL\"}'"
  echo
  echo "   Or set OLLAMA_MODEL in .env to an installed model, e.g. llama3.2:latest"
  # show installed names briefly
  echo "$TAGS_JSON" | tr ',' '\n' | grep '"name"' | head -n 20 || true
  exit 1
fi

echo "==> POST /api/chat (format=json) model=$MODEL"
curl -fsS "$OLLAMA_HOST/api/chat" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"stream\":false,\"format\":\"json\",\"messages\":[{\"role\":\"user\",\"content\":\"{\\\"ok\\\":true} 만 JSON으로 반환\"}]}" \
  | head -c 800
echo
echo
echo "OK: Ollama smoke passed"
