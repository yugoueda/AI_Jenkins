#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [ ! -f .env ]; then
  echo "error: create .env and set JENKINS_IMAGE and AGENT_IMAGE first" >&2
  exit 1
fi

read_env_value() {
  sed -n "s/^$1=//p" .env | tail -n 1
}

jenkins_image="$(read_env_value JENKINS_IMAGE)"
agent_image="$(read_env_value AGENT_IMAGE)"

for image in "$jenkins_image" "$agent_image"; do
  if [ -z "$image" ] || [[ "$image" != */* ]]; then
    echo "error: both image names must include a registry/repository path" >&2
    echo "JENKINS_IMAGE=$jenkins_image" >&2
    echo "AGENT_IMAGE=$agent_image" >&2
    exit 1
  fi
done

docker compose --env-file .env -f compose.yaml -f compose.build.yaml \
  --profile agent build --pull jenkins agent-init
docker push "$jenkins_image"
docker push "$agent_image"

echo "[ok] Published $jenkins_image"
echo "[ok] Published $agent_image"
