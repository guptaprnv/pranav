# Distributed Training Network

A peer-to-peer distributed ML training platform where **you earn training time
by contributing your compute**. Run a Mac mini, an iPad, or a cloud VM —
every device you contribute earns credits you spend to train your own models.

**Initial target: 20 concurrent users → architected for 1000.**

---

## Core Idea

```
You contribute compute  →  earn credits  →  spend credits to train models
      Mac mini M3                              ResNet, LLaMA, Diffusion…
      iPad M2                                  on the shared GPU cluster
      Cloud GPU
```

Credits are proportional to hardware tier and time contributed.
A Mac mini M3 running for 1 hour earns enough credits to run ~21 minutes of
A100-equivalent training.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Devices                          │
│  Mac mini M3        iPad M2         Linux Workstation   │
│  [Node Agent]       [iOS App]        [Node Agent]       │
│  [Menu Bar App]     [Contributes]    [torchrun]         │
└────────────┬────────────┬───────────────┬───────────────┘
             │  P2P Gossip│  mDNS/UDP     │
             ▼            ▼               ▼
┌─────────────────────────────────────────────────────────┐
│                   P2P Network Layer                      │
│  Peer Discovery (mDNS + UDP broadcast + static seeds)   │
│  Gossip Protocol (cluster state, peer health)           │
│  Gradient Sync Channel (TCP, FedAvg aggregation)        │
└────────────────────────┬────────────────────────────────┘
                         │
             ┌───────────▼───────────┐
             │    Orchestration      │
             │  Task Dispatcher      │  ← assigns data shards to peers
             │  Sync Manager         │  ← model versioning, FedAvg
             │  Fault Handler        │  ← peer dropout recovery
             └───────────┬───────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Job Queue   │ │  Ledger      │ │  Cloud       │
│  (Redis)     │ │  Contribution│ │  Backup      │
│  Priority    │ │  Credits     │ │  S3/GCS/AES  │
│  Scheduling  │ │  Quotas      │ │  Rate limits │
└──────────────┘ └──────────────┘ └──────────────┘
        │
        ▼
┌──────────────┐
│  REST API    │  ← FastAPI, scales horizontally
│  /jobs       │
│  /cluster    │
│  /credits    │
└──────────────┘
```

---

## Quick Start

### Recommended: Docker on Mac mini
```bash
DT_OWNER=your_username docker compose -f docker/docker-compose.mac.yml up -d --force-recreate
```

Host endpoints:
- API: `http://localhost:8002`
- Node agent: `http://localhost:7777`
- Redis: `redis://localhost:6379/0`

### Submit a training job
```bash
curl -X POST http://localhost:8002/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "job_name": "my-resnet",
    "config_path": "/path/to/configs/small.yaml",
    "owner": "your_username",
    "num_gpus": 1
  }'
```

### Check job status
```bash
curl http://localhost:8002/jobs/<job_id>
```

### Manual dev mode
If you want to run services outside Docker during development:

```bash
pip install -r requirements.txt
PYTHONPATH=. uvicorn api.main:app --host 0.0.0.0 --port 8001
PYTHONPATH=. python -m node_agent.__main__ --owner your_username --redis-url redis://localhost:6379/0 --port 7777
```

Use either the Docker API on `8002` or the manual API on `8001`, not both at once.

---

## Docker Compose (local cluster)

```bash
cd docker/
docker compose up
# API → http://localhost:8000
# MLflow → http://localhost:5000 (run with --profile mlflow)
```

---

## macOS Menu Bar App

```bash
cd desktop/macos/
./build.sh
# → dist/DTrain-0.1.0.dmg
```

Drag to Applications, launch. The ● icon in your menu bar shows:
- Contribution status and compute-units earned
- Credits available
- Number of peers online

---

## iPad App

```bash
cd mobile/ios/
npm install
npx expo run:ios       # simulator
npx expo run:ios --device  # physical iPad
```

The iPad app connects to your local node agent (or a Mac mini on the same LAN)
and shows your dashboard, contribution status, and credit balance.

---

## Contribution Credit System

| Hardware | Units/hour | Equivalent GPU minutes/hour contributed |
|----------|-----------|------------------------------------------|
| H100 GPU | 7200 | 120 min A100-equivalent |
| A100 GPU | 3600 | 60 min |
| Mac mini M3 | 1260 | 21 min |
| Mac mini M2 | 1008 | 16.8 min |
| iPad M2 | 432 | 7.2 min |
| iPad M1 | 288 | 4.8 min |

### User Tiers

| Tier | Requirement | Max GPUs | Max Job | Cloud Backup |
|------|-------------|----------|---------|--------------|
| Free | signup | 1 | 1 hour | ✗ |
| Contributor | 3,600 units | 4 | 12 hours | ✓ |
| Power | 72,000 units | 32 | 72 hours | ✓ |

---

## Project Structure

```
distributed-training/
├── src/
│   ├── trainer/          # DDP + FSDP trainers
│   ├── scheduler/        # Job queue (Redis) + resource manager
│   ├── monitoring/       # Metrics + structured logging
│   ├── config/           # TrainingConfig (YAML-backed)
│   └── utils/            # Checkpoints, data loaders
├── p2p/                  # Peer identity, discovery, gossip, gradient sync
├── ledger/               # Contribution tracking, credits, quotas
├── orchestrator/         # Task dispatch, model sync, fault recovery
├── cloud/                # Encrypted backup, per-user rate limiting
├── node_agent/           # Agent that runs on each device
├── api/                  # FastAPI REST server
├── desktop/macos/        # macOS menu bar app + .dmg packaging
├── mobile/ios/           # React Native iPad app
├── docker/               # Dockerfiles + compose
├── k8s/                  # Kubernetes manifests
└── configs/              # small / medium / large training configs
```

---

## Scaling to 1000 Users

The system is designed to scale by adding infrastructure, not rewriting code:

| Component | 20 users | 1000 users |
|-----------|----------|------------|
| Redis | Single instance | Redis Cluster (6 shards) |
| API | 1 pod | HPA: 2–10 pods |
| Workers | 2–4 pods | 50–200 pods |
| P2P gossip | LAN UDP | libp2p DHT (planned) |
| Metrics | MLflow | Prometheus + Grafana (planned) |

See `TECH_STACK.md` for the full technology roadmap.
