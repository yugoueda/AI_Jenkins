#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:?repo root is required}"
port="${2:?port is required}"
install_dependencies="${3:-1}"

cd "$repo_root"

if [ ! -d .venv ]; then
  echo "[start-webhook] Creating Python virtual environment"
  python3 -m venv .venv
fi

. .venv/bin/activate

if [ "$install_dependencies" = "1" ]; then
  if ! python -c "import fastapi, uvicorn, sqlalchemy, alembic" >/dev/null 2>&1; then
    echo "[start-webhook] Installing Python dependencies"
    python -m pip install --upgrade pip
    pip install -r requirements.txt
  else
    echo "[start-webhook] Python dependencies already available"
  fi
fi

echo "[start-webhook] Applying database migrations"
alembic upgrade head

echo "[start-webhook] Stopping existing webhook server on port $port if present"
pkill -f "uvicorn Src.main:app .*--port $port" >/dev/null 2>&1 || true
pkill -f "uvicorn Src.main:app.*--port $port" >/dev/null 2>&1 || true
