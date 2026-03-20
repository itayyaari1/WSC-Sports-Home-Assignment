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
│       ├── Chart.yaml              # Umbrella chart — depends on bitnami/kafka + bitnami/minio
│       ├── values.yaml           # All configurable values
│       └── templates/
│           ├── _helpers.tpl       # Shared template helpers
│           ├── configmap.yaml     # Shared env vars for all pods
│           ├── secret.yaml        # MinIO credentials as K8s Secret
│           ├── minio-init-job.yaml   # Post-install hook — creates S3 bucket
│           ├── producer-job.yaml     # One-shot Kubernetes Job
│           └── consumer-deployment.yaml  # Long-running Kubernetes Deployment
│
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

Deploys the full pipeline on a local Kubernetes cluster using a Helm chart. All infrastructure runs as plain Kubernetes manifests — no external chart dependencies — using the same Docker Hub images as `docker-compose.yml`.

### Prerequisites

```bash
brew install minikube helm kubectl
```

### What gets deployed

| Pod | Type | Image |
|-----|------|-------|
| `wsc-pipeline-zookeeper` | Deployment | `confluentinc/cp-zookeeper:7.5.0` |
| `wsc-pipeline-kafka` | StatefulSet | `confluentinc/cp-kafka:7.5.0` |
| `wsc-pipeline-minio` | Deployment | `minio/minio:latest` |
| `wsc-pipeline-minio-init` | Job (hook) | `minio/mc:latest` — creates the S3 bucket |
| `wsc-pipeline-producer` | Job (one-shot) | `wsc-producer` (built locally) |
| `wsc-pipeline-consumer` | Deployment | `wsc-consumer` (built locally) |

Startup order is enforced by init containers:
- Kafka waits for ZooKeeper
- Producer waits for Kafka
- Consumer waits for both Kafka and MinIO

---

### Step 1 — Start Minikube

```bash
make minikube-start
```

This starts a Minikube cluster with 4 CPUs and 6 GB RAM. Takes ~1 minute on first run.

---

### Step 2 — Build the application images

```bash
make minikube-build
```

This points your Docker CLI at Minikube's internal daemon and builds both `wsc-producer` and `wsc-consumer` images directly inside it. `imagePullPolicy: Never` in the Helm chart means Kubernetes uses these local images without needing a registry.

---

### Step 3 — Deploy everything

```bash
make k8s-up
```

Runs `helm upgrade --install` with a 10-minute timeout. On first run it pulls the infrastructure images (`cp-zookeeper`, `cp-kafka`, `minio/minio`) from Docker Hub — this takes 3–5 minutes. The command blocks until all pods are healthy.

Expected output when complete:
```
Release "wsc-pipeline" has been upgraded. Happy Helming!
```

---

### Step 4 — Check the status

```bash
make k8s-status
```

Expected healthy state:
```
NAME                                          READY   STATUS      AGE
pod/wsc-pipeline-zookeeper-xxx               1/1     Running     5m
pod/wsc-pipeline-kafka-0                     1/1     Running     5m
pod/wsc-pipeline-minio-xxx                   1/1     Running     5m
pod/wsc-pipeline-producer-xxx                0/1     Completed   5m   ← ran and exited OK
pod/wsc-pipeline-consumer-xxx                1/1     Running     5m

job.batch/wsc-pipeline-producer              1/1     Complete    5m
deployment.apps/wsc-pipeline-consumer        1/1     Running     5m
```

---

### Step 5 — Inspect the logs

```bash
# See the producer scrape careers page and publish to Kafka
make k8s-logs-producer

# Stream the consumer enriching positions and uploading to MinIO
make k8s-logs-consumer
```

---

### Step 6 — View output in MinIO

Port-forward the MinIO console to your localhost (keep this terminal open):

```bash
kubectl port-forward svc/wsc-pipeline-minio 9001:9001
```

Then open **http://localhost:9001** in your browser.  
Login: `minioadmin` / `minioadmin`  
Navigate to: `wsc-positions-data → positions → year=... → month=... → day=...`

You should see a `.parquet` file for each producer run.

---

### Step 7 — Re-run the producer (trigger a fresh scrape)

The producer Job runs once on deploy and then completes. To scrape again:

```bash
kubectl delete job wsc-pipeline-producer
make k8s-up
```

This recreates the Job. The always-running consumer picks up the new Kafka message automatically.

---

### Kubernetes dashboard

```bash
make minikube-dashboard
```

Opens the Minikube dashboard in your browser — shows pod status, logs, resource usage, and job history all in one view.

---

### Tear down

```bash
# Remove the Helm release (Minikube cluster keeps running)
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

## Scalability — High Throughput Design

The pipeline is built to handle thousands of records per second from multiple concurrent sources across three layers:

**1. Kafka topic partitioning**  
The `wsc-positions` topic is configured with **3 partitions** (`KAFKA_NUM_PARTITIONS=3`). Multiple producers publishing from independent sources distribute messages across partitions, allowing the broker to absorb high ingest rates without a single-partition bottleneck.

**2. Consumer Group horizontal scaling**  
The consumer runs as a **Consumer Group** (`KAFKA_GROUP_ID=wsc-consumer-group`). Kafka's partition assignment protocol gives each consumer instance exclusive ownership of one partition, so scaling to 3 replicas (`--scale consumer=3` in Docker Compose, `replicaCount: 3` in Helm) means all 3 partitions are drained in parallel — throughput scales linearly with replica count up to the partition count.

**3. Async enrichment with `aiohttp` + `asyncio.gather`**  
Within each consumer instance, enriching a batch of positions used to issue one blocking HTTP request at a time. Now all position-detail pages in a batch are fetched **concurrently** in a single `asyncio.gather` call:

```python
html_pages = asyncio.run(_fetch_all_html(positions))   # all URLs in parallel
enriched   = [_enrich_one(p, html, cache) for p, html in zip(positions, html_pages)]
```

For a batch of N positions this reduces wall-clock fetch time from `O(N × latency)` to `O(max latency)`, eliminating the dominant bottleneck for I/O-bound enrichment.

---

## Design Decisions

- **confluent-kafka** over kafka-python — production-grade, actively maintained, better performance
- **In-memory Parquet** — no disk I/O in containers, cleaner and more portable
- **MinIO for local S3** — S3-compatible, avoids AWS costs during development; identical API
- **Manual offset commit** — at-least-once delivery guarantee; offset committed only after S3 upload succeeds
- **Pydantic Settings** — typed configuration with validation, auto-loads from env vars
- **Tenacity retries** — exponential backoff on scraping and S3 uploads for resilience
- **Shared module** — `shared/` avoids code duplication between producer and consumer (HTML parsing, Parquet I/O, base config)
- **Consistent images across Docker and K8s** — Helm chart uses the same `confluentinc/cp-kafka`, `cp-zookeeper`, and `minio/minio` images as `docker-compose.yml`, avoiding registry or availability issues
