# WSC Sports — Position Pipeline

A data engineering pipeline that scrapes job positions from WSC Sports' careers page, streams them through Kafka, enriches with metadata, and stores in S3-compatible storage (MinIO).

---

## Architecture

```
┌─────────────┐    ┌──────────────────────┐    ┌───────┐    ┌──────────────────────┐    ┌───────┐
│ WSC Careers │───>│      Producer        │───>│ Kafka │───>│       Consumer       │───>│ MinIO │
│    Page     │    │  scrape → parquet    │    │       │    │  enrich → upload     │    │  (S3) │
└─────────────┘    └──────────────────────┘    └───────┘    └──────────────────────┘    └───────┘
```

### Data Flow

**Producer**
1. Scrapes all open positions from [wsc-sports.com/Careers](https://wsc-sports.com/Careers)
2. Sorts alphabetically and assigns 1-based indices
3. Serializes to in-memory Parquet: `Index (int32)`, `Position_Title (string)`
4. Publishes Parquet bytes to Kafka topic `wsc-positions`

**Consumer**
1. Polls Kafka for messages
2. Deserializes Parquet bytes back to DataFrame
3. Enriches each position (see table below)
4. Uploads enriched Parquet to MinIO with date-partitioned keys
5. Commits Kafka offset only after a successful upload (at-least-once guarantee)

**Enrichment columns added by the consumer:**

| Column | Description |
|--------|-------------|
| `category` | Engineering, Product, Design, Operations, or Other — keyword-based |
| `seniority_level` | Junior, Mid, Senior, or Lead — title keyword matching |
| `complexity_score` | 0–100 heuristic (seniority 40pts, category 30pts, specificity 15pts, modifiers 15pts) |
| `enriched_at` | UTC timestamp |

**S3 output layout:**
```
s3://wsc-positions-data/
  └── positions/
      └── year=2026/
          └── month=03/
              └── day=19/
                  └── positions_20260319143022.parquet
```

---

## Project Structure

```
WSC-Sports-Home-Assignment/
│
├── shared/                        # Code shared by both services
│   ├── logger.py                  # Shared logging setup
│   ├── config.py                  # SharedBaseSettings (Kafka + careers_url)
│   ├── careers_html.py            # Careers page fetch + HTML parsing
│   └── parquet_io.py              # In-memory Parquet read/write helpers
│
├── producer/                      # One-shot scraper → Kafka publisher
│   ├── src/
│   │   ├── main.py                # Entry point & orchestration
│   │   ├── scraper.py             # Web scraping with tenacity retry logic
│   │   ├── parquet_builder.py     # DataFrame → Parquet serialization
│   │   ├── kafka_producer.py      # Kafka message publishing
│   │   └── config.py              # ProducerSettings (extends SharedBaseSettings)
│   ├── tests/
│   │   ├── test_scraper.py
│   │   └── test_parquet_builder.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── consumer/                      # Long-running Kafka consumer → S3 uploader
│   ├── src/
│   │   ├── main.py                # Entry point & poll loop
│   │   ├── kafka_consumer.py      # Kafka message consumption
│   │   ├── enrichment.py          # Category, seniority & complexity scoring
│   │   ├── storage.py             # S3 upload with tenacity retry logic
│   │   ├── url_cache.py           # Careers page URL cache
│   │   └── config.py              # ConsumerSettings (extends SharedBaseSettings)
│   ├── tests/
│   │   ├── test_enrichment.py
│   │   └── test_storage.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── helm/                          # Kubernetes deployment (Minikube / any cluster)
│   └── wsc-pipeline/
│       ├── Chart.yaml             # Umbrella chart — depends on bitnami/kafka + bitnami/minio
│       ├── values.yaml            # All configurable values
│       └── templates/
│           ├── _helpers.tpl       # Shared template helpers
│           ├── configmap.yaml     # Shared env vars for all pods
│           ├── secret.yaml        # MinIO credentials as K8s Secret
│           ├── minio-init-job.yaml   # Post-install hook — creates S3 bucket
│           ├── producer-job.yaml     # One-shot Kubernetes Job
│           └── consumer-deployment.yaml  # Long-running Kubernetes Deployment
│
├── terraform/                     # AWS infrastructure (Phase 2)
├── docker-compose.yml             # Full local stack (Kafka + MinIO + Producer + Consumer)
├── .env.example                   # Environment variable reference
└── Makefile                       # All convenience commands
```

---

## Running via Docker Compose

The simplest way to run the full pipeline locally. Everything runs in containers.

**Prerequisites:** Docker

```bash
# Build images and start all services
make up

# Stream logs from all services
make logs

# Stop all services
make down

# Stop and remove volumes + images
make clean
```

Services started:
- **Zookeeper** — Kafka coordination (internal)
- **Kafka** — message broker (localhost:9092)
- **MinIO** — S3-compatible storage (API: localhost:9000, Console: localhost:9001)
- **Producer** — runs once: scrape → publish → exit
- **Consumer** — long-running poll loop → enrich → upload

**View uploaded files:** Open the MinIO console at **http://localhost:9001**  
Login: `minioadmin` / `minioadmin` → browse `wsc-positions-data/positions/`

### Running services on the host (infra in Docker)

Useful for development with fast iteration — Python runs on your machine, Kafka + MinIO in Docker.

**Prerequisites:** Python 3.11+, and on macOS: `brew install librdkafka`

```bash
# 1. Create virtual environments and install dependencies
make local-install

# 2. Start Kafka + MinIO in Docker
make local-infra

# 3. Terminal 1 — start the consumer (polls continuously)
make run-consumer

# 4. Terminal 2 — run the producer (scrapes, publishes, exits)
make run-producer
```

---

## Running via Kubernetes (Minikube)

Deploys the full pipeline on a local Kubernetes cluster using Helm.

**Prerequisites:**
```bash
brew install minikube helm kubectl
```

The Helm chart deploys:
- **Kafka** (Bitnami chart, KRaft mode — no ZooKeeper)
- **MinIO** (Bitnami chart, standalone mode)
- **MinIO init Job** — creates the `wsc-positions-data` bucket (Helm post-install hook)
- **Producer** — Kubernetes Job (one-shot, waits for Kafka via init container)
- **Consumer** — Kubernetes Deployment (long-running, waits for Kafka + MinIO via init containers)

### Step-by-step deployment

```bash
# 1. Start Minikube with enough resources for Kafka + MinIO
make minikube-start

# 2. Build producer & consumer images inside Minikube's Docker daemon
#    (imagePullPolicy: Never — no registry needed)
make minikube-build

# 3. Pull Bitnami sub-chart dependencies and deploy everything
make k8s-up
```

`make k8s-up` takes 3–5 minutes on first run (pulls Bitnami images). It blocks until all pods are healthy.

### Inspecting the deployment

```bash
# Overview of all pods, jobs, and deployments
make k8s-status

# Producer logs (scraping + Kafka publish)
make k8s-logs-producer

# Consumer logs (streaming — enrich + upload)
make k8s-logs-consumer

# Open the Kubernetes dashboard in your browser
minikube dashboard
```

### Verifying S3 output in MinIO

```bash
# Port-forward MinIO API
kubectl port-forward svc/wsc-pipeline-minio 9000:9000 &

# List uploaded parquet files
mc alias set k8s http://localhost:9000 minioadmin minioadmin
mc ls k8s/wsc-positions-data/positions/ --recursive
```

Or open the MinIO console:
```bash
kubectl port-forward svc/wsc-pipeline-minio 9001:9001 &
# Then visit http://localhost:9001 (minioadmin / minioadmin)
```

### Tear down

```bash
# Remove the Helm release (keeps Minikube running)
make k8s-down

# Stop and delete the Minikube cluster entirely
minikube stop && minikube delete
```

---

## Running Tests

```bash
# Run both test suites inside Docker (no local Python needed)
make test-docker

# Run on the host (requires local venvs from make local-install)
make test
```

---

## Configuration

All configuration via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Kafka broker address |
| `KAFKA_TOPIC` | `wsc-positions` | Kafka topic name |
| `KAFKA_GROUP_ID` | `wsc-consumer-group` | Consumer group ID |
| `KAFKA_AUTO_OFFSET_RESET` | `earliest` | Offset reset policy |
| `CAREERS_URL` | `https://wsc-sports.com/Careers` | URL to scrape |
| `SCRAPE_TIMEOUT_SECONDS` | `30` | Scraper HTTP timeout |
| `SCRAPE_RETRIES` | `3` | Scraper retry attempts |
| `S3_BUCKET` | `wsc-positions-data` | S3 bucket for output |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | S3 endpoint (MinIO for local dev) |
| `AWS_REGION` | `us-east-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | `minioadmin` | S3 access key |
| `AWS_SECRET_ACCESS_KEY` | `minioadmin` | S3 secret key |

---

## Design Decisions

- **confluent-kafka** over kafka-python — production-grade, actively maintained, better performance
- **In-memory Parquet** — no disk I/O in containers, cleaner and more portable
- **MinIO for local S3** — S3-compatible, avoids AWS costs during development; identical API
- **Manual offset commit** — at-least-once delivery guarantee; offset committed only after S3 upload succeeds
- **Pydantic Settings** — typed configuration with validation, auto-loads from env vars
- **Tenacity retries** — exponential backoff on scraping and S3 uploads for resilience
- **Shared module** — `shared/` avoids code duplication between producer and consumer (HTML parsing, Parquet I/O, base config)
- **KRaft Kafka on K8s** — no ZooKeeper sidecar needed, simpler cluster topology
