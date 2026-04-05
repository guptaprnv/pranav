#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# train_5min.sh — Full orchestration:
#   1. Start Mac mini (Docker: Redis + API + node agent)
#   2. Check AWS credentials
#   3. Launch g4dn.xlarge on AWS, run ResNet-50/CIFAR-10 for 5 minutes
#   4. Stream live logs to terminal
#   5. Auto-terminate EC2 when done
#   6. Print training summary
#
# Usage:
#   chmod +x scripts/train_5min.sh
#   DT_OWNER=yourname ./scripts/train_5min.sh
#
# Options (env vars):
#   DT_OWNER      — your username (required)
#   DT_MINUTES    — training duration in minutes (default: 5)
#   DT_REGION     — AWS region (default: us-east-1)
#   DT_USE_SPOT=1 — use Spot instance (~70% cheaper, may be interrupted)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# ── Config ────────────────────────────────────────────────────────────────────
DT_OWNER="${DT_OWNER:-}"
DT_MINUTES="${DT_MINUTES:-5}"
DT_REGION="${DT_REGION:-us-east-1}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'

banner() { echo -e "\n${BOLD}${CYAN}━━━ $1 ━━━${NC}"; }
ok()     { echo -e "  ${GREEN}✓${NC} $1"; }
warn()   { echo -e "  ${YELLOW}⚠${NC}  $1"; }
die()    { echo -e "  ${RED}✗${NC} $1"; exit 1; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║  DTrain — Mac mini + iPad + AWS                   ║"
echo "  ║  ResNet-50 on CIFAR-10 · ${DT_MINUTES}-minute run             ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Owner ─────────────────────────────────────────────────────────────────────
if [ -z "$DT_OWNER" ]; then
    read -r -p "  Enter your username: " DT_OWNER
fi
export DT_OWNER

# ════════════════════════════════════════════════════════════════════
# STEP 1 — Mac mini: start local services in Docker
# ════════════════════════════════════════════════════════════════════
banner "Step 1/3 · Mac mini — Docker services"

DOCKER_COMPOSE="docker compose"
docker compose version &>/dev/null 2>&1 || DOCKER_COMPOSE="docker-compose"

if ! docker info &>/dev/null 2>&1; then
    die "Docker is not running. Start Docker Desktop first."
fi

echo "  Starting Redis + API + node agent…"
DT_OWNER="$DT_OWNER" $DOCKER_COMPOSE \
    -f docker/docker-compose.mac.yml \
    up -d --remove-orphans 2>&1 | grep -E "(Starting|Recreating|Created|Running|✓)" || true

# Wait for API
echo -n "  Waiting for API server"
for i in $(seq 1 20); do
    curl -sf http://localhost:8000/health &>/dev/null && { echo ""; ok "API ready"; break; }
    echo -n "."; sleep 3
done

# Find LAN IP for iPad
MAC_IP=$(ipconfig getifaddr en0 2>/dev/null || \
         ipconfig getifaddr en1 2>/dev/null || \
         hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")

echo ""
echo -e "  ${BOLD}iPad:${NC} Open DTrain app → Settings → Agent URL → ${CYAN}http://${MAC_IP}:7777${NC}"

# ════════════════════════════════════════════════════════════════════
# STEP 2 — AWS: check credentials
# ════════════════════════════════════════════════════════════════════
banner "Step 2/3 · AWS — Credential Check"

if ! command -v aws &>/dev/null; then
    warn "AWS CLI not found."
    echo "  Install: brew install awscli  or  pip install awscli"
    echo "  Then run: make aws-setup"
    die "AWS CLI required."
fi

if ! python3 -c "import boto3" 2>/dev/null; then
    echo "  Installing boto3…"
    pip install --quiet boto3
fi

IDENTITY=$(aws sts get-caller-identity --output json 2>/dev/null || echo "")
if [ -z "$IDENTITY" ]; then
    echo ""
    warn "No AWS credentials. Running setup…"
    bash scripts/aws_setup.sh
    IDENTITY=$(aws sts get-caller-identity --output json 2>/dev/null || echo "")
    [ -z "$IDENTITY" ] && die "AWS credentials still invalid. See scripts/aws_setup.sh"
fi

ACCOUNT=$(echo "$IDENTITY" | python3 -c "import sys,json; print(json.load(sys.stdin)['Account'])")
ok "AWS account: $ACCOUNT (region: $DT_REGION)"

# Cost warning
COST=$(python3 -c "print(f'\${${DT_MINUTES} * 0.526 / 60:.3f}')")
echo ""
echo -e "  ${YELLOW}Cost estimate: ~${COST} for ${DT_MINUTES} min on g4dn.xlarge (on-demand)${NC}"
echo -e "  ${YELLOW}Set DT_USE_SPOT=1 to save ~70%${NC}"
echo ""
read -r -p "  Proceed? [Y/n]: " CONFIRM
[[ "${CONFIRM:-Y}" =~ ^[Nn]$ ]] && { echo "  Cancelled."; exit 0; }

# ════════════════════════════════════════════════════════════════════
# STEP 3 — AWS: launch training
# ════════════════════════════════════════════════════════════════════
banner "Step 3/3 · AWS — Launching Training"

echo "  Launching g4dn.xlarge · ResNet-50 · CIFAR-10 · ${DT_MINUTES} min"
echo ""

python3 scripts/aws_train.py \
    --minutes  "$DT_MINUTES" \
    --region   "$DT_REGION"  \
    --model    resnet50       \
    --dataset  cifar10

# ════════════════════════════════════════════════════════════════════
# Done
# ════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔════════════════════════════════════════╗"
echo "  ║  Training run complete! 🎉              ║"
echo "  ╚════════════════════════════════════════╝"
echo -e "${NC}"
echo "  Dashboard:   http://localhost:8000/docs"
echo "  Cluster:     http://localhost:8000/cluster"
echo "  iPad app:    Connect to http://${MAC_IP}:7777"
echo ""
echo "  Checkpoints: docker exec \$(docker ps -qf name=api) ls /checkpoints"
echo ""
