#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$ROOT_DIR/.bin"
CLOUDFLARED="$BIN_DIR/cloudflared"
PORT="${1:-8501}"

mkdir -p "$BIN_DIR"

if [[ ! -x "$CLOUDFLARED" ]]; then
  echo "Downloading cloudflared..."
  curl -L --fail \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o "$CLOUDFLARED"
  chmod +x "$CLOUDFLARED"
fi

echo "Opening public tunnel for http://127.0.0.1:${PORT}"
exec "$CLOUDFLARED" tunnel --url "http://127.0.0.1:${PORT}" --no-autoupdate
