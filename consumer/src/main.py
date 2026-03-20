import sys
from datetime import datetime, timezone

import pandas as pd

from shared.logger import get_logger
from src.config import settings
from src.dlq_producer import publish_to_dlq
from src.enrichment import enrich_positions
from src.kafka_consumer import commit_offset, create_consumer, poll_message
from src.models import BasePosition, EnrichedPosition
from src.storage import upload_to_s3

logger = get_logger(__name__)


def _df_to_positions(df: pd.DataFrame) -> list[BasePosition]:
    """Convert a raw positions DataFrame into a list of BasePosition models."""
    return [
        BasePosition(index=int(row.Index), title=str(row.Position_Title), url=str(row.Position_URL))
        for row in df.itertuples(index=False)
    ]


def _enriched_to_df(enriched: list[EnrichedPosition]) -> pd.DataFrame:
    """Convert a list of EnrichedPosition models back to a DataFrame for storage."""
    now = datetime.now(timezone.utc)
    rows = [
        {
            "Index": e.index,
            "Position_Title": e.title,
            "category": e.category,
            "seniority_level": e.seniority_level,
            "complexity_score": e.complexity_score,
            "enriched_at": now,
        }
        for e in enriched
    ]
    return pd.DataFrame(rows)


def run():
    """Main consumer loop: consume -> enrich -> upload -> commit."""
    logger.info("Starting WSC Sports position consumer")
    consumer = create_consumer()

    try:
        while True:
            result = poll_message(consumer)

            if result is None:
                continue

            df, raw_bytes = result

            # Convert DataFrame rows to Position models
            positions = _df_to_positions(df)

            # Enrich
            try:
                enriched = enrich_positions(positions)
            except Exception as e:
                logger.error("Enrichment failed, forwarding to DLQ: %s", e)
                publish_to_dlq(raw_bytes, f"enrichment error: {e}", settings.kafka_topic)
                commit_offset(consumer)
                continue

            # Convert enriched models back to DataFrame for storage
            enriched_df = _enriched_to_df(enriched)

            # Upload to S3
            try:
                s3_key = upload_to_s3(enriched_df)
                logger.info("Successfully processed and uploaded to %s", s3_key)
            except Exception as e:
                logger.error("S3 upload failed after retries, forwarding to DLQ: %s", e)
                publish_to_dlq(raw_bytes, f"s3 upload error: {e}", settings.kafka_topic)
                commit_offset(consumer)
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
