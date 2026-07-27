#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$bundle_dir"

for required in compose.yaml .env images.tar.gz SHA256SUMS; do
  if [ ! -f "$required" ]; then
    echo "error: missing bundle file: $required" >&2
    exit 1
  fi
done

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum -c SHA256SUMS
else
  shasum -a 256 -c SHA256SUMS
fi

echo "[install] Loading container images..."
gzip -dc images.tar.gz | docker image load

if [ -f jenkins-home.tar.gz ]; then
  volume_name="ai-jenkins_jenkins-home"
  if docker volume inspect "$volume_name" >/dev/null 2>&1; then
    echo "error: $volume_name already exists; refusing to overwrite Jenkins data" >&2
    exit 1
  fi

  docker compose --env-file .env create
  jenkins_image="$(sed -n 's/^JENKINS_IMAGE=//p' .env | tail -n 1)"
  docker run --rm \
    --user root \
    --entrypoint tar \
    -v "$volume_name:/restore" \
    -v "$bundle_dir:/bundle:ro" \
    "$jenkins_image" \
    xzf /bundle/jenkins-home.tar.gz -C /restore
fi

docker compose --env-file .env up -d --no-build --wait --wait-timeout 180
docker compose --env-file .env ps

echo "[ok] Jenkins is available at http://localhost:8080"
