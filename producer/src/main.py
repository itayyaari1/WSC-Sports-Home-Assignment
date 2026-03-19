import sys

from shared.logger import get_logger
from src.scraper import make_scraper, ScraperError
from src.parquet_builder import ParquetBuilder
from src.kafka_producer import PositionProducer

logger = get_logger(__name__)

def run():
    """Main producer pipeline: scrape -> parquet -> kafka."""
    logger.info("Starting WSC Sports position producer")

    # Step 1: Scrape positions
    scraper = make_scraper()
    try:
        positions = scraper.scrape()
    except ScraperError as e:
        logger.error("Scraping failed: %s", e)
        sys.exit(1)

    # Step 2: Build parquet
    builder = ParquetBuilder()
    try:
        parquet_bytes = builder.build(positions)
    except ValueError as e:
        logger.error("Parquet build failed: %s", e)
        sys.exit(1)

    # Step 3: Publish to Kafka
    producer = PositionProducer()
    try:
        producer.publish(parquet_bytes, record_count=len(positions))
    except Exception as e:
        logger.error("Kafka publish failed: %s", e)
        sys.exit(1)

    logger.info("Producer pipeline completed successfully")


if __name__ == "__main__":
    run()
