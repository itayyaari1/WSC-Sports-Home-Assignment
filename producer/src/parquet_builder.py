import io
import logging

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

SCHEMA = pa.schema([
    ("Index", pa.int32()),
    ("Position_Title", pa.string()),
])


def build_parquet(positions: list[str]) -> bytes:
    """Build an in-memory parquet file from a sorted list of position titles.

    Args:
        positions: Alphabetically sorted list of position titles.

    Returns:
        Parquet file as bytes.
    """
    if not positions:
        raise ValueError("Cannot build parquet from empty positions list")

    df = pd.DataFrame({
        "Index": range(1, len(positions) + 1),
        "Position_Title": positions,
    })

    # Enforce schema types
    df["Index"] = df["Index"].astype("int32")

    table = pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)

    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    parquet_bytes = buffer.getvalue()

    logger.info(
        "Built parquet file: %d positions, %d bytes",
        len(positions),
        len(parquet_bytes),
    )
    return parquet_bytes
