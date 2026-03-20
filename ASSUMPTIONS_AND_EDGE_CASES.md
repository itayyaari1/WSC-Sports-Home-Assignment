# Assumptions and Edge Cases

## 1. Core Assumptions

| ID | Assumption |
|----|-----------|
| A1 | Producer sends both title and URL; consumer receives them directly without resolving. |
| A2 | Job titles are unique identifiers — different seniority/department context always produces a distinct title string. |
| A3 | Each Kafka message is a full position snapshot, not an incremental delta. |
| A4 | `years_of_experience`, `skills_count`, and `url` are intentionally omitted from the S3 output schema. |
| A5 | All services run in UTC; host/container clock offset will skew S3 key partitioning and DLQ timestamps. |
| A6 | Both `wsc-positions` and `wsc-positions-dlq` topics are auto-created by Kafka on first use. |
| A7 | MinIO credentials (`"test"/"test"`) are dev placeholders and must be overridden for production. |
| A8 | SHA-256 of the requirements block HTML uniquely identifies enrichment state; changes outside that block do not invalidate the cache. |

---

## 2. Edge Cases Handled

| ID | What | How |
|----|------|-----|
| E1 | Message processing failure (deserialization / enrichment / S3) | Routed to DLQ with `error-reason`, `original-topic`, `failed-at` headers; offset committed. |
| E2 | Repeated enrichment of unchanged positions | Requirements block hashed (SHA-256); cache hit skips network fetch. |
| E3 | Tombstone (null-payload) Kafka messages | Detected by `msg.value() is None`, silently skipped without DLQ. |
| E4 | Kafka startup noise (`UNKNOWN_TOPIC_OR_PART`, `PARTITION_EOF`) | Logged and ignored; consumer keeps polling until producer creates the topic. |
| E5 | "View Position" CTA text appended to titles in HTML | Stripped before publishing. |
| E6 | Unicode inconsistencies in titles | NFKC normalization applied. |
| E7 | Primary CSS selector returns no results | Falls back to `li > a` selector. |
| E8 | Slow or hanging position detail page | Per-URL 15s timeout; returns `None`, falls back to title-only enrichment. |
| E9 | Transient S3 errors | 3 retries with 1–10s exponential backoff. |
| E10 | Transient scraper network errors | 3 retries with 2–10s exponential backoff. |
| E11 | Consumer crash between poll and upload | Auto-commit disabled; offset committed only after successful S3 upload or DLQ publish. |
| E12 | Empty scrape result | Raises `ValueError` immediately rather than publishing an empty message. |
| E13 | `None` raw bytes sent to DLQ | Coerced to `b""` to avoid `TypeError`. |
| E14 | Missing or corrupted cache file | Treated as empty cache without failing. |

