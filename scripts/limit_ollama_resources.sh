#!/usr/bin/env bash
# 기존 ollama 컨테이너 CPU/메모리 상한 (MacBook Air + Docker Desktop 12GB 권장)
# 재생성 없이 docker update 로 적용됩니다.
#
# NOTE: Docker Desktop Settings → Resources → Memory 와 이 스크립트의
# --memory 는 별개입니다. Desktop 한도만 올려도 컨테이너는 예전 상한이
# 남을 수 있으니, Desktop 변경 후 이 스크립트를 다시 실행하세요.
set -euo pipefail

NAME="${OLLAMA_CONTAINER:-ollama}"
CPUS="${OLLAMA_DOCKER_CPUS:-4.0}"
MEMORY="${OLLAMA_DOCKER_MEMORY:-10g}"
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
echo "Tip: ./scripts/run_draft.sh starts/stops this container automatically."
