#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

REDIS_URL="${DT_REDIS_URL:-${REDIS_URL:-}}"
SEEDS="${DT_SEEDS:-}"
OWNER="${DT_OWNER:-$(whoami)}"
PORT="${DT_PORT:-7777}"
NODE_IP="${DT_NODE_IP:-}"

if [ -z "$REDIS_URL" ]; then
  echo "Set DT_REDIS_URL to the Mac mini Redis URL, for example:"
  echo "  DT_REDIS_URL=redis://192.168.1.12:6379/0"
  exit 1
fi

echo "Starting native peer"
echo "  owner: $OWNER"
echo "  redis: $REDIS_URL"
echo "  seeds: ${SEEDS:-<none>}"
echo "  port:  $PORT"

python3 -m pip install -q -r requirements.txt
python3 -m pip install -q zeroconf cryptography psutil

if [ -z "$NODE_IP" ]; then
  NODE_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
fi

if [ -n "$SEEDS" ]; then
  DT_NODE_IP="$NODE_IP" PYTHONPATH=. python3 -m node_agent.__main__ \
    --owner "$OWNER" \
    --redis-url "$REDIS_URL" \
    --port "$PORT" \
    --seeds "$SEEDS"
else
  DT_NODE_IP="$NODE_IP" PYTHONPATH=. python3 -m node_agent.__main__ \
    --owner "$OWNER" \
    --redis-url "$REDIS_URL" \
    --port "$PORT"
fi
