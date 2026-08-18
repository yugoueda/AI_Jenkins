#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

with_agent=0
if [ "${1:-}" = "--with-agent" ]; then
  with_agent=1
elif [ "$#" -ne 0 ]; then
  echo "usage: $0 [--with-agent]" >&2
  exit 2
fi

for command_name in docker; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "error: $command_name is not installed" >&2
    exit 1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "error: Docker Compose v2 is not available" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "error: Docker daemon is not reachable; start Docker and retry" >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[setup] Created .env from .env.example."
  echo "[setup] Review GitLab/Jenkins credentials in .env before enabling integrations."
fi

docker compose --env-file .env --profile agent config --quiet

if ((with_agent == 1)); then
  echo "[setup] Building Jenkins and CLI agent images..."
  docker compose --env-file .env -f compose.yaml -f compose.build.yaml \
    --profile agent build --pull jenkins agent-init
  echo "[setup] Starting Jenkins, webhook, and worker..."
  docker compose --env-file .env --profile agent up -d --no-build --wait --wait-timeout 300
else
  echo "[setup] Building Jenkins image..."
  docker compose --env-file .env -f compose.yaml -f compose.build.yaml \
    build --pull jenkins
  echo "[setup] Starting Jenkins..."
  docker compose --env-file .env up -d --no-build --wait --wait-timeout 300
fi

docker compose --env-file .env --profile agent ps
jenkins_http_port="$(sed -n 's/^JENKINS_HTTP_PORT=//p' .env | tail -n 1)"
echo "[ok] Jenkins is available at http://localhost:${jenkins_http_port:-8080}"
echo "[next] Initial password: docker compose exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword"
if ((with_agent == 1)); then
  echo "[next] Claude login: ./scripts/claude-login.sh login"
fi
