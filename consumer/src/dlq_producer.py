from datetime import datetime, timezone

from confluent_kafka import Producer

from shared.logger import get_logger
from src.config import settings

logger = get_logger(__name__)


class DlqProducer:
    """Publishes failed messages to the Dead Letter Queue topic with error metadata headers."""

    def __init__(self) -> None:
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "security.protocol": settings.kafka_security_protocol,
            }
        )
        logger.info("DLQ producer created, target topic '%s'", settings.dlq_topic)

    def _delivery_report(self, err, msg) -> None:
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

    def publish(self, raw_bytes: bytes, error_reason: str, original_topic: str) -> None:
        """Publish a failed message to the DLQ topic with error metadata in headers.

        Headers attached:
            error-reason    – human-readable description of why processing failed
            original-topic  – the Kafka topic the message was originally consumed from
            failed-at       – UTC ISO-8601 timestamp of the failure
        """
        headers = [
            ("error-reason", error_reason.encode()),
            ("original-topic", original_topic.encode()),
            ("failed-at", datetime.now(timezone.utc).isoformat().encode()),
        ]
        self._producer.produce(
            topic=settings.dlq_topic,
            value=raw_bytes,
            headers=headers,
            on_delivery=self._delivery_report,
        )
        self._producer.flush()
        logger.warning(
            "Message forwarded to DLQ topic '%s': %s",
            settings.dlq_topic,
            error_reason,
        )
