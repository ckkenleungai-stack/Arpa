#!/usr/bin/env bash
# Arpa W1 local API (expects Postgres up or MemorySaver fallback for unit paths)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}/packages/control_plane:${ROOT}/packages/workflows:${ROOT}/packages/gateway:${ROOT}/packages/tools:${ROOT}/packages/db:${ROOT}/packages/ar:${ROOT}/packages/evals${PYTHONPATH:+:$PYTHONPATH}"
export ALLOWED_ROOT="${ALLOWED_ROOT:-${ROOT}/workspace_data}"
export JWT_SECRET="${JWT_SECRET:-dev-only-change-me-not-a-real-secret-32b-min}"
export JWT_ISSUER="${JWT_ISSUER:-arpa-local}"
export JWT_AUDIENCE="${JWT_AUDIENCE:-arpa-api}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://arpa:arpa@localhost:5432/arpa}"
export DATABASE_URL_SYNC="${DATABASE_URL_SYNC:-postgresql://arpa:arpa@localhost:5432/arpa}"

mkdir -p "$ALLOWED_ROOT"

echo "Starting Arpa control plane on :8000 ..."
exec uvicorn control_plane.main:app --reload --host 0.0.0.0 --port 8000
