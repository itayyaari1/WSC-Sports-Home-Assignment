import sys

from shared.logger import get_logger
from src.config import settings
from src.dlq_producer import DlqProducer
from src.enrichment import enrich_positions
from src.kafka_consumer import KafkaConsumer
from src.models import BasePosition
from src.storage import S3Uploader

logger = get_logger(__name__)


def _dicts_to_positions(rows: list[dict]) -> list[BasePosition]:
    """Convert deserialized Parquet rows into a list of BasePosition models."""
    return [
        BasePosition(index=int(row["Index"]), title=str(row["Position_Title"]), url=str(row["Position_URL"]))
        for row in rows
    ]


def run():
    """Main consumer loop: consume -> enrich -> upload -> commit."""
    logger.info("Starting WSC Sports position consumer")

    dlq = DlqProducer()
    consumer = KafkaConsumer(dlq_producer=dlq)
    uploader = S3Uploader()

    try:
        while True:
            result = consumer.poll()

            if result is None:
                continue

            rows, raw_bytes = result

            # Convert deserialized rows to Position models
            try:
                positions = _dicts_to_positions(rows)
            except Exception as e:
                logger.error("Schema conversion failed, forwarding to DLQ: %s", e)
                try:
                    dlq.publish(raw_bytes, f"schema error: {e}", settings.kafka_topic)
                except Exception as dlq_exc:
                    logger.error("DLQ publish also failed: %s", dlq_exc)
                finally:
                    consumer.commit_offset()
                continue

            # Enrich
            try:
                enriched = enrich_positions(positions)
            except Exception as e:
                logger.error("Enrichment failed, forwarding to DLQ: %s", e)
                try:
                    dlq.publish(raw_bytes, f"enrichment error: {e}", settings.kafka_topic)
                except Exception as dlq_exc:
                    logger.error("DLQ publish also failed: %s", dlq_exc)
                finally:
                    consumer.commit_offset()
                continue

            # Upload to S3
            try:
                s3_key = uploader.upload(enriched)
                logger.info("Successfully processed and uploaded to %s", s3_key)
            except Exception as e:
                logger.error("S3 upload failed after retries, forwarding to DLQ: %s", e)
                try:
                    dlq.publish(raw_bytes, f"s3 upload error: {e}", settings.kafka_topic)
                except Exception as dlq_exc:
                    logger.error("DLQ publish also failed: %s", dlq_exc)
                finally:
                    consumer.commit_offset()
                continue

            # Commit offset only after successful upload
            consumer.commit_offset()

    except Exception as e:
        logger.error("Unexpected error in consumer loop: %s", e)
        sys.exit(1)
    finally:
        logger.info("Closing consumer")
        try:
            # Flush any in-flight DLQ messages
            dlq._producer.flush(timeout=30)
        except Exception as e:
            logger.error("Failed to flush DLQ messages: %s", e)
        consumer.close()
        logger.info("Consumer shut down cleanly")


if __name__ == "__main__":
    run()
