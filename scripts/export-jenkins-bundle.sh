#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

include_data=0
if [ "${1:-}" = "--include-data" ]; then
  include_data=1
elif [ "$#" -ne 0 ]; then
  echo "usage: $0 [--include-data]" >&2
  exit 2
fi

compose_images="$(
  docker compose --profile agent config --format json |
    python3 -c 'import json,sys; c=json.load(sys.stdin); print(c["services"]["jenkins"]["image"]); print(c["services"]["worker"]["image"])'
)"
jenkins_image="$(printf '%s\n' "$compose_images" | sed -n '1p')"
agent_image="$(printf '%s\n' "$compose_images" | sed -n '2p')"
if [ -z "$jenkins_image" ] || [ -z "$agent_image" ]; then
  echo "error: could not resolve JENKINS_IMAGE or AGENT_IMAGE" >&2
  exit 1
fi

docker image inspect "$jenkins_image" >/dev/null
docker image inspect "$agent_image" >/dev/null
docker image inspect docker:28-dind >/dev/null

image_tag="${jenkins_image##*:}"
image_tag="${image_tag//[^A-Za-z0-9._-]/-}"
bundle_name="ai-jenkins-bundle-${image_tag}"
if ((include_data == 1)); then
  bundle_name="${bundle_name}-with-data"
fi
dist_root="$repo_root/dist"
bundle_dir="$dist_root/$bundle_name"
archive="$dist_root/$bundle_name.tar"

if [ -e "$bundle_dir" ] || [ -e "$archive" ]; then
  echo "error: bundle already exists: $bundle_name" >&2
  exit 1
fi

mkdir -p "$bundle_dir/jenkins/certs"
cp compose.yaml "$bundle_dir/compose.yaml"
cp scripts/install-jenkins-bundle.sh "$bundle_dir/install.sh"
cp scripts/claude-login.sh "$bundle_dir/claude-login.sh"
cp Doc/Jenkins_別PC導入手順.md "$bundle_dir/INSTALL.md"
cp Doc/CLIエージェント導入手順.md "$bundle_dir/AGENT_INSTALL.md"
chmod +x "$bundle_dir/install.sh"
chmod +x "$bundle_dir/claude-login.sh"

{
  echo "JENKINS_IMAGE=$jenkins_image"
  echo "AGENT_IMAGE=$agent_image"
  echo "JENKINS_HTTP_HOST=127.0.0.1"
  echo "JENKINS_HTTP_PORT=8080"
  echo "JENKINS_JAVA_OPTS=-Xms512m -Xmx2g -Djenkins.install.runSetupWizard=true"
  echo "WEBHOOK_HTTP_HOST=127.0.0.1"
  echo "WEBHOOK_HTTP_PORT=8000"
  echo "GITLAB_WEBHOOK_SECRET=change-me"
  echo "CLAUDE_CODE_OAUTH_TOKEN="
  echo "ANTHROPIC_API_KEY="
  echo "CLAUDE_MODEL=sonnet"
  echo "AGENT_TIMEOUT_SECONDS=600"
  echo "AGENT_MAX_ATTEMPTS=2"
} >"$bundle_dir/.env"

echo "[export] Saving container images..."
docker image save "$jenkins_image" "$agent_image" docker:28-dind |
  gzip -c >"$bundle_dir/images.tar.gz"

{
  echo "created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "jenkins_image=$jenkins_image"
  echo "jenkins_image_id=$(docker image inspect --format '{{.Id}}' "$jenkins_image")"
  echo "jenkins_architecture=$(docker image inspect --format '{{.Architecture}}' "$jenkins_image")"
  echo "agent_image=$agent_image"
  echo "agent_image_id=$(docker image inspect --format '{{.Id}}' "$agent_image")"
  echo "agent_architecture=$(docker image inspect --format '{{.Architecture}}' "$agent_image")"
  echo "docker_image=docker:28-dind"
  echo "docker_image_id=$(docker image inspect --format '{{.Id}}' docker:28-dind)"
  echo "includes_jenkins_home=$include_data"
} >"$bundle_dir/bundle-manifest.txt"

if ((include_data == 1)); then
  volume_name="ai-jenkins_jenkins-home"
  if ! docker volume inspect "$volume_name" >/dev/null 2>&1; then
    echo "error: Jenkins volume not found: $volume_name" >&2
    exit 1
  fi

  echo "[export] Stopping Jenkins for a consistent data backup..."
  docker compose stop jenkins
  restart_required=1
  trap 'if [ "${restart_required:-0}" = 1 ]; then docker compose up -d jenkins; fi' EXIT

  docker run --rm \
    --user root \
    --entrypoint tar \
    -v "$volume_name:/source:ro" \
    -v "$bundle_dir:/bundle" \
    "$jenkins_image" \
    czf /bundle/jenkins-home.tar.gz -C /source .

  docker compose up -d --wait --wait-timeout 180 jenkins
  restart_required=0
  trap - EXIT
fi

(
  cd "$bundle_dir"
  checksum_files=(
    images.tar.gz
    compose.yaml
    install.sh
    claude-login.sh
    .env
    INSTALL.md
    AGENT_INSTALL.md
    bundle-manifest.txt
  )
  if ((include_data == 1)); then
    checksum_files+=(jenkins-home.tar.gz)
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${checksum_files[@]}" >SHA256SUMS
  else
    shasum -a 256 "${checksum_files[@]}" >SHA256SUMS
  fi
)

tar -cf "$archive" -C "$dist_root" "$bundle_name"

(
  cd "$dist_root"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$bundle_name.tar" >"$bundle_name.tar.sha256"
  else
    shasum -a 256 "$bundle_name.tar" >"$bundle_name.tar.sha256"
  fi
)

echo "[ok] Bundle: $archive"
echo "[ok] Checksum: $archive.sha256"
