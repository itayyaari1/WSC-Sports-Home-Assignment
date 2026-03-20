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
- **Manual offset commit**: Ensures at-least-once delivery — offset committed only after S3 upload succeeds or DLQ publish succeeds
- **Dead Letter Queue**: Failed messages (deserialization, enrichment, S3 failure) are routed to `wsc-positions-dlq` with error metadata, avoiding silent drops or infinite retries
- **Pydantic Settings**: Typed configuration with validation, auto-loads from env vars
- **Tenacity retries**: Exponential backoff on scraping and S3 uploads for resilience

## Project Structure

```
shared/                      # Code shared by both producer and consumer
├── logger.py              # Shared logging setup (get_logger)
├── config.py              # SharedBaseSettings (Kafka + careers_url fields)
├── careers_html.py        # Careers page fetch + HTML parsing utilities
└── parquet_io.py          # In-memory Parquet read/write helpers

producer/                    # Scrapes positions, builds parquet, publishes to Kafka
├── src/
│   ├── main.py            # Entry point & orchestration
│   ├── scraper.py         # Web scraping with retry logic (uses shared.careers_html)
│   ├── parquet_builder.py # DataFrame → Parquet serialization (uses shared.parquet_io)
│   ├── kafka_producer.py  # Kafka message publishing
│   └── config.py          # ProducerSettings extends SharedBaseSettings
└── tests/

consumer/                    # Consumes from Kafka, enriches data, uploads to S3
├── src/
│   ├── main.py            # Entry point & consumer loop
│   ├── kafka_consumer.py  # Kafka message consumption (uses shared.parquet_io)
│   ├── dlq_producer.py    # Dead Letter Queue publisher with error metadata headers
│   ├── enrichment.py      # Category, seniority & complexity scoring
│   ├── storage.py         # S3 upload with retry logic (uses shared.parquet_io)
│   ├── url_cache.py       # Careers page URL cache (uses shared.careers_html)
│   └── config.py          # ConsumerSettings extends SharedBaseSettings
└── tests/
   ├── test_enrichment.py  # Category, seniority, complexity scoring logic
   ├── test_storage.py     # S3 upload with retries
   └── test_dlq.py         # Dead Letter Queue routing behavior

docker-compose.yml          # Zookeeper, Kafka, LocalStack, Producer, Consumer services
localstack-init/            # LocalStack S3 bucket initialization script
terraform/                  # AWS infrastructure (Phase 2)
helm/                       # Kubernetes deployment charts (Phase 2)
```

## Common Commands

All commands use the Makefile:

```bash
# Full Docker (simplest)
make build              # Build Docker images
make up                 # Start all services (Kafka, LocalStack, Producer, Consumer)
make down               # Stop services
make logs               # Stream logs from all services
make clean              # Stop services and remove volumes/images

# Local development (Python on host, infra in Docker)
make local-install      # Create .venv in each service dir, symlink .env, install deps
make local-infra        # Start only Kafka + LocalStack in Docker
make run-producer       # Run producer locally (one-shot: scrape → publish → exit)
make run-consumer       # Run consumer locally (long-running poll loop)

# Testing & linting
make test               # Run pytest on producer/ and consumer/ tests
make lint               # Run ruff check on producer/src and consumer/src

# Infrastructure (Phase 2 — Terraform)
make infra-init         # terraform init
make infra-plan         # terraform plan (dev)
make infra-apply        # terraform apply (dev)
make infra-destroy      # terraform destroy
```

**Running a single test:**
```bash
cd producer && ../.venv/bin/python -m pytest tests/test_scraper.py -v
cd consumer && .venv/bin/python -m pytest tests/test_enrichment.py::test_function_name -v
```

**Inspecting output data (LocalStack S3):**
```bash
# List uploaded files
aws --endpoint-url=http://localhost:4566 s3 ls s3://wsc-positions-data/positions/ --recursive

# Download and read a parquet file
aws --endpoint-url=http://localhost:4566 s3 cp s3://wsc-positions-data/<key>.parquet /tmp/out.parquet
cd consumer && .venv/bin/python -c "import pandas as pd; print(pd.read_parquet('/tmp/out.parquet').to_string())"
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
   - **Deserialization failure** → Routes to DLQ with error reason header, commits offset
3. Enriches each position with:
   - **category**: Engineering, Product, Design, Operations, or Other (keyword-based)
   - **seniority_level**: Junior, Mid, Senior, or Lead (title keywords)
   - **complexity_score**: 0-100 heuristic (seniority 40pts, category depth 30pts, specificity 15pts, modifiers 15pts)
   - **enriched_at**: UTC timestamp
   - **Enrichment failure** → Routes to DLQ with error reason header, commits offset
4. Uploads enriched Parquet to S3 with date-partitioned keys: `positions/year=YYYY/month=MM/day=DD/positions_TIMESTAMP.parquet`
   - **Upload failure** → Routes to DLQ with error reason header, commits offset
5. Commits Kafka offset only after successful S3 upload (at-least-once guarantee)

**Dead Letter Queue:**
Messages sent to DLQ include three headers:
- `error-reason`: Human-readable failure description
- `original-topic`: Source topic (e.g., `wsc-positions`)
- `failed-at`: UTC ISO-8601 timestamp

Raw Parquet bytes are preserved, allowing replay to the main topic after fixes.

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
| `DLQ_TOPIC` | `wsc-positions-dlq` | Dead Letter Queue topic name |
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
├── test_dlq.py             # DLQ routing on deserialization/enrichment/upload failures
```

All tests run via `make test` (on host with local venvs) or `make test-docker` (in containers).

## Docker & Local Development

Docker Compose orchestrates:
- **Zookeeper** (port 2181) — Kafka coordination
- **Kafka** (port 9092) — Message broker, exposed on `localhost:9092` for host processes
- **LocalStack** (port 4566) — S3 simulation, exposed on `localhost:4566` for host processes
- **Producer** — Runs scraper loop, publishes to Kafka
- **Consumer** — Runs consumer loop, uploads to S3

Services use healthchecks to wait for dependencies. Run `make up` to start all in Docker, or `make local-infra` + `make run-producer`/`make run-consumer` to run Python on the host.

**Local dev setup notes:**
- `make local-install` creates `producer/.venv` and `consumer/.venv` and symlinks `.env` into each service dir
- `.env` uses `localhost` addresses for Kafka and LocalStack (not Docker hostnames)
- `confluent-kafka` requires `librdkafka` on macOS: `brew install librdkafka`
- The consumer tolerates `UNKNOWN_TOPIC_OR_PART` on startup — it waits until the producer creates the topic

## Common Development Patterns

- **Shared modules**: Common code lives in `shared/` and is imported by both services; avoids duplication of HTML parsing, Parquet I/O, and base config
- **Pydantic for config**: `ProducerSettings` and `ConsumerSettings` both extend `SharedBaseSettings` from `shared/config.py`; service-specific fields are added in each service's `config.py`
- **Retry logic**: Scraper and storage both use `tenacity` for exponential backoff
- **Kafka offset commit**: Consumer commits offset only after successful S3 upload **or** successful DLQ publish (at-least-once guarantee); no message is silently dropped
- **Dead Letter Queue routing**: Three failure modes are caught and routed to DLQ:
  1. Deserialization error (corrupt Parquet payload) in `kafka_consumer.poll_message()`
  2. Enrichment error in `main.run()` enrichment step
  3. S3 upload error in `main.run()` upload step
  - Each message includes error metadata in headers; raw bytes preserved for replay
- **In-memory Parquet**: No temporary files — serialize/deserialize via `shared.parquet_io` helpers in memory for simplicity and portability
