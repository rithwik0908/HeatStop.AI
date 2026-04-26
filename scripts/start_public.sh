#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3)"
fi

PORT="${PORT:-8501}"
BACKEND_PORT="${HEATSTOP_BACKEND_PORT:-8000}"
BUILD_ON_START="${HEATSTOP_BUILD_ON_START:-0}"
BOOT_CORRIDORS="${HEATSTOP_BOOT_CORRIDORS:-M15:0,M15-SBS:0,M101:0}"
BOOT_STOP_LIMIT="${HEATSTOP_BOOT_STOP_LIMIT:-15}"

export HEATSTOP_API_URL="${HEATSTOP_API_URL:-http://127.0.0.1:${BACKEND_PORT}}"

if [[ "$BUILD_ON_START" =~ ^(1|true|yes)$ ]]; then
  if [[ -n "$BOOT_CORRIDORS" ]]; then
    "$PYTHON_BIN" scripts/build_demo_data.py --corridors "$BOOT_CORRIDORS" --stop-limit "$BOOT_STOP_LIMIT"
  else
    "$PYTHON_BIN" scripts/build_demo_data.py \
      --route "${HEATSTOP_ROUTE_SHORT_NAME:-M15}" \
      --direction "${HEATSTOP_DIRECTION_ID:-0}" \
      --stop-limit "$BOOT_STOP_LIMIT"
  fi
fi

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

"$PYTHON_BIN" -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!

"$PYTHON_BIN" - <<PY
import sys
import time
import urllib.request

url = "http://127.0.0.1:${BACKEND_PORT}/health"
for _ in range(60):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                sys.exit(0)
    except Exception:
        time.sleep(0.5)

print(f"Backend never became ready at {url}", file=sys.stderr)
sys.exit(1)
PY

exec "$PYTHON_BIN" -m streamlit run ui/dashboard.py \
  --server.address 0.0.0.0 \
  --server.port "$PORT" \
  --server.headless true
