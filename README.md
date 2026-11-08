# Cloud Computing (CS3081) Mini Project

**End-to-End Sequence-Level Knowledge Distillation, Containerized FastAPI Inference, and Kubernetes Deployment**

- **Student:** Yograj Chahar
- **GitHub Repository:** [yograjchahar05/cc-assignment](https://github.com/yograjchahar05/cc-assignment)
- **Model Release:** [`v1.0.0`](https://github.com/yograjchahar05/cc-assignment/releases/tag/v1.0.0)
- **Final Tag:** `final`

---

## Quickstart Guide

This project provides an automated `Makefile` to build, deploy, test, and tear down the system from a fresh clone in ≤ 3 commands.

### 1. Build and Deploy Full System

To create the local k3d Kubernetes cluster and deploy SeaweedFS object storage, FastAPI inference workloads, and HPA autoscaling:

```bash
make up
```

This runs:
1. `k3d cluster create --config cluster/k3d.yaml`
2. `kubectl apply -f k8s/namespaces.yaml` (creates `app`, `data`, `pipeline`)
3. `kubectl apply -f k8s/secrets.yaml` (injects S3 object storage credentials)
4. `kubectl apply -f k8s/seaweedfs.yaml` (deploys SeaweedFS S3 storage in namespace `data`)
5. `kubectl apply -f k8s/app.yaml` (deploys FastAPI service, ClusterIP, and Ingress in namespace `app`)
6. `kubectl apply -f k8s/hpa.yaml` (deploys HorizontalPodAutoscaler targeting 70% CPU)

---

### 2. Testing and Validation

#### Run Automated Unit Tests
```bash
make test
```
Executes pytest across `tests/test_unit.py` (5 tests covering schema validation, custom headers, and fault injection).

#### Run Linter
```bash
make lint
```
Executes `ruff check service/ worker/ training/ tests/`.

#### Run Stateless NACL Simulator
```bash
python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
```
Verifies stateless packet decisions on public subnet (100% correct).

#### Quality Gate Evaluation
```bash
python tools/score.py results/student_validation.jsonl data/validation.jsonl --min-validity 95
```
Evaluates distilled model outputs on held-out validation queries against the 95% minimum validity quality gate.

---

### 3. Student Model Training (Sequence-Level Distillation)

#### Fast Verification Training (First 50 records)
```bash
make train SUBSET=50
```

#### Full Student Training
```bash
make train
```
Reads configuration exclusively from `training/config.yaml`, trains `EleutherAI/pythia-70m` on CPU in FP32 precision, logs loss per epoch to `training/loss.csv`, saves weights to `models/v1/`, and computes `models/v1/model.sha256`.

---

### 4. Load Testing (Locust)

Run the standard 2-minute load test against the running service:

```bash
locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest
```

Outputs:
- `results/loadtest_stats.csv`: p50, p95, throughput, failure count.
- `results/loadtest_headers.json`: response header counts (`X-Served-By`, `X-Model-Version`).

---

### 5. Tear Down and Cleanup

To delete the cluster and tear down all associated resources:

```bash
make down
```

---

## Repository Structure

```
.
├── .github/workflows/
│   └── ci.yml                 # 5-stage CI/CD pipeline with secret scan & quality gate
├── Makefile                   # Single-command automation: up, down, train, test, lint
├── AI_USE.md                  # Comprehensive AI usage and verification disclosure
├── README.md                  # Project overview and runbook
├── pytest.ini                 # Pytest configuration
├── ruff.toml                  # Linter configuration (line-length: 120)
├── cluster/
│   └── k3d.yaml               # k3d cluster specification with port 8080 mapping
├── data/
│   ├── commands_pool.jsonl    # 3,000 raw SLURP voice commands
│   ├── validation.jsonl       # 100 validation commands (evaluation only)
│   ├── schema.json            # 4-key JSON schema & 8 allowable intents
│   └── rate_card.json         # Hourly cloud pricing rates for cost estimation
├── datasets/
│   ├── teacher/
│   │   ├── shard-0.jsonl      # Worker 0 raw teacher completions (1,500 records)
│   │   └── shard-1.jsonl      # Worker 1 raw teacher completions (1,500 records)
│   └── v1/
│       ├── train.jsonl        # Cleaned dataset (2,935 records, ID-ordered)
│       └── train.sha256       # SHA-256 checksum of train.jsonl
├── k8s/
│   ├── namespaces.yaml        # Namespaces: app, data, pipeline
│   ├── secrets.yaml           # S3 credentials secret
│   ├── seaweedfs.yaml         # SeaweedFS deployment, PVC, and S3 Service
│   ├── app.yaml               # FastAPI Deployment (2 replicas), Service, Ingress
│   ├── hpa.yaml               # HorizontalPodAutoscaler (min 1, max 2, 70% CPU)
│   └── pipeline.yaml          # Modulo sharding parallel worker Pods
├── models/
│   ├── v1/                    # Distilled student model (v1) configs, tokenizers, sha256
│   └── v2/                    # Rolling update model (v2) configs, tokenizers, sha256
├── network/
│   ├── subnets.md             # VLSM subnet allocation table & working for 10.20.0.0/16
│   └── nacl.json              # Stateless NACL rules for public subnet
├── prompts/
│   └── teacher_prompt.txt     # Strict 4-key JSON prompt for teacher model
├── report/
│   ├── report.pdf             # 8-page final project report
│   └── reflection.pdf         # 3-page comprehensive project reflection
├── results/
│   ├── benchmark_50_requests.json # 50-request memory & latency live benchmark
│   ├── loadtest_stats.csv         # Locust load test statistics (p50: 1.6s, p95: 2.2s)
│   ├── loadtest_headers.json      # Load balancing header distribution
│   ├── teacher_validation.json    # Teacher validation scores (97% validity, 49% frame)
│   ├── student_validation.json    # Student validation scores (100% validity, 33% frame)
│   └── untrained_validation.json  # Untrained baseline scores (0% validity, 0% frame)
├── service/
│   ├── app.py                 # FastAPI service (/parse, /healthz, /readyz, FAULT_INJECT)
│   ├── Dockerfile             # Multi-stage CPU-only image (<1.2 GB)
│   └── requirements.txt       # Pinned CPU dependencies
├── tests/
│   └── test_unit.py           # Pytest test suite (5/5 tests passing)
├── tools/
│   ├── check_github_digests.py# Release asset SHA-256 verifier
│   ├── create_release.py      # GitHub Release v1.0.0 creator & asset uploader
│   ├── generate_reflection.py # Generates 3-page reflection.pdf
│   ├── generate_report.py     # Generates 8-page report.pdf
│   ├── locustfile.py          # Locust load testing script
│   ├── nacl_sim.py            # Stateless NACL simulation harness
│   ├── score.py               # Official evaluation & quality gate script
│   └── test_service_live.py   # 50-request benchmark under resource monitoring
└── worker/
    ├── clean.py               # Data cleaning & mathematical identity verification
    └── worker.py              # Parallel worker with modulo sharding logic
```
