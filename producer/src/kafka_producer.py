import logging
import time

from confluent_kafka import Producer, KafkaError, KafkaException

from src.config import settings

logger = logging.getLogger(__name__)


def _delivery_callback(err, msg):
    """Called once per message to indicate delivery result."""
    if err is not None:
        logger.error("Message delivery failed: %s", err)
    else:
        logger.info(
            "Message delivered to %s [partition %d] at offset %d",
            msg.topic(),
            msg.partition(),
            msg.offset(),
        )


def create_producer() -> Producer:
    """Create and return a configured Kafka producer."""
    config = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "security.protocol": settings.kafka_security_protocol,
        "acks": "all",
        "enable.idempotence": True,
        "compression.type": "snappy",
        "retries": 5,
        "retry.backoff.ms": 500,
    }
    return Producer(config)


def publish_parquet(producer: Producer, parquet_bytes: bytes, record_count: int) -> None:
    """Publish parquet bytes to the Kafka topic."""
    headers = {
        "timestamp": str(int(time.time())),
        "record_count": str(record_count),
        "source": settings.careers_url,
    }

    try:
        producer.produce(
            topic=settings.kafka_topic,
            value=parquet_bytes,
            headers=headers,
            callback=_delivery_callback,
        )
        # Wait for delivery confirmation
        producer.flush(timeout=30)
        logger.info("Parquet message published to topic '%s'", settings.kafka_topic)
    except (KafkaError, KafkaException) as e:
        logger.error("Failed to publish message to Kafka: %s", e)
        raise
