#!/bin/sh
# BioVault Agent startup script
# The agent loop is a daemon thread inside FastAPI — no separate process needed.
# uvicorn starts the app; lifespan() kicks off the agent thread automatically.

set -e

echo "Starting BioVault Agent v2.0.0"
echo "DB_PATH=${DB_PATH:-/data/biovault.db}"
echo "UPLOAD_DIR=${UPLOAD_DIR:-/data/uploads}"

mkdir -p "${DB_PATH%/*}" "${UPLOAD_DIR:-/data/uploads}"

exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info \
    --access-log
