#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

env_args=()
if [ -f .env ]; then
  env_args=(--env-file .env)
elif [ -f .env.example ]; then
  env_args=(--env-file .env.example)
fi

action="${1:-login}"

validate_oauth_token() {
  local env_file=""
  if [ -f .env ]; then
    env_file=".env"
  elif [ -f .env.example ]; then
    env_file=".env.example"
  fi

  [ -n "$env_file" ] || return 0

  local oauth_token
  oauth_token="$(sed -n 's/^CLAUDE_CODE_OAUTH_TOKEN=//p' "$env_file" | tail -n 1)"
  if [ -n "$oauth_token" ] && [[ "$oauth_token" != sk-ant-oat* ]]; then
    echo "error: CLAUDE_CODE_OAUTH_TOKEN is not a setup-token result." >&2
    echo "The final token must start with sk-ant-oat; do not use the browser authorization code." >&2
    return 1
  fi
}

case "$action" in
  setup-token)
    docker compose "${env_args[@]}" --profile agent run \
      --rm --no-deps worker claude setup-token
    echo
    echo "Set the final token beginning with sk-ant-oat in CLAUDE_CODE_OAUTH_TOKEN."
    echo "Do not set the browser authorization code in .env."
    ;;
  login)
    validate_oauth_token
    docker compose "${env_args[@]}" --profile agent run \
      --rm --no-deps worker claude auth login --claudeai
    ;;
  status)
    validate_oauth_token
    docker compose "${env_args[@]}" --profile agent run \
      --rm --no-deps worker claude auth status --text
    ;;
  logout)
    docker compose "${env_args[@]}" --profile agent run \
      --rm --no-deps worker claude auth logout
    ;;
  *)
    echo "usage: $0 {setup-token|login|status|logout}" >&2
    exit 2
    ;;
esac
