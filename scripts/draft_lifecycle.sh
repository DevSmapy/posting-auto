#!/usr/bin/env bash
# Draft-run Docker lifecycle: start containers, release ollama after LLM,
# stop remaining on exit. Source from run_draft.sh (do not exec).
# shellcheck shell=bash

OLLAMA_CONTAINER="${OLLAMA_CONTAINER:-ollama}"
OLLAMA_HOST_URL="${OLLAMA_HOST_URL:-http://127.0.0.1:11434}"
OLLAMA_HOST_URL="${OLLAMA_HOST_URL%/}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"
OLLAMA_AUTO_CONTAINER="${OLLAMA_AUTO_CONTAINER:-1}"
OLLAMA_DOCKER_RESTART="${OLLAMA_DOCKER_RESTART:-0}"
OLLAMA_WAIT_SEC="${OLLAMA_WAIT_SEC:-90}"
OLLAMA_WARM="${OLLAMA_WARM:-1}"

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-}"
BROWSERLESS_CONTAINER="${BROWSERLESS_CONTAINER:-}"
# 1 = manage postgres/browserless via compose (same start/stop workflow as ollama)
DRAFT_AUTO_AUX="${DRAFT_AUTO_AUX:-1}"
POSTGRES_WAIT_SEC="${POSTGRES_WAIT_SEC:-60}"
# browserless: auto-start when PUBLISH_CARDS is on, or force with DRAFT_START_BROWSERLESS=1
DRAFT_START_BROWSERLESS="${DRAFT_START_BROWSERLESS:-}"

_draft_root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
_draft_compose_file="${DRAFT_COMPOSE_FILE:-$_draft_root/docker-compose.yml}"

_ollama_truthy() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|y) return 0 ;;
    *) return 1 ;;
  esac
}

_draft_auto_on() {
  _ollama_truthy "${OLLAMA_AUTO_CONTAINER}"
}

_draft_aux_on() {
  _ollama_truthy "${DRAFT_AUTO_AUX}"
}

_draft_compose() {
  docker compose -f "$_draft_compose_file" --project-directory "$_draft_root" "$@"
}

_draft_want_browserless() {
  if [[ -n "${DRAFT_START_BROWSERLESS}" ]]; then
    _ollama_truthy "${DRAFT_START_BROWSERLESS}"
    return $?
  fi
  _ollama_truthy "${PUBLISH_CARDS:-0}"
}

_draft_resolve_compose_container() {
  # $1 = compose service name → prints container id/name or empty
  local svc="$1"
  _draft_compose ps -q "$svc" 2>/dev/null || true
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

postgres_wait_ready() {
  local port="${POSTGRES_PORT:-5433}"
  local i
  echo "==> waiting for Postgres on 127.0.0.1:${port} (up to ${POSTGRES_WAIT_SEC}s)"
  for ((i = 1; i <= POSTGRES_WAIT_SEC; i++)); do
    if (echo >/dev/tcp/127.0.0.1/"$port") >/dev/null 2>&1; then
      echo "   ready (${i}s)"
      return 0
    fi
    # bash /dev/tcp may be unavailable; fall back to nc/docker exec
    if command -v nc >/dev/null 2>&1 && nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then
      echo "   ready (${i}s)"
      return 0
    fi
    sleep 1
  done
  echo "!! Postgres did not become ready within ${POSTGRES_WAIT_SEC}s (SQLite fallback may apply)" >&2
  return 0
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

_draft_start_named() {
  local name="$1"
  if [[ -z "$name" ]]; then
    return 0
  fi
  if ! docker inspect "$name" >/dev/null 2>&1; then
    echo "!! container '${name}' not found — skip" >&2
    return 0
  fi
  if _ollama_truthy "${OLLAMA_DOCKER_RESTART}" && [[ "$name" == "$OLLAMA_CONTAINER" ]]; then
    echo "==> docker restart ${name}"
    docker restart "$name" >/dev/null
  else
    echo "==> docker start ${name}"
    docker start "$name" >/dev/null
  fi
}

draft_start_aux_containers() {
  if ! _draft_aux_on; then
    echo "==> DRAFT_AUTO_AUX=${DRAFT_AUTO_AUX} — skip postgres/browserless"
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  if [[ ! -f "$_draft_compose_file" ]]; then
    echo "!! compose file missing: $_draft_compose_file" >&2
    return 0
  fi

  echo "==> compose up -d postgres"
  if ! _draft_compose up -d postgres; then
    echo "!! compose up postgres failed — continuing (SQLite fallback may apply)" >&2
  else
    postgres_wait_ready || true
  fi

  if _draft_want_browserless; then
    echo "==> compose up -d browserless"
    if ! _draft_compose up -d browserless; then
      echo "!! compose up browserless failed — continuing" >&2
    fi
  else
    echo "==> skip browserless (PUBLISH_CARDS/DRAFT_START_BROWSERLESS off)"
  fi

  # Optional explicit names (override compose discovery for stop later)
  if [[ -z "$POSTGRES_CONTAINER" ]]; then
    POSTGRES_CONTAINER="$(_draft_resolve_compose_container postgres)"
  fi
  if _draft_want_browserless && [[ -z "$BROWSERLESS_CONTAINER" ]]; then
    BROWSERLESS_CONTAINER="$(_draft_resolve_compose_container browserless)"
  fi
}

draft_start_ollama() {
  if ! _draft_auto_on; then
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
  _draft_start_named "$OLLAMA_CONTAINER"
  ollama_wait_ready
}

# Start everything needed for a draft run.
draft_start_all() {
  draft_start_aux_containers
  draft_start_ollama
  ollama_warm_model
}

# After LLM work finishes — free RAM before Discord wait / Approve.
# Safe to call multiple times (idempotent).
draft_release_ollama() {
  if ! _draft_auto_on; then
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  if ! docker inspect "$OLLAMA_CONTAINER" >/dev/null 2>&1; then
    return 0
  fi
  # Only act if running
  if [[ "$(docker inspect -f '{{.State.Running}}' "$OLLAMA_CONTAINER" 2>/dev/null || echo false)" != "true" ]]; then
    echo "==> ollama already stopped"
    return 0
  fi

  echo "==> unload model ${OLLAMA_MODEL} (best-effort)"
  docker exec "$OLLAMA_CONTAINER" ollama stop "$OLLAMA_MODEL" >/dev/null 2>&1 || true

  echo "==> docker stop ${OLLAMA_CONTAINER} (before Discord / Approve)"
  docker stop "$OLLAMA_CONTAINER" >/dev/null 2>&1 || true
}

# After all LLM work: stop ollama and aux so Approve wait does not hold RAM/CPU.
draft_release_after_llm() {
  echo "==> release containers after LLM (before Discord / Approve)"
  draft_release_ollama || true
  draft_stop_aux_containers || true
}

draft_stop_aux_containers() {
  if ! _draft_aux_on; then
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  if [[ ! -f "$_draft_compose_file" ]]; then
    return 0
  fi

  echo "==> compose stop postgres browserless"
  _draft_compose stop postgres browserless >/dev/null 2>&1 || true
}

# Final cleanup: ollama (if still up) + aux containers.
draft_cleanup_all() {
  draft_release_ollama || true
  draft_stop_aux_containers || true
}

# --- backwards-compatible aliases ---
ollama_start_container() { draft_start_ollama; }
ollama_cleanup_container() { draft_release_ollama; }
