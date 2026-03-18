import logging
import sys

from src.scraper import scrape_positions, ScraperError
from src.parquet_builder import build_parquet
from src.kafka_producer import create_producer, publish_parquet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

def run():
    """Main producer pipeline: scrape -> parquet -> kafka."""
    logger.info("Starting WSC Sports position producer")

    # Step 1: Scrape positions
    try:
        positions = scrape_positions()
    except ScraperError as e:
        logger.error("Scraping failed: %s", e)
        sys.exit(1)

    # Step 2: Build parquet
    try:
        parquet_bytes = build_parquet(positions)
    except ValueError as e:
        logger.error("Parquet build failed: %s", e)
        sys.exit(1)

    # Step 3: Publish to Kafka
    producer = create_producer()
    try:
        publish_parquet(producer, parquet_bytes, record_count=len(positions))
    except Exception as e:
        logger.error("Kafka publish failed: %s", e)
        sys.exit(1)

    logger.info("Producer pipeline completed successfully")


if __name__ == "__main__":
    run()
