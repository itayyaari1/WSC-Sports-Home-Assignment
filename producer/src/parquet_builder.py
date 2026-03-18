import io

import pyarrow as pa
import pyarrow.parquet as pq

from shared.logger import get_logger

logger = get_logger(__name__)

SCHEMA = pa.schema([
    ("Index", pa.int32()),
    ("Position_Title", pa.string()),
])


def build_parquet(positions: list[str]) -> bytes:
    """Build an in-memory parquet file from sorted position titles.
    """
    if not positions:
        raise ValueError("Cannot build parquet from empty positions list")

    table = pa.Table.from_arrays(
        arrays=[
            pa.array(range(1, len(positions) + 1), type=pa.int32()),
            pa.array(positions, type=pa.string()),
        ],
        schema=SCHEMA,
    )

    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    parquet_bytes = buffer.getvalue()

    logger.info(
        "Built parquet file: %d positions, %d bytes",
        len(positions),
        len(parquet_bytes),
    )
    return parquet_bytes
