#!/usr/bin/env bash
# 기존 ollama 컨테이너 CPU/메모리 상한 (MacBook Air 권장)
# 재생성 없이 docker update 로 적용됩니다.
set -euo pipefail

NAME="${OLLAMA_CONTAINER:-ollama}"
CPUS="${OLLAMA_DOCKER_CPUS:-2.0}"
MEMORY="${OLLAMA_DOCKER_MEMORY:-6g}"
# memory-swap 을 memory 와 같게 두면 swap 없이 상한만 적용 (Docker 제약 회피)
# -1 이면 swap 무제한이라 Mac Desktop 에서 거부될 수 있음 → memory 와 동일 권장
MEMORY_SWAP="${OLLAMA_DOCKER_MEMORY_SWAP:-$MEMORY}"

echo "==> docker update $NAME --cpus=$CPUS --memory=$MEMORY --memory-swap=$MEMORY_SWAP"
docker update \
  --cpus="$CPUS" \
  --memory="$MEMORY" \
  --memory-swap="$MEMORY_SWAP" \
  "$NAME"

docker inspect "$NAME" --format \
  'NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}} MemorySwap={{.HostConfig.MemorySwap}}'
echo "OK. Also set in .env: OLLAMA_NUM_THREAD=4 (API 옵션)"
