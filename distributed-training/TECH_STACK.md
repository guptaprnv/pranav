# Technology Stack — What's In & What's Coming

## CURRENT (v0.1 — 20-user MVP)

### Training Core
| Component | Tech | Why |
|-----------|------|-----|
| Distributed training | PyTorch DDP + FSDP | Industry standard; scales from 1→1000 GPUs |
| Model state sync | FedAvg over TCP | Simple, proven in federated learning |
| Process launch | `torchrun` (torch.distributed.run) | Native PyTorch elastic launcher |

### P2P Networking
| Component | Tech | Why |
|-----------|------|-----|
| Peer identity | Ed25519 keypair | Permanent, unforgeable identity |
| LAN discovery | mDNS / Bonjour (zeroconf) | Zero-config for Mac mini clusters |
| Cluster gossip | Custom UDP gossip protocol | O(log N) convergence, no central server |
| Gradient sync | TCP length-framed protocol | Reliable delivery for gradient payloads |

### Job Infrastructure
| Component | Tech | Why |
|-----------|------|-----|
| Job queue | Redis sorted sets | Fast, atomic, survives API restarts |
| Resource tracking | Redis + Lua scripts | Atomic allocation without locking |
| API server | FastAPI + Uvicorn | Async, auto-docs, easy to scale |
| Metrics | MLflow (optional) | Self-hostable experiment tracking |

### Contribution Ledger
| Component | Tech | Why |
|-----------|------|-----|
| Session tracking | Redis | Sub-ms reads for heartbeat updates |
| Credit accounting | Redis atomic INCRBYFLOAT | No race conditions |
| Rate limiting | Token bucket in Redis | Per-user daily quotas |

### Desktop / Mobile
| Platform | Tech | Why |
|----------|------|-----|
| macOS menu bar | `rumps` (Python) | Lightweight, native feel |
| macOS packaging | py2app + dmgbuild | Standard .dmg distribution |
| iPad / iOS | React Native (Expo) | Write once, run on iPad + iPhone |

### Cloud Backup
| Component | Tech | Why |
|-----------|------|-----|
| Encryption | AES-256 via Fernet (PBKDF2 key) | User controls key, server can't decrypt |
| Storage | S3 / GCS / Azure / local | Pluggable |

---

## PLANNED (v0.2+ — 1000-user scale)

> These are marked in the code with `# TECH: add later` comments.
> Architecture is designed to accommodate them without rewrites.

### Training
- [ ] **DeepSpeed ZeRO-3** — replace FSDP for extreme model sharding (100B+ params)
- [ ] **Megatron-LM tensor parallelism** — pipeline + tensor parallel for LLMs
- [ ] **Gradient compression** (PowerSGD, 1-bit Adam) — reduce P2P bandwidth 10-100x
- [ ] **Activation checkpointing** — trade compute for memory on low-VRAM devices
- [ ] **Async SGD** — allow stale gradients, remove round synchronization barrier

### P2P Networking
- [ ] **libp2p** — replace custom gossip with battle-tested DHT + Kademlia routing
- [ ] **QUIC transport** (via `aioquic`) — faster than TCP for gradient streams
- [ ] **NAT traversal** — allow nodes behind home routers (STUN/TURN)
- [ ] **WireGuard overlay** — encrypted mesh network across the internet

### Infrastructure
- [ ] **Kubernetes operator** — custom CRD for `DistributedTrainingJob`
- [ ] **SLURM integration** — submit jobs to HPC clusters
- [ ] **Prometheus + Grafana** — replace MLflow for cluster-wide monitoring
- [ ] **Apache Kafka** — replace Redis pub/sub for 10k+ events/sec throughput
- [ ] **Redis Cluster** — shard the job queue for 1000+ concurrent users

### Contribution & Credits
- [ ] **On-chain ledger** (optional) — immutable contribution record via blockchain
- [ ] **Differential privacy** — add noise to gradients before sharing (privacy)
- [ ] **Secure aggregation** — cryptographic gradient aggregation (no coordinator sees raw grads)

### Desktop / Mobile
- [ ] **Swift native iPad app** — full Core ML on-device inference contribution
- [ ] **Metal Performance Shaders** — GPU training on Apple Silicon via MPS backend
- [ ] **Windows installer** — NSIS / WiX for Windows workstation agents
- [ ] **Linux daemon** — systemd service for always-on Linux nodes

### Security
- [ ] **TLS everywhere** — mTLS between all peers
- [ ] **Byzantine fault tolerance** — Krum / Multi-Krum gradient aggregation
- [ ] **Gradient poisoning detection** — anomaly detection on submitted gradients
- [ ] **Rate-limited peer admission** — prevent Sybil attacks on the network

---

## Architecture Decision Records (ADRs)

### Why Redis instead of a database?
For 20 users, Redis is overkill-simple and fast. At 1000 users,
add Redis Cluster — zero code changes, just configuration.
A relational DB would require schema migrations and connection pooling complexity.

### Why FedAvg instead of synchronous AllReduce?
Heterogeneous hardware (Mac mini M3 vs iPad M1 vs A100) means
synchronous AllReduce blocks on the slowest peer. FedAvg is
naturally asynchronous and handles stragglers gracefully.
Switch to AllReduce (NCCL) for homogeneous clusters with DDP.

### Why py2app + rumps instead of Electron?
Electron ships a full Chromium (~100MB). A menu bar agent should be <10MB.
rumps + py2app produces a native .app that uses 0 RAM when idle.
Downside: macOS only. Cross-platform → Electron or Tauri (planned).

### Why React Native for iPad instead of Swift?
Faster iteration for a v0.1. The iPad app is a thin UI shell — all
real logic runs in the Python node agent. When Core ML integration
is needed (on-device inference), swap the compute layer for Swift/C++
while keeping the React Native UI.
