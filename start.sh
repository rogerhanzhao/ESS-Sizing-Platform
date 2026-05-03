#!/usr/bin/env bash
# CALB ESS Sizing Platform — Linux / Docker startup script
# Usage: ./start.sh [--port PORT]
set -euo pipefail

PORT=8511
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        *)      echo "Unknown argument: $1"; exit 1 ;;
    esac
done

cd "$(dirname "$0")"

echo "Running database migrations..."
python -m alembic upgrade head
echo "Migrations OK."

exec python -m streamlit run app.py \
    --server.address 127.0.0.1 \
    --server.port "$PORT" \
    --server.headless true \
    --server.fileWatcherType none
