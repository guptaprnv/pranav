# DTrain — Distributed Training Network
# ──────────────────────────────────────────────────────────────────────────────
# Usage:
#   make help              → list all commands
#   make train-aws-5min    → full run: Mac mini + AWS 5-min training
#   make mac-start         → start Mac mini services (Docker)
#   make aws-setup         → check / configure AWS credentials
#
# Set your username:  DT_OWNER=yourname make train-aws-5min
# Use Spot instances: DT_USE_SPOT=1 make train-aws-5min  (~70% cheaper)
# ──────────────────────────────────────────────────────────────────────────────

DT_OWNER    ?= $(shell whoami)
DT_MINUTES  ?= 5
DT_REGION   ?= us-east-1
DT_USE_SPOT ?= 0

COMPOSE     := docker compose -f docker/docker-compose.mac.yml
PYTHON      := python3

.DEFAULT_GOAL := help

# ── Colors ────────────────────────────────────────────────────────────────────
CYAN  := \033[0;36m
BOLD  := \033[1m
RESET := \033[0m

# ────────────────────────────────────────────────────────────────────────────
## Main targets
# ────────────────────────────────────────────────────────────────────────────

.PHONY: train-aws-5min
train-aws-5min: ## 🚀 Full run: Mac mini Docker + 5-min AWS training
	@chmod +x scripts/train_5min.sh
	@DT_OWNER=$(DT_OWNER) DT_MINUTES=$(DT_MINUTES) \
	 DT_REGION=$(DT_REGION) DT_USE_SPOT=$(DT_USE_SPOT) \
	 bash scripts/train_5min.sh

.PHONY: train-aws
train-aws: ## ☁️  Launch AWS training only (no Mac mini setup)
	@DT_USE_SPOT=$(DT_USE_SPOT) $(PYTHON) scripts/aws_train.py \
		--minutes $(DT_MINUTES) \
		--region  $(DT_REGION)  \
		--model   resnet50      \
		--dataset cifar10

# ────────────────────────────────────────────────────────────────────────────
## Mac mini
# ────────────────────────────────────────────────────────────────────────────

.PHONY: mac-start
mac-start: ## 🖥  Start Mac mini services (Docker: Redis + API + agent)
	@chmod +x scripts/mac_start.sh
	@DT_OWNER=$(DT_OWNER) bash scripts/mac_start.sh

.PHONY: mac-stop
mac-stop: ## ⏹  Stop all Mac mini Docker services
	$(COMPOSE) down

.PHONY: mac-logs
mac-logs: ## 📋 Tail Mac mini service logs
	$(COMPOSE) logs -f

.PHONY: mac-status
mac-status: ## 📊 Show cluster status
	@curl -s http://localhost:8002/cluster | $(PYTHON) -m json.tool

.PHONY: mac-restart
mac-restart: mac-stop mac-start ## 🔄 Restart Mac mini services

# ────────────────────────────────────────────────────────────────────────────
## AWS
# ────────────────────────────────────────────────────────────────────────────

.PHONY: aws-setup
aws-setup: ## 🔑 Check / configure AWS credentials
	@chmod +x scripts/aws_setup.sh
	@bash scripts/aws_setup.sh

.PHONY: aws-spot
aws-spot: ## 💰 5-min training on Spot instance (~70% cheaper)
	@$(MAKE) train-aws DT_USE_SPOT=1

.PHONY: aws-10min
aws-10min: ## ⏱  10-minute AWS training run
	@$(MAKE) train-aws DT_MINUTES=10

# ────────────────────────────────────────────────────────────────────────────
## Local dev (no GPU required)
# ────────────────────────────────────────────────────────────────────────────

.PHONY: train-local
train-local: ## 💻 Run training locally (CPU, 2 epochs, quick test)
	$(PYTHON) -m src.train \
		--config configs/small.yaml \
		--max_minutes 2

.PHONY: install
install: ## 📦 Install Python dependencies
	pip install -r requirements.txt

.PHONY: peer-start
peer-start: ## 🔌 Start a native peer worker connected to a remote Redis/API seed
	@chmod +x scripts/peer_start.sh
	@DT_OWNER=$(DT_OWNER) DT_REDIS_URL="$(DT_REDIS_URL)" DT_SEEDS="$(DT_SEEDS)" DT_PORT="$(DT_PORT)" \
	  bash scripts/peer_start.sh

# ────────────────────────────────────────────────────────────────────────────
## iPad
# ────────────────────────────────────────────────────────────────────────────

.PHONY: ipad-setup
ipad-setup: ## 📱 Setup iPad React Native app
	cd mobile/ios && npm install
	@echo ""
	@MAC_IP=$$(ipconfig getifaddr en0 2>/dev/null || echo "YOUR_MAC_IP"); \
	echo "  Next steps:"; \
	echo "  1. cd mobile/ios && npx expo start"; \
	echo "  2. Scan the QR code with your iPad's Camera app"; \
	echo "  3. In the app: Settings → Agent URL → http://$$MAC_IP:7777"

.PHONY: ipad-start
ipad-start: ## 📱 Start iPad app (Expo dev server)
	cd mobile/ios && npx expo start --tunnel

# ────────────────────────────────────────────────────────────────────────────
## Utilities
# ────────────────────────────────────────────────────────────────────────────

.PHONY: jobs
jobs: ## 📋 List queued training jobs
	@curl -s http://localhost:8002/jobs | $(PYTHON) -m json.tool

.PHONY: credits
credits: ## 💳 Show credit balance
	@curl -s "http://localhost:8002/credits?owner=$(DT_OWNER)" \
	  | $(PYTHON) -m json.tool 2>/dev/null || \
	  echo "Start mac-start first, then check credits via the iPad app"

.PHONY: clean
clean: ## 🧹 Stop Docker and remove volumes
	$(COMPOSE) down -v --remove-orphans
	@echo "  Volumes removed."

.PHONY: help
help: ## Show this help
	@echo ""
	@echo "$(BOLD)$(CYAN)DTrain — Distributed Training$(RESET)"
	@echo ""
	@echo "$(BOLD)Quick start:$(RESET)"
	@echo "  DT_OWNER=yourname make train-aws-5min"
	@echo ""
	@echo "$(BOLD)Commands:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-18s$(RESET) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)Options:$(RESET)"
	@echo "  DT_OWNER=name     Your username  (default: $$(whoami))"
	@echo "  DT_MINUTES=5      Training time  (default: 5)"
	@echo "  DT_REGION=...     AWS region     (default: us-east-1)"
	@echo "  DT_USE_SPOT=1     Use Spot ~70%% cheaper"
	@echo ""
