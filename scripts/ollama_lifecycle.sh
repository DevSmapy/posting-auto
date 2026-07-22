#!/usr/bin/env bash
# Ollama Docker container lifecycle helpers for draft runs.
# Source from run_draft.sh (do not exec). Expects ROOT and optional .env already loaded.
# shellcheck shell=bash

OLLAMA_CONTAINER="${OLLAMA_CONTAINER:-ollama}"
OLLAMA_HOST_URL="${OLLAMA_HOST_URL:-http://127.0.0.1:11434}"
OLLAMA_HOST_URL="${OLLAMA_HOST_URL%/}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"
OLLAMA_AUTO_CONTAINER="${OLLAMA_AUTO_CONTAINER:-1}"
OLLAMA_DOCKER_RESTART="${OLLAMA_DOCKER_RESTART:-0}"
OLLAMA_WAIT_SEC="${OLLAMA_WAIT_SEC:-90}"
OLLAMA_WARM="${OLLAMA_WARM:-1}"

_ollama_truthy() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|y) return 0 ;;
    *) return 1 ;;
  esac
}

_ollama_auto_on() {
  _ollama_truthy "${OLLAMA_AUTO_CONTAINER}"
}

ollama_wait_ready() {
  local i
  echo "==> waiting for Ollama at ${OLLAMA_HOST_URL}/api/tags (up to ${OLLAMA_WAIT_SEC}s)"
  for ((i = 1; i <= OLLAMA_WAIT_SEC; i++)); do
    if curl -fsS --max-time 2 "${OLLAMA_HOST_URL}/api/tags" >/dev/null 2>&1; then
      echo "   ready (${i}s)"
      return 0
    fi
    sleep 1
  done
  echo "!! Ollama did not become ready within ${OLLAMA_WAIT_SEC}s" >&2
  return 1
}

ollama_warm_model() {
  if ! _ollama_truthy "${OLLAMA_WARM}"; then
    echo "==> skip model warm (OLLAMA_WARM=${OLLAMA_WARM})"
    return 0
  fi
  echo "==> warm model ${OLLAMA_MODEL}"
  curl -fsS --max-time 180 "${OLLAMA_HOST_URL}/api/chat" \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"${OLLAMA_MODEL}\",\"stream\":false,\"keep_alive\":\"30m\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}" \
    >/dev/null
  echo "   warm ok"
}

ollama_start_container() {
  if ! _ollama_auto_on; then
    echo "==> OLLAMA_AUTO_CONTAINER=${OLLAMA_AUTO_CONTAINER} — skip docker start"
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    echo "!! docker not found; cannot manage ${OLLAMA_CONTAINER}" >&2
    return 1
  fi
  if ! docker inspect "$OLLAMA_CONTAINER" >/dev/null 2>&1; then
    echo "!! container '${OLLAMA_CONTAINER}' not found. Create it first, then re-run." >&2
    return 1
  fi

  if _ollama_truthy "${OLLAMA_DOCKER_RESTART}"; then
    echo "==> docker restart ${OLLAMA_CONTAINER}"
    docker restart "$OLLAMA_CONTAINER"
  else
    echo "==> docker start ${OLLAMA_CONTAINER}"
    docker start "$OLLAMA_CONTAINER" >/dev/null
  fi
  ollama_wait_ready
}

ollama_cleanup_container() {
  if ! _ollama_auto_on; then
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  if ! docker inspect "$OLLAMA_CONTAINER" >/dev/null 2>&1; then
    return 0
  fi

  echo "==> unload model ${OLLAMA_MODEL} (best-effort)"
  docker exec "$OLLAMA_CONTAINER" ollama stop "$OLLAMA_MODEL" >/dev/null 2>&1 || true

  echo "==> docker stop ${OLLAMA_CONTAINER}"
  docker stop "$OLLAMA_CONTAINER" >/dev/null 2>&1 || true
}
