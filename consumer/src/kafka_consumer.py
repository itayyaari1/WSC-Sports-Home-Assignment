import pandas as pd
from confluent_kafka import Consumer, KafkaError

from shared.logger import get_logger
from shared.parquet_io import read_parquet_bytes
from src.config import settings

logger = get_logger(__name__)

# Imported lazily here to avoid a circular import; dlq_producer depends on config only.
def _send_to_dlq(raw_bytes: bytes, reason: str, topic: str) -> None:
    from src.dlq_producer import publish_to_dlq  # noqa: PLC0415
    publish_to_dlq(raw_bytes, reason, topic)


def create_consumer() -> Consumer:
    """Create and return a configured Kafka consumer."""
    config = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "security.protocol": settings.kafka_security_protocol,
        "group.id": settings.kafka_group_id,
        "auto.offset.reset": settings.kafka_auto_offset_reset,
        "enable.auto.commit": False,
    }
    consumer = Consumer(config)
    consumer.subscribe([settings.kafka_topic])
    logger.info(
        "Subscribed to topic '%s' with group '%s'",
        settings.kafka_topic,
        settings.kafka_group_id,
    )
    return consumer


def poll_message(consumer: Consumer) -> tuple[pd.DataFrame, bytes] | None:
    """Poll for a single message and return (DataFrame, raw_bytes), or None.

    If the message payload cannot be deserialized the raw bytes are forwarded to
    the DLQ and the offset is committed so the consumer can move on.
    """
    msg = consumer.poll(timeout=settings.kafka_poll_timeout)

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
        {k: v.decode() if isinstance(v, bytes) else v for k, v in headers.items()},
    )

    raw_bytes = msg.value()
    try:
        df = read_parquet_bytes(raw_bytes)
    except Exception as exc:
        logger.error("Failed to deserialize message payload: %s", exc)
        _send_to_dlq(raw_bytes, f"deserialization error: {exc}", msg.topic())
        commit_offset(consumer)
        return None

    logger.info("Deserialized parquet with %d rows", len(df))
    return df, raw_bytes


def commit_offset(consumer: Consumer) -> None:
    """Manually commit the current offset."""
    consumer.commit(asynchronous=False)
    logger.info("Offset committed")
