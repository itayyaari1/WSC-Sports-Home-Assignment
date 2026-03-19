import sys
from datetime import datetime, timezone

import pandas as pd

from shared.logger import get_logger
from src.config import settings
from src.enrichment import enrich_positions
from src.kafka_consumer import commit_offset, create_consumer, poll_message
from src.models import BasePosition, EnrichedPosition
from src.storage import upload_to_s3
from src.url_cache import check_and_refresh_cache

logger = get_logger(__name__)


def _df_to_positions(df: pd.DataFrame) -> list[BasePosition]:
    """Convert a raw positions DataFrame into a list of BasePosition models."""
    return [
        BasePosition(index=int(row.Index), title=str(row.Position_Title))
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
            df = poll_message(consumer)

            if df is None:
                continue

            # Check and refresh URL cache
            check_and_refresh_cache(settings.careers_url, settings.url_cache_path)

            # Convert DataFrame rows to Position models
            positions = _df_to_positions(df)

            # Enrich
            try:
                enriched = enrich_positions(positions)
            except Exception as e:
                logger.error("Enrichment failed: %s", e)
                continue

            # Convert enriched models back to DataFrame for storage
            enriched_df = _enriched_to_df(enriched)

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
