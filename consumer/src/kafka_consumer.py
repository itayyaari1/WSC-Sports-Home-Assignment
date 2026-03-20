from confluent_kafka import Consumer, KafkaError

from shared.logger import get_logger
from shared.parquet_io import read_parquet_bytes
from src.config import settings
from src.dlq_producer import DlqProducer

logger = get_logger(__name__)


class KafkaConsumer:
    """Consumes Parquet-encoded position messages from a Kafka topic."""

    def __init__(self, dlq_producer: DlqProducer) -> None:
        self._dlq = dlq_producer
        config = {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "security.protocol": settings.kafka_security_protocol,
            "group.id": settings.kafka_group_id,
            "auto.offset.reset": settings.kafka_auto_offset_reset,
            "enable.auto.commit": False,
        }
        self._consumer = Consumer(config)
        self._consumer.subscribe([settings.kafka_topic])
        logger.info(
            "Subscribed to topic '%s' with group '%s'",
            settings.kafka_topic,
            settings.kafka_group_id,
        )

    def poll(self) -> tuple[list[dict], bytes] | None:
        """Poll for a single message and return (DataFrame, raw_bytes), or None.

        If the message payload cannot be deserialized the raw bytes are forwarded to
        the DLQ and the offset is committed so the consumer can move on.
        """
        msg = self._consumer.poll(timeout=settings.kafka_poll_timeout)

        if msg is None:
            return None

        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                logger.debug("Reached end of partition")
                return None
            if msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                logger.debug("Topic not yet available, waiting...")
                return None
            logger.error("Consumer error: %s", msg.error())
            raise Exception(f"Kafka consumer error: {msg.error()}")

        headers = dict(msg.headers()) if msg.headers() else {}
        logger.info(
            "Received message: topic=%s, partition=%d, offset=%d, headers=%s",
            msg.topic(),
            msg.partition(),
            msg.offset(),
            {k: v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v for k, v in headers.items()},
        )

        raw_bytes = msg.value()

        # Guard against tombstone messages (null value)
        if raw_bytes is None:
            logger.warning("Received tombstone message (null value), skipping")
            self.commit_offset()
            return None

        try:
            rows = read_parquet_bytes(raw_bytes)
        except Exception as exc:
            logger.error("Failed to deserialize message payload: %s", exc)
            self._dlq.publish(raw_bytes, f"deserialization error: {exc}", msg.topic())
            self.commit_offset()
            return None

        logger.info("Deserialized parquet with %d rows", len(rows))
        return rows, raw_bytes

    def commit_offset(self) -> None:
        """Manually commit the current offset."""
        self._consumer.commit(asynchronous=False)
        logger.info("Offset committed")

    def close(self) -> None:
        """Close the underlying Kafka consumer."""
        self._consumer.close()
