import io

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def write_parquet_bytes(table: pa.Table) -> bytes:
    """Serialize a PyArrow Table to in-memory Parquet bytes (snappy compressed)."""
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


def read_parquet_bytes(data: bytes) -> pd.DataFrame:
    """Deserialize Parquet bytes into a pandas DataFrame."""
    buffer = io.BytesIO(data)
    table = pq.read_table(buffer)
    return table.to_pandas()
