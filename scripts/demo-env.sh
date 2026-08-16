#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

action="${1:-up}"

log() {
  echo "[demo-env] $1"
}

check_health() {
  log "Checking webhook and Jenkins health endpoints"
  curl --fail --silent --output /dev/null http://127.0.0.1:8000/healthz \
    && log "webhook: healthy" \
    || log "webhook: not reachable yet"
  curl --fail --silent --output /dev/null http://127.0.0.1:8080/login \
    && log "jenkins: healthy" \
    || log "jenkins: not reachable yet"
}

pull_flutter_image_if_missing() {
  log "Checking Flutter build image in Jenkins DinD volume"
  if docker compose exec -T jenkins \
      docker image inspect ghcr.io/cirruslabs/flutter:stable >/dev/null 2>&1; then
    log "Flutter image already present, skipping pull"
  else
    log "Flutter image missing, pulling ghcr.io/cirruslabs/flutter:stable"
    docker compose exec -T jenkins \
      docker pull ghcr.io/cirruslabs/flutter:stable
  fi
}

cmd_up() {
  docker compose config --quiet
  docker compose --profile agent up -d --no-build --wait
  docker compose ps
  ./scripts/claude-login.sh status
  pull_flutter_image_if_missing
  check_health
  log "Demo environment is up."
}

cmd_rebuild() {
  ./scripts/jenkins-image.sh build
  ./scripts/agent-image.sh build
  docker compose --profile agent up -d --no-build --force-recreate --wait
  docker compose ps
  ./scripts/claude-login.sh status
  pull_flutter_image_if_missing
  check_health
  log "Rebuild complete. Run '$0 jobs' if Jenkinsfile.* or create-ai-review-jobs.groovy changed."
}

cmd_jobs() {
  ./scripts/refresh-jenkins-jobs.sh
}

cmd_status() {
  docker compose ps
  ./scripts/claude-login.sh status
  check_health
}

cmd_logs() {
  docker compose --profile agent logs --tail=100 jenkins webhook worker
}

cmd_ngrok() {
  command -v ngrok >/dev/null 2>&1 || {
    echo "error: ngrok command not found; install and authenticate ngrok first" >&2
    exit 1
  }
  log "Starting ngrok tunnel for http://127.0.0.1:8000 (Ctrl-C to stop)"
  log "Register <ngrok-domain>/webhook as the GitLab Webhook URL once ngrok reports its address."
  exec ngrok http http://127.0.0.1:8000
}

cmd_down() {
  log "If ngrok is running, stop it (Ctrl-C) in its terminal before or after this."
  docker compose --profile agent down
  log "Stopped. Named volumes (Jenkins config/jobs, Claude Code auth, DB, Flutter image) are preserved."
}

case "$action" in
  up)
    cmd_up
    ;;
  rebuild)
    cmd_rebuild
    ;;
  jobs)
    cmd_jobs
    ;;
  status)
    cmd_status
    ;;
  logs)
    cmd_logs
    ;;
  ngrok)
    cmd_ngrok
    ;;
  down)
    cmd_down
    ;;
  *)
    echo "usage: $0 {up|rebuild|jobs|status|logs|ngrok|down}" >&2
    echo "  up      通常の再開 (docker compose up, ヘルスチェック, Flutterイメージ確認)" >&2
    echo "  rebuild イメージ再構築 + ジョブ定義以外の再作成" >&2
    echo "  jobs    Jenkinsジョブ定義の再読み込み" >&2
    echo "  status  コンテナ状態とヘルスチェック" >&2
    echo "  logs    jenkins/webhook/workerの直近ログ" >&2
    echo "  ngrok   ngrokトンネルを起動 (別ターミナルで実行, Ctrl-Cで停止)" >&2
    echo "  down    Composeコンテナの停止 (named volumeは保持)" >&2
    exit 2
    ;;
esac
