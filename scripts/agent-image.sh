#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

action="${1:-build}"

case "$action" in
  build)
    docker compose -f compose.yaml -f compose.build.yaml \
      --profile agent build --pull agent-init
    ;;
  push)
    if [ ! -f .env ]; then
      echo "error: create .env and set AGENT_IMAGE to a registry image first" >&2
      exit 1
    fi

    image="$(sed -n 's/^AGENT_IMAGE=//p' .env | tail -n 1)"
    if [ -z "$image" ] || [[ "$image" != */* ]]; then
      echo "error: AGENT_IMAGE must include a registry/repository path" >&2
      exit 1
    fi

    docker compose -f compose.yaml -f compose.build.yaml \
      --profile agent build --pull agent-init
    docker push "$image"
    ;;
  *)
    echo "usage: $0 {build|push}" >&2
    exit 2
    ;;
esac
