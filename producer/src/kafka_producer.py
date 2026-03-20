import time

from confluent_kafka import Producer, KafkaError, KafkaException

from shared.logger import get_logger
from src.config import settings

logger = get_logger(__name__)


class PositionProducer:
    """Publishes Parquet-encoded position data to a Kafka topic."""

    def __init__(self) -> None:
        config = {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "security.protocol": settings.kafka_security_protocol,
            "acks": "all",
            "enable.idempotence": True,
            "compression.type": "snappy",
            "retries": 5,
            "retry.backoff.ms": 500,
        }
        self._producer = Producer(config)
        self._delivery_error = None

    def _delivery_callback(self, err, msg) -> None:
        """Called once per message to indicate delivery result."""
        if err is not None:
            self._delivery_error = err
            logger.error("Message delivery failed: %s", err)
        else:
            logger.info(
                "Message delivered to %s [partition %d] at offset %d",
                msg.topic(),
                msg.partition(),
                msg.offset(),
            )

    def publish(self, parquet_bytes: bytes, record_count: int) -> None:
        """Publish parquet bytes to the Kafka topic."""
        # Guard against None or empty parquet bytes
        if not parquet_bytes:
            raise ValueError("parquet_bytes is None or empty; nothing to publish")

        headers = {
            "timestamp": str(int(time.time())),
            "record_count": str(record_count),
            "source": settings.careers_url,
        }

        try:
            self._producer.produce(
                topic=settings.kafka_topic,
                value=parquet_bytes,
                headers=headers,
                callback=self._delivery_callback,
            )
        except (KafkaError, KafkaException) as e:
            logger.error("Failed to produce message to Kafka: %s", e)
            raise

        # Reset delivery error flag for this publish
        self._delivery_error = None
        unflushed = self._producer.flush(timeout=30)

        if unflushed > 0:
            raise KafkaException(f"flush() timed out with {unflushed} messages undelivered")

        if self._delivery_error is not None:
            raise KafkaException(f"Message delivery failed: {self._delivery_error}")

        logger.info("Parquet message published to topic '%s'", settings.kafka_topic)
