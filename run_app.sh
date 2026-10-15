#!/usr/bin/env bash
# Start both FastAPI backend and Streamlit dashboard simultaneously
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

export PYTHONPATH="$DIR:${PYTHONPATH:-}"

UVICORN_BIN="$DIR/.venv/bin/uvicorn"
STREAMLIT_BIN="$DIR/.venv/bin/streamlit"

if [ ! -x "$UVICORN_BIN" ]; then
    if command -v uvicorn >/dev/null 2>&1; then
        UVICORN_BIN="uvicorn"
    else
        echo "❌ Uvicorn binary not found at $DIR/.venv/bin/uvicorn or in PATH."
        exit 1
    fi
fi

if [ ! -x "$STREAMLIT_BIN" ]; then
    if command -v streamlit >/dev/null 2>&1; then
        STREAMLIT_BIN="streamlit"
    else
        echo "❌ Streamlit binary not found at $DIR/.venv/bin/streamlit or in PATH."
        exit 1
    fi
fi

BACKEND_PID=""

cleanup() {
    if [ -n "$BACKEND_PID" ]; then
        echo ""
        echo "🛑 Shutting down backend (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
        echo "Done."
    fi
}

trap cleanup EXIT INT TERM

# Check if backend is already running
if curl -s -f http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "ℹ️ Backend is already running and healthy on http://127.0.0.1:8000"
else
    echo "🚀 Starting LogLens AI Backend on http://127.0.0.1:8000 ..."
    "$UVICORN_BIN" app.main:app --host 127.0.0.1 --port 8000 --reload &
    BACKEND_PID=$!

    echo "⏳ Waiting for backend to be ready..."
    BACKEND_READY=0
    for i in $(seq 1 30); do
        if curl -s -f http://127.0.0.1:8000/health >/dev/null 2>&1; then
            BACKEND_READY=1
            echo "✅ Backend is healthy and ready!"
            break
        fi
        if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo "❌ Backend server process died unexpectedly on startup."
            exit 1
        fi
        sleep 0.5
    done

    if [ "$BACKEND_READY" -ne 1 ]; then
        echo "❌ Backend failed to become healthy within 15 seconds."
        exit 1
    fi
fi

echo "🌟 Launching Streamlit Dashboard on http://localhost:8501 ..."
"$STREAMLIT_BIN" run frontend/streamlit_app.py --browser.gatherUsageStats false --server.headless true
