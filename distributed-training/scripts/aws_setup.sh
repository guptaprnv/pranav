#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# aws_setup.sh — Check AWS credentials and configure if needed
#
# Run: chmod +x scripts/aws_setup.sh && ./scripts/aws_setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $1"; }
die()  { echo -e "  ${RED}✗${NC} $1"; exit 1; }
info() { echo -e "  ${CYAN}→${NC} $1"; }

echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║   DTrain — AWS Credential Setup      ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"

# ── 1. Check AWS CLI ──────────────────────────────────────────────────────────
if ! command -v aws &>/dev/null; then
    warn "AWS CLI not installed."
    echo ""
    info "Install it with:"
    echo "    brew install awscli          # Mac"
    echo "    pip install awscli           # pip"
    echo "    or: https://aws.amazon.com/cli/"
    echo ""
    die "Please install AWS CLI and re-run this script."
fi
ok "AWS CLI found: $(aws --version 2>&1 | head -1)"

# ── 2. Check Python boto3 ────────────────────────────────────────────────────
if ! python3 -c "import boto3" 2>/dev/null; then
    warn "boto3 not installed — installing now"
    pip install --quiet boto3
fi
ok "boto3 ready"

# ── 3. Test existing credentials ─────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}Checking existing AWS credentials…${NC}"

IDENTITY=$(aws sts get-caller-identity --output json 2>/dev/null || echo "")
if [ -n "$IDENTITY" ]; then
    ACCOUNT=$(echo "$IDENTITY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['Account'])")
    ARN=$(echo "$IDENTITY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['Arn'])")
    ok "Credentials valid!"
    info "Account : $ACCOUNT"
    info "Identity: $ARN"
    echo ""

    # Check g4dn.xlarge availability in a region
    REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")
    info "Checking g4dn.xlarge availability in $REGION…"
    AZ_INFO=$(aws ec2 describe-instance-type-offerings \
        --location-type availability-zone \
        --filters Name=instance-type,Values=g4dn.xlarge \
        --region "$REGION" \
        --query 'InstanceTypeOfferings[].Location' \
        --output text 2>/dev/null || echo "")

    if [ -n "$AZ_INFO" ]; then
        ok "g4dn.xlarge available in: $AZ_INFO"
    else
        warn "g4dn.xlarge not available in $REGION — try us-east-1 or us-west-2"
        info "Change region: aws configure set region us-east-1"
    fi
    echo ""
    ok "AWS is ready. Run: make train-aws-5min"
    exit 0
fi

# ── 4. No credentials — guide user ───────────────────────────────────────────
warn "No valid AWS credentials found."
echo ""
echo -e "${BOLD}  To get AWS credentials:${NC}"
echo ""
echo "  Option A — Existing account (recommended if you have one):"
echo "  1. Go to: https://console.aws.amazon.com/iam/home#/security_credentials"
echo "  2. Click 'Create access key'"
echo "  3. Download the CSV"
echo ""
echo "  Option B — New account:"
echo "  1. Sign up: https://aws.amazon.com/free"
echo "  2. Enable billing alerts so you don't get surprised"
echo "     (5 min on g4dn.xlarge ≈ \$0.05)"
echo ""
echo -e "${BOLD}  Then configure:${NC}"
echo "    aws configure"
echo "    # Enter: Access Key ID, Secret Access Key, region (us-east-1), output (json)"
echo ""
read -r -p "  Would you like to run 'aws configure' now? [y/N]: " DO_CONFIG
if [[ "$DO_CONFIG" =~ ^[Yy]$ ]]; then
    aws configure
    echo ""
    # Re-test
    IDENTITY=$(aws sts get-caller-identity --output json 2>/dev/null || echo "")
    if [ -n "$IDENTITY" ]; then
        ok "Credentials configured successfully!"
        ok "Run: make train-aws-5min"
    else
        die "Credentials still invalid. Check your Access Key and Secret."
    fi
fi
