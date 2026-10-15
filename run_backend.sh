#!/usr/bin/env bash
# Start the FastAPI backend server using the project virtualenv
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

export PYTHONPATH="$DIR:${PYTHONPATH:-}"

UVICORN_BIN="$DIR/.venv/bin/uvicorn"
if [ ! -x "$UVICORN_BIN" ]; then
    if command -v uvicorn >/dev/null 2>&1; then
        UVICORN_BIN="uvicorn"
    else
        echo "❌ Uvicorn binary not found at $DIR/.venv/bin/uvicorn or in PATH."
        echo "Please set up the virtual environment: python3 -m venv .venv && pip install -e ."
        exit 1
    fi
fi

echo "🚀 Starting LogLens AI Backend on http://127.0.0.1:8000 ..."
exec "$UVICORN_BIN" app.main:app --host 127.0.0.1 --port 8000 --reload
