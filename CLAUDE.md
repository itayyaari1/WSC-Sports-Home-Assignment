# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**WSC Sports Position Pipeline** — A data engineering pipeline that scrapes job positions from WSC Sports' careers page, streams them via Kafka, enriches with metadata, and stores in S3.

## Architecture

```
WSC Careers Page → Producer (scrape + parquet) → Kafka → Consumer (enrich + upload) → S3
```

**Key Design Decisions:**
- **confluent-kafka** over kafka-python: Production-grade, actively maintained, better performance
- **In-memory Parquet**: No disk I/O — cleaner and more portable in containers
- **LocalStack for local S3**: Avoids AWS costs during development, identical API
- **Manual offset commit**: Ensures at-least-once delivery — offset committed only after S3 upload succeeds
- **Pydantic Settings**: Typed configuration with validation, auto-loads from env vars
- **Tenacity retries**: Exponential backoff on scraping and S3 uploads for resilience

## Project Structure

```
producer/                    # Scrapes positions, builds parquet, publishes to Kafka
├── src/
│   ├── main.py            # Entry point & orchestration
│   ├── scraper.py         # Web scraping with retry logic
│   ├── parquet_builder.py # DataFrame → Parquet serialization
│   ├── kafka_producer.py  # Kafka message publishing
│   └── config.py          # Pydantic settings from env vars
└── tests/

consumer/                    # Consumes from Kafka, enriches data, uploads to S3
├── src/
│   ├── main.py            # Entry point & consumer loop
│   ├── kafka_consumer.py  # Kafka message consumption
│   ├── enrichment.py      # Category, seniority & complexity scoring
│   ├── storage.py         # S3 upload with retry logic
│   └── config.py          # Pydantic settings from env vars
└── tests/

docker-compose.yml          # Zookeeper, Kafka, LocalStack, Producer, Consumer services
localstack-init/            # LocalStack S3 bucket initialization script
terraform/                  # AWS infrastructure (Phase 2)
helm/                       # Kubernetes deployment charts (Phase 2)
```

## Common Commands

All commands use the Makefile:

```bash
# Development
make build              # Build Docker images
make up                 # Start all services (Kafka, LocalStack, Producer, Consumer)
make down               # Stop services
make logs               # Stream logs from all services
make test               # Run pytest on producer/ and consumer/ tests
make lint               # Run ruff check on producer/src and consumer/src
make clean              # Stop services and remove volumes/images

# Infrastructure (Phase 2 — Terraform)
make infra-init         # terraform init
make infra-plan         # terraform plan (dev)
make infra-apply        # terraform apply (dev)
make infra-destroy      # terraform destroy
```

**Running a single test:**
```bash
cd producer && python -m pytest tests/test_scraper.py -v
cd consumer && python -m pytest tests/test_enrichment.py::test_function_name -v
```

## Data Flow

### Producer
1. Scrapes all positions from `https://wsc-sports.com/Careers`
2. Sorts positions alphabetically and assigns 1-based indices
3. Serializes to in-memory Parquet with schema: `Index (int32)`, `Position_Title (string)`
4. Publishes Parquet bytes to Kafka topic `wsc-positions`

### Consumer
1. Polls Kafka topic `wsc-positions`
2. Deserializes Parquet bytes back to DataFrame
3. Enriches each position with:
   - **category**: Engineering, Product, Design, Operations, or Other (keyword-based)
   - **seniority_level**: Junior, Mid, Senior, or Lead (title keywords)
   - **complexity_score**: 0-100 heuristic (seniority 40pts, category depth 30pts, specificity 15pts, modifiers 15pts)
   - **enriched_at**: UTC timestamp
4. Uploads enriched Parquet to S3 with date-partitioned keys: `positions/year=YYYY/month=MM/day=DD/positions_TIMESTAMP.parquet`
5. Commits Kafka offset only after successful S3 upload (at-least-once guarantee)

### Enrichment Notes
- Enrichment is title-based only (full job descriptions not available from careers listing)
- Production improvement would scrape full descriptions for more accurate scoring (skills count, years of experience)

## Configuration

All configuration via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Kafka broker address |
| `KAFKA_TOPIC` | `wsc-positions` | Kafka topic name |
| `KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT` | Kafka security protocol |
| `KAFKA_GROUP_ID` | `wsc-consumer-group` | Consumer group ID |
| `CAREERS_URL` | `https://wsc-sports.com/Careers` | URL to scrape |
| `SCRAPE_TIMEOUT_SECONDS` | `30` | Scraper timeout |
| `SCRAPE_RETRIES` | `3` | Scraper retry attempts |
| `S3_BUCKET` | `wsc-positions-data` | S3 bucket name |
| `S3_ENDPOINT_URL` | `http://localstack:4566` | S3 endpoint (LocalStack for dev) |
| `AWS_REGION` | `us-east-1` | AWS region |

## Testing

Tests use `pytest` with mocking where appropriate. Structure:

```
producer/tests/
├── test_scraper.py         # Scraper retry logic, parsing
├── test_parquet_builder.py # DataFrame to Parquet serialization

consumer/tests/
├── test_enrichment.py      # Category, seniority, complexity scoring logic
├── test_storage.py         # S3 upload with retries
```

All tests run via `make test`.

## Docker & Local Development

Docker Compose orchestrates:
- **Zookeeper** (port 2181) — Kafka coordination
- **Kafka** (port 9092) — Message broker
- **LocalStack** (port 4566) — S3 simulation
- **Producer** — Runs scraper loop, publishes to Kafka
- **Consumer** — Runs consumer loop, uploads to S3

Services use healthchecks to wait for dependencies. Run `make up` to start all.

## Common Development Patterns

- **Pydantic for config**: Both producer and consumer use `config.py` with Pydantic `BaseSettings` to load and validate env vars
- **Retry logic**: Scraper and storage both use `tenacity` for exponential backoff
- **Kafka offset commit**: Consumer only commits after successful upload to ensure at-least-once delivery
- **In-memory Parquet**: No temporary files — serialize/deserialize in memory for simplicity and portability
