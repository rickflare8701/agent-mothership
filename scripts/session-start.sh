#!/usr/bin/env bash
# Session startup — run this at the start of every opencode session
set -euo pipefail

echo "=== Agent Mothership Session Start ==="

# 1. Headroom proxy (context compression)
if ! curl -sf http://127.0.0.1:8787/health >/dev/null 2>&1; then
  echo "Starting Headroom proxy on port 8787..."
  pip install "headroom-ai[proxy]" --break-system-packages -q 2>/dev/null
  nohup headroom proxy --port 8787 > /tmp/headroom-proxy.log 2>&1 &
  sleep 1
  export HEADROOM_PROXY_URL=http://127.0.0.1:8787
  echo "  Headroom proxy started (PID $!)"
else
  echo "  Headroom proxy already running"
fi

echo "=== Ready ==="
