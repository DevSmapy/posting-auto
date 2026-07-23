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
# Cold load of 7B on Mac/Docker CPU often exceeds 3m; default 10m.
OLLAMA_WARM_TIMEOUT_SEC="${OLLAMA_WARM_TIMEOUT_SEC:-600}"
OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-30m}"
# Server-side model load budget (container env). Default Ollama is 5m — too short here.
OLLAMA_LOAD_TIMEOUT="${OLLAMA_LOAD_TIMEOUT:-10m}"
OLLAMA_NUM_THREAD="${OLLAMA_NUM_THREAD:-4}"
OLLAMA_NUM_CTX="${OLLAMA_NUM_CTX:-4096}"
OLLAMA_TEMPERATURE="${OLLAMA_TEMPERATURE:-0.3}"

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

ollama_container_env_value() {
  local key="$1"
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$OLLAMA_CONTAINER" 2>/dev/null \
    | awk -F= -v k="$key" '$1==k {print substr($0, index($0,"=")+1); exit}'
}

# Recreate ollama if LOAD_TIMEOUT / KEEP_ALIVE env differ (docker update cannot change Env).
ollama_ensure_runtime_env() {
  if ! _draft_auto_on; then
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  if ! docker inspect "$OLLAMA_CONTAINER" >/dev/null 2>&1; then
    return 0
  fi

  local want_load="${OLLAMA_LOAD_TIMEOUT:-10m}"
  local want_keep="${OLLAMA_KEEP_ALIVE:-30m}"
  local cur_load cur_keep
  cur_load="$(ollama_container_env_value OLLAMA_LOAD_TIMEOUT)"
  cur_keep="$(ollama_container_env_value OLLAMA_KEEP_ALIVE)"
  if [[ "$cur_load" == "$want_load" && "$cur_keep" == "$want_keep" ]]; then
    return 0
  fi

  # Standalone/external ollama (not posting-auto compose profile). Re-apply
  # inspect'd networks/restart/runtime/binds so n8n hostname reachability survives.
  local image port
  image="$(docker inspect -f '{{.Config.Image}}' "$OLLAMA_CONTAINER")"
  port="$(docker inspect -f '{{(index (index .HostConfig.PortBindings "11434/tcp") 0).HostPort}}' "$OLLAMA_CONTAINER" 2>/dev/null || true)"
  port="${port:-11434}"

  local -a bind_args=()
  local b
  while IFS= read -r b; do
    [[ -n "$b" ]] && bind_args+=(-v "$b")
  done < <(docker inspect -f '{{range .HostConfig.Binds}}{{println .}}{{end}}' "$OLLAMA_CONTAINER")

  local -a nets=()
  local n
  while IFS= read -r n; do
    [[ -n "$n" ]] && nets+=("$n")
  done < <(docker inspect -f '{{range $k, $_ := .NetworkSettings.Networks}}{{println $k}}{{end}}' "$OLLAMA_CONTAINER")

  local restart_name restart_max
  restart_name="$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$OLLAMA_CONTAINER" 2>/dev/null || true)"
  restart_max="$(docker inspect -f '{{.HostConfig.RestartPolicy.MaximumRetryCount}}' "$OLLAMA_CONTAINER" 2>/dev/null || true)"
  local -a restart_args=()
  if [[ -n "$restart_name" && "$restart_name" != "no" ]]; then
    if [[ "$restart_name" == "on-failure" && -n "$restart_max" && "$restart_max" != "0" ]]; then
      restart_args=(--restart "on-failure:${restart_max}")
    else
      restart_args=(--restart "$restart_name")
    fi
  fi

  local runtime
  runtime="$(docker inspect -f '{{.HostConfig.Runtime}}' "$OLLAMA_CONTAINER" 2>/dev/null || true)"
  local -a runtime_args=()
  if [[ -n "$runtime" && "$runtime" != "runc" && "$runtime" != "io.containerd.runc.v2" ]]; then
    runtime_args=(--runtime "$runtime")
  fi

  local -a network_create_args=()
  if ((${#nets[@]} > 0)); then
    network_create_args=(--network "${nets[0]}")
  fi

  echo "==> recreate ${OLLAMA_CONTAINER}: OLLAMA_LOAD_TIMEOUT ${cur_load:-unset}→${want_load}, OLLAMA_KEEP_ALIVE ${cur_keep:-unset}→${want_keep}"
  docker stop "$OLLAMA_CONTAINER" >/dev/null 2>&1 || true
  docker rm "$OLLAMA_CONTAINER" >/dev/null

  docker run -d --name "$OLLAMA_CONTAINER" \
    -p "${port}:11434" \
    -e OLLAMA_HOST=0.0.0.0:11434 \
    -e "OLLAMA_LOAD_TIMEOUT=${want_load}" \
    -e "OLLAMA_KEEP_ALIVE=${want_keep}" \
    "${network_create_args[@]}" \
    "${restart_args[@]}" \
    "${runtime_args[@]}" \
    "${bind_args[@]}" \
    "$image" >/dev/null

  local i
  for ((i = 1; i < ${#nets[@]}; i++)); do
    docker network connect "${nets[i]}" "$OLLAMA_CONTAINER" >/dev/null 2>&1 || true
  done

  # Preserve resource caps (lost on recreate; docker update cannot set Env).
  local cpus="${OLLAMA_DOCKER_CPUS:-4.0}"
  local memory="${OLLAMA_DOCKER_MEMORY:-10g}"
  docker update --cpus="$cpus" --memory="$memory" --memory-swap="$memory" "$OLLAMA_CONTAINER" >/dev/null 2>&1 || true
  local nets_disp="${nets[*]}"
  nets_disp="${nets_disp:-bridge}"
  echo "   recreated (${image}, port=${port}, nets=${nets_disp}, cpus=${cpus}, memory=${memory})"
}

ollama_warm_model() {
  if ! _ollama_truthy "${OLLAMA_WARM}"; then
    echo "==> skip model warm (OLLAMA_WARM=${OLLAMA_WARM})"
    return 0
  fi
  local timeout_sec="${OLLAMA_WARM_TIMEOUT_SEC:-600}"
  local keep_alive="${OLLAMA_KEEP_ALIVE:-30m}"
  local num_thread="${OLLAMA_NUM_THREAD:-4}"
  local num_ctx="${OLLAMA_NUM_CTX:-4096}"
  local temperature="${OLLAMA_TEMPERATURE:-0.3}"
  # Must match mvp_pipeline ollama_options() — mismatched num_ctx forces a cold reload.
  echo "==> warm model ${OLLAMA_MODEL} (timeout=${timeout_sec}s keep_alive=${keep_alive} num_ctx=${num_ctx} num_thread=${num_thread})"
  local payload
  payload="$(
    cat <<EOF
{
  "model": "${OLLAMA_MODEL}",
  "stream": false,
  "format": "json",
  "keep_alive": "${keep_alive}",
  "options": {
    "temperature": ${temperature},
    "num_thread": ${num_thread},
    "num_ctx": ${num_ctx}
  },
  "messages": [
    {"role": "user", "content": "{\"ok\":true} 만 JSON으로 반환"}
  ]
}
EOF
  )"
  if curl -fsS --max-time "${timeout_sec}" "${OLLAMA_HOST_URL}/api/chat" \
    -H 'Content-Type: application/json' \
    -d "$payload" \
    >/dev/null; then
    echo "   warm ok (same options as story LLM)"
  else
    echo "!! warm failed or timed out after ${timeout_sec}s — continuing; first LLM call may load the model" >&2
  fi
  return 0
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
  ollama_ensure_runtime_env
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
