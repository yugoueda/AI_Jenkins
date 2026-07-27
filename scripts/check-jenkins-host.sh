#!/usr/bin/env bash
set -euo pipefail

errors=0
kernel_release="$(uname -r)"

if [[ "$kernel_release" == *microsoft-standard-WSL2* ]]; then
  echo "[ok] WSL 2: $kernel_release"
elif [[ "$kernel_release" == *[Mm]icrosoft* ]]; then
  echo "[error] WSL 1 is not supported. Convert this distribution to WSL 2." >&2
  errors=$((errors + 1))
else
  echo "[info] Non-WSL Linux host: $kernel_release"
fi

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "[info] OS: ${PRETTY_NAME:-unknown}"
fi

if command -v docker >/dev/null 2>&1; then
  echo "[ok] $(docker --version)"
else
  echo "[error] Docker is not installed." >&2
  errors=$((errors + 1))
fi

if docker compose version >/dev/null 2>&1; then
  echo "[ok] $(docker compose version)"
else
  echo "[error] Docker Compose v2 is not available." >&2
  errors=$((errors + 1))
fi

if docker info >/dev/null 2>&1; then
  echo "[ok] Docker daemon is reachable."
else
  echo "[error] Docker daemon is not reachable." >&2
  errors=$((errors + 1))
fi

memory_kib="$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)"
disk_kib="$(df -Pk . | awk 'NR == 2 { print $4 }')"
echo "[info] Memory: $((memory_kib / 1024)) MiB"
echo "[info] Free disk at project path: $((disk_kib / 1024 / 1024)) GiB"

if ((memory_kib < 4 * 1024 * 1024)); then
  echo "[warning] Less than 4 GiB RAM is available to the Linux environment." >&2
fi

if ((disk_kib < 50 * 1024 * 1024)); then
  echo "[warning] Less than 50 GiB disk space is free." >&2
fi

if ((errors > 0)); then
  exit 1
fi

echo "[ok] Jenkins host prerequisites passed."
