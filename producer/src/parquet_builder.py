import pyarrow as pa

from shared.logger import get_logger
from shared.parquet_io import write_parquet_bytes

logger = get_logger(__name__)


class ParquetBuilder:
    """Serializes position lists to in-memory Parquet bytes."""

    SCHEMA = pa.schema([
        ("Index", pa.int32()),
        ("Position_Title", pa.string()),
        ("Position_URL", pa.string()),
    ])

    def build(self, positions: list[tuple[str, str]]) -> bytes:
        """Build an in-memory parquet file from sorted (title, url) pairs."""
        if not positions:
            raise ValueError("Cannot build parquet from empty positions list")

        titles, urls = zip(*positions)

        table = pa.Table.from_arrays(
            arrays=[
                pa.array(range(1, len(positions) + 1), type=pa.int32()),
                pa.array(titles, type=pa.string()),
                pa.array(urls, type=pa.string()),
            ],
            schema=self.SCHEMA,
        )

        parquet_bytes = write_parquet_bytes(table)

        logger.info(
            "Built parquet file: %d positions, %d bytes",
            len(positions),
            len(parquet_bytes),
        )
        return parquet_bytes
