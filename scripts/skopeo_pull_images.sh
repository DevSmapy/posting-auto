#!/usr/bin/env bash
# 이미지를 외장 HDD tar로 받은 뒤 docker load 로 적재 (skopeo)
#
# 참고 (Mac Docker Desktop):
#   skopeo copy … docker-daemon:…  는
#   "writing blob: io: read/write on closed pipe" 가 자주 납니다.
#   → archive 저장은 skopeo, daemon 적재는 docker load 를 씁니다.
#
# 사용 예:
#   ./scripts/skopeo_pull_images.sh
#   IMAGE_DIR="/Volumes/WD_BLACK/Careers/DockerData/images" ./scripts/skopeo_pull_images.sh
#   # ollama 이미지 tar 만 Extreme SSD 에 둘 때:
#   IMAGE_DIR="$OLLAMA_IMAGE_DIR" ./scripts/skopeo_pull_images.sh   # (스크립트 내 ollama 줄 주석 해제 후)
set -euo pipefail

# 기본: WD_BLACK (postgres / browserless / n8n tar)
# ollama tar 는 OLLAMA_IMAGE_DIR (Extreme SSD, 경로에 공백 있음 → 항상 따옴표)
IMAGE_DIR="${IMAGE_DIR:-/Volumes/WD_BLACK/Careers/DockerData/images}"
OLLAMA_IMAGE_DIR="${OLLAMA_IMAGE_DIR:-/Volumes/Extreme SSD/DockerData/images}"
# 외장 HDD 직접 쓰기가 불안정하면 로컬에 받은 뒤 복사
WORK_DIR="${WORK_DIR:-/tmp/skopeo-pull-work}"
OS_OVERRIDE="${OS_OVERRIDE:-linux}"
ARCH_OVERRIDE="${ARCH_OVERRIDE:-arm64}"

# .env 로드 (공백 경로용 따옴표 유지)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
  IMAGE_DIR="${IMAGE_DIR:-/Volumes/WD_BLACK/Careers/DockerData/images}"
  OLLAMA_IMAGE_DIR="${OLLAMA_IMAGE_DIR:-/Volumes/Extreme SSD/DockerData/images}"
fi

mkdir -p "$IMAGE_DIR" "$WORK_DIR" "$OLLAMA_IMAGE_DIR"

copy_and_load() {
  local ref="$1"      # docker.io/library/postgres:16-alpine
  local name="$2"     # postgres-16-alpine
  local dest_ref="$3" # postgres:16-alpine

  local tar="$IMAGE_DIR/${name}.tar"
  local tmp="$WORK_DIR/${name}.tar"

  echo "==> skopeo copy docker://$ref"
  echo "    arch=${OS_OVERRIDE}/${ARCH_OVERRIDE}"
  echo "    temp -> $tmp"

  rm -f "$tmp"
  skopeo copy \
    --override-os "$OS_OVERRIDE" \
    --override-arch "$ARCH_OVERRIDE" \
    "docker://$ref" \
    "docker-archive:${tmp}:${dest_ref}"

  echo "==> copy archive -> $tar"
  rm -f "$tar"
  cp -f "$tmp" "$tar"
  rm -f "$tmp"

  echo "==> docker load -i (skopeo docker-daemon 우회)"
  local load_out
  load_out="$(docker load -i "$tar")"
  echo "$load_out"

  # RepoTags 가 비어 있는 archive 대비 — ID로 재태그
  if ! docker image inspect "$dest_ref" >/dev/null 2>&1; then
    local img_id
    img_id="$(echo "$load_out" | awk '/Loaded image ID:/ {print $4; exit}')"
    if [[ -z "${img_id:-}" ]]; then
      img_id="$(echo "$load_out" | awk '/Loaded image:/ {print $3; exit}')"
    fi
    if [[ -n "${img_id:-}" ]]; then
      echo "==> docker tag $img_id $dest_ref"
      docker tag "$img_id" "$dest_ref"
    else
      echo "!! could not determine image id to tag as $dest_ref" >&2
      exit 1
    fi
  fi

  docker image inspect "$dest_ref" --format 'OK: {{.RepoTags}} {{.Id}}'
}

# MVP 보조 이미지
copy_and_load "docker.io/library/postgres:16-alpine" "postgres-16-alpine" "postgres:16-alpine"
copy_and_load "ghcr.io/browserless/chromium:latest" "browserless-chromium" "ghcr.io/browserless/chromium:latest"

# (선택) n8n — WD_BLACK IMAGE_DIR
# copy_and_load "docker.io/n8nio/n8n:latest" "n8n-latest" "n8nio/n8n:latest"

# (선택) ollama — Extreme SSD 의 OLLAMA_IMAGE_DIR 에 저장
# IMAGE_DIR="$OLLAMA_IMAGE_DIR" copy_and_load "docker.io/ollama/ollama:latest" "ollama-latest" "ollama/ollama:latest"

echo
echo "Done. General archives (WD_BLACK): $IMAGE_DIR"
ls -lh "$IMAGE_DIR"
echo
echo "Ollama archives (Extreme SSD): $OLLAMA_IMAGE_DIR"
ls -lh "$OLLAMA_IMAGE_DIR" 2>/dev/null || true
