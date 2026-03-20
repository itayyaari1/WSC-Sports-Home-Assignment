from datetime import datetime, timezone

from confluent_kafka import Producer

from shared.logger import get_logger
from src.config import settings

logger = get_logger(__name__)

_producer: Producer | None = None


def _get_producer() -> Producer:
    global _producer
    if _producer is None:
        _producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "security.protocol": settings.kafka_security_protocol,
            }
        )
        logger.info("DLQ producer created, target topic '%s'", settings.dlq_topic)
    return _producer


def _delivery_report(err, msg) -> None:
    if err:
        logger.error(
            "DLQ delivery failed for topic=%s partition=%d: %s",
            msg.topic(),
            msg.partition(),
            err,
        )
    else:
        logger.debug(
            "DLQ message delivered to topic=%s partition=%d offset=%d",
            msg.topic(),
            msg.partition(),
            msg.offset(),
        )


def publish_to_dlq(raw_bytes: bytes, error_reason: str, original_topic: str) -> None:
    """Publish a failed message to the DLQ topic with error metadata in headers.

    Headers attached:
        error-reason    – human-readable description of why processing failed
        original-topic  – the Kafka topic the message was originally consumed from
        failed-at       – UTC ISO-8601 timestamp of the failure
    """
    producer = _get_producer()
    headers = [
        ("error-reason", error_reason.encode()),
        ("original-topic", original_topic.encode()),
        ("failed-at", datetime.now(timezone.utc).isoformat().encode()),
    ]
    producer.produce(
        topic=settings.dlq_topic,
        value=raw_bytes,
        headers=headers,
        on_delivery=_delivery_report,
    )
    producer.flush()
    logger.warning(
        "Message forwarded to DLQ topic '%s': %s",
        settings.dlq_topic,
        error_reason,
    )
