#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# mac_start.sh — One-command Mac mini setup
#
# Run this on your Mac mini:
#   chmod +x scripts/mac_start.sh && ./scripts/mac_start.sh
#
# What it does:
#  1. Checks Docker is installed and running
#  2. Finds your Mac mini's LAN IP (for iPad to connect)
#  3. Starts Redis + API server + node agent in Docker
#  4. Prints QR code URL for iPad to connect
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'

banner() { echo -e "\n${BOLD}${CYAN}▶ $1${NC}"; }
ok()     { echo -e "  ${GREEN}✓${NC} $1"; }
warn()   { echo -e "  ${YELLOW}⚠${NC}  $1"; }
die()    { echo -e "  ${RED}✗${NC} $1"; exit 1; }

echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║   DTrain — Mac mini Node Setup       ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

# ── 1. Docker check ───────────────────────────────────────────────────────────
banner "Checking Docker"
command -v docker &>/dev/null || die "Docker not found. Install from https://docs.docker.com/desktop/mac/"
docker info &>/dev/null       || die "Docker daemon not running. Start Docker Desktop first."
ok "Docker is running"

DOCKER_COMPOSE="docker compose"
$DOCKER_COMPOSE version &>/dev/null || DOCKER_COMPOSE="docker-compose"

# ── 2. Owner name ─────────────────────────────────────────────────────────────
banner "Configuration"
if [ -z "${DT_OWNER:-}" ]; then
    read -r -p "  Enter your username (for credits & ledger): " DT_OWNER
    export DT_OWNER
fi
ok "Owner: $DT_OWNER"

# ── 3. LAN IP ─────────────────────────────────────────────────────────────────
MAC_IP=$(ipconfig getifaddr en0 2>/dev/null || \
         ipconfig getifaddr en1 2>/dev/null || \
         hostname -I 2>/dev/null | awk '{print $1}' || \
         echo "127.0.0.1")
ok "Mac mini LAN IP: $MAC_IP"

# ── 4. Start services ─────────────────────────────────────────────────────────
banner "Starting Docker services"
DT_OWNER="$DT_OWNER" $DOCKER_COMPOSE \
    -f docker/docker-compose.mac.yml \
    up -d --remove-orphans

# Wait for API to become healthy
echo -n "  Waiting for API server"
for i in $(seq 1 30); do
    if curl -sf "http://localhost:8000/health" &>/dev/null; then
        echo ""
        ok "API server is up"
        break
    fi
    echo -n "."
    sleep 2
done

# ── 5. Print iPad connection info ─────────────────────────────────────────────
API_URL="http://${MAC_IP}:8000"
AGENT_URL="http://${MAC_IP}:7777"

echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  ✓ Mac mini is live!${NC}"
echo ""
echo -e "  ${CYAN}API Server:${NC}   $API_URL"
echo -e "  ${CYAN}Node Agent:${NC}   $AGENT_URL"
echo ""
echo -e "  ${BOLD}iPad setup:${NC}"
echo -e "  1. Open the DTrain app on your iPad"
echo -e "  2. Go to Settings and set Agent URL to:"
echo -e "     ${YELLOW}${AGENT_URL}${NC}"
echo -e "  3. Tap 'Connect' — you'll see this Mac mini appear in Peers"
echo ""
echo -e "  ${BOLD}Cluster status:${NC}"
echo -e "  ${CYAN}curl ${API_URL}/cluster${NC}"
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"

# ── 6. Live tail ─────────────────────────────────────────────────────────────
echo ""
read -r -p "  Tail logs now? [y/N]: " TAIL
if [[ "$TAIL" =~ ^[Yy]$ ]]; then
    $DOCKER_COMPOSE -f docker/docker-compose.mac.yml logs -f
fi
