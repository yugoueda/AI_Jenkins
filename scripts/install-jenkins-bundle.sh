#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$bundle_dir"

for required in compose.yaml .env images.tar.gz SHA256SUMS bundle-manifest.txt; do
  if [ ! -f "$required" ]; then
    echo "error: missing bundle file: $required" >&2
    exit 1
  fi
done

if ! command -v docker >/dev/null 2>&1; then
  echo "error: Docker is not installed" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "error: Docker Compose v2 is not available" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "error: Docker daemon is not reachable; start Docker and retry" >&2
  exit 1
fi

host_architecture="$(docker version --format '{{.Server.Arch}}')"
for key in jenkins_architecture agent_architecture docker_image_architecture; do
  image_architecture="$(sed -n "s/^${key}=//p" bundle-manifest.txt | tail -n 1)"
  if [ -n "$image_architecture" ] && [ "$image_architecture" != "$host_architecture" ]; then
    echo "error: bundle architecture $image_architecture does not match Docker host $host_architecture" >&2
    exit 1
  fi
done

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum -c SHA256SUMS
else
  shasum -a 256 -c SHA256SUMS
fi

docker compose --env-file .env --profile agent config --quiet

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
