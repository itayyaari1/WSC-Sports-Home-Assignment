import io
import logging

import pandas as pd
import pyarrow.parquet as pq
from confluent_kafka import Consumer, KafkaError

from src.config import settings

logger = logging.getLogger(__name__)


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


def deserialize_parquet(data: bytes) -> pd.DataFrame:
    """Deserialize parquet bytes into a pandas DataFrame."""
    buffer = io.BytesIO(data)
    table = pq.read_table(buffer)
    return table.to_pandas()


def poll_message(consumer: Consumer) -> pd.DataFrame | None:
    """Poll for a single message and return as DataFrame, or None if no message."""
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

    df = deserialize_parquet(msg.value())
    logger.info("Deserialized parquet with %d rows", len(df))
    return df


def commit_offset(consumer: Consumer) -> None:
    """Manually commit the current offset."""
    consumer.commit(asynchronous=False)
    logger.info("Offset committed")
