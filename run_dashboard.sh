#!/usr/bin/env bash
# Start the Streamlit dashboard using the project virtualenv
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

export PYTHONPATH="$DIR:${PYTHONPATH:-}"

STREAMLIT_BIN="$DIR/.venv/bin/streamlit"
if [ ! -x "$STREAMLIT_BIN" ]; then
    if command -v streamlit >/dev/null 2>&1; then
        STREAMLIT_BIN="streamlit"
    else
        echo "❌ Streamlit binary not found at $DIR/.venv/bin/streamlit or in PATH."
        echo "Please set up the virtual environment: python3 -m venv .venv && pip install -e ."
        exit 1
    fi
fi

echo "🌟 Launching Streamlit Dashboard on http://localhost:8501 ..."
exec "$STREAMLIT_BIN" run frontend/streamlit_app.py --browser.gatherUsageStats false --server.headless true
