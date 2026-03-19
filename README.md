# WSC Sports — Position Pipeline

A data engineering pipeline that scrapes job positions from WSC Sports' careers page, streams them through Kafka, enriches with metadata, and stores in S3.

## Architecture

```
┌─────────────┐    ┌──────────┐    ┌───────┐    ┌──────────┐    ┌────┐
│ WSC Careers │───>│ Producer │───>│ Kafka │───>│ Consumer │───>│ S3 │
│   Page      │    │(scrape + │    │       │    │(enrich + │    │    │
│             │    │ parquet) │    │       │    │ upload)  │    │    │
└─────────────┘    └──────────┘    └───────┘    └──────────┘    └────┘
```

## Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for running tests locally)

## Quick Start

```bash
# Start all services (Kafka, LocalStack S3, Producer, Consumer)
make up

# View logs
make logs

# Stop everything
make down

# Clean up (remove volumes and images)
make clean
```

## Project Structure

```
├── producer/              # Scrapes positions, builds parquet, publishes to Kafka
│   ├── src/
│   │   ├── main.py        # Entry point & orchestration
│   │   ├── scraper.py     # Web scraping with retry logic
│   │   ├── parquet_builder.py  # DataFrame → Parquet serialization
│   │   ├── kafka_producer.py   # Kafka message publishing
│   │   └── config.py      # Pydantic settings from env vars
│   └── tests/
├── consumer/              # Consumes from Kafka, enriches data, uploads to S3
│   ├── src/
│   │   ├── main.py        # Entry point & consumer loop
│   │   ├── kafka_consumer.py   # Kafka message consumption
│   │   ├── enrichment.py  # Category, seniority & complexity scoring
│   │   ├── storage.py     # S3 upload with retry logic
│   │   └── config.py      # Pydantic settings from env vars
│   └── tests/
├── terraform/             # AWS infrastructure (EKS, MSK, S3, ECR)
├── helm/                  # Kubernetes deployment charts
├── docker-compose.yml     # Local development environment
└── Makefile               # Convenience commands
```

## How It Works

### Producer
1. Scrapes all open positions from [wsc-sports.com/Careers](https://wsc-sports.com/Careers)
2. Sorts positions alphabetically (A-Z) and assigns 1-based indices
3. Serializes to Parquet format (in-memory) with schema: `Index (int32)`, `Position_Title (string)`
4. Publishes the Parquet bytes to Kafka topic `wsc-positions`

### Consumer
1. Polls Kafka for new messages
2. Deserializes Parquet bytes back to DataFrame
3. Runs enrichment pipeline (see below)
4. Uploads enriched Parquet to S3 with date-partitioned keys
5. Commits Kafka offset only after successful upload (at-least-once guarantee)

### Enrichment

Each position is enriched with:

| Column | Description |
|--------|-------------|
| `category` | Engineering, Product, Design, Operations, or Other — based on keyword matching |
| `seniority_level` | Junior, Mid, Senior, or Lead — based on title keywords |
| `complexity_score` | 0-100 heuristic score based on seniority (40pts), category depth (30pts), title specificity (15pts), and keyword modifiers (15pts) |
| `enriched_at` | UTC timestamp of enrichment |

**Note:** Enrichment is title-based since we only scrape the careers listing page. In production, scraping full job descriptions would enable more accurate scoring (skills count, years of experience).

## S3 Output Format

```
s3://wsc-positions-data/
  └── positions/
      └── year=2026/
          └── month=03/
              └── day=18/
                  └── positions_20260318143022.parquet
```

Date-partitioned for efficient querying with tools like Athena or Spark.

## Running Locally

Run the Python services on your host machine with infrastructure (Kafka, MinIO) in Docker.

**Prerequisites:** Docker, Python 3.11+, and on macOS: `brew install librdkafka`

```bash
# 1. Install dependencies and set up virtual environments
make local-install

# 2. Start Kafka + MinIO in Docker
make local-infra

# 3. Run the consumer (Terminal 1) — polls Kafka for messages
make run-consumer

# 4. Run the producer (Terminal 2) — scrapes, publishes, and exits
make run-producer
```

**View output data:** Open the MinIO console at **http://localhost:9001** (login: `minioadmin` / `minioadmin`) and browse `wsc-positions-data/positions/`.

## Running Tests

### In Docker (recommended)

Builds the images and runs both test suites inside isolated containers. No Kafka or MinIO infrastructure required — all external dependencies are mocked.

```bash
make test-docker
```

### On the host

Requires Python 3.11+ and the service dependencies installed locally.

```bash
make test
```

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Kafka broker address |
| `KAFKA_TOPIC` | `wsc-positions` | Kafka topic name |
| `S3_BUCKET` | `wsc-positions-data` | S3 bucket for output |
| `S3_ENDPOINT_URL` | `http://localstack:4566` | S3 endpoint (LocalStack for dev) |
| `CAREERS_URL` | `https://wsc-sports.com/Careers` | URL to scrape |

## Design Decisions

- **confluent-kafka** over kafka-python: Production-grade, actively maintained, better performance
- **In-memory Parquet**: No disk I/O in containers — cleaner and more portable
- **LocalStack for local S3**: Avoids AWS costs during development, identical API
- **Manual offset commit**: Ensures at-least-once delivery — offset committed only after S3 upload succeeds
- **Pydantic Settings**: Typed configuration with validation, auto-loads from env vars
- **Tenacity retries**: Exponential backoff on scraping and S3 uploads for resilience

## Infrastructure (Phase 2)

See `terraform/` for AWS infrastructure and `helm/` for Kubernetes deployment charts.

```bash
make infra-init     # terraform init
make infra-plan     # terraform plan (dev)
make infra-apply    # terraform apply (dev)
make infra-destroy  # tear down everything
```
