import signal
import sys

from shared.logger import get_logger
from src.kafka_consumer import create_consumer, poll_message, commit_offset
from src.enrichment import enrich_positions
from src.storage import upload_to_s3

logger = get_logger(__name__)

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Received signal %d, shutting down gracefully...", signum)
    _shutdown = True


def run():
    """Main consumer loop: consume -> enrich -> upload -> commit."""
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("Starting WSC Sports position consumer")
    consumer = create_consumer()

    try:
        while not _shutdown:
            df = poll_message(consumer)

            if df is None:
                continue

            # Enrich
            try:
                enriched_df = enrich_positions(df)
            except Exception as e:
                logger.error("Enrichment failed: %s", e)
                continue

            # Upload to S3
            try:
                s3_key = upload_to_s3(enriched_df)
                logger.info("Successfully processed and uploaded to %s", s3_key)
            except Exception as e:
                logger.error("S3 upload failed, will retry on next poll: %s", e)
                continue

            # Commit offset only after successful upload
            commit_offset(consumer)

    except Exception as e:
        logger.error("Unexpected error in consumer loop: %s", e)
        sys.exit(1)
    finally:
        logger.info("Closing consumer")
        consumer.close()

    logger.info("Consumer shut down cleanly")


if __name__ == "__main__":
    run()
