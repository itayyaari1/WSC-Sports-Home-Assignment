import io

import pyarrow as pa
import pyarrow.parquet as pq


def write_parquet_bytes(table: pa.Table) -> bytes:
    """Serialize a PyArrow Table to in-memory Parquet bytes (snappy compressed)."""
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


def read_parquet_bytes(data: bytes) -> list[dict]:
    """Deserialize Parquet bytes into a list of row dicts."""
    if data is None:
        raise ValueError("read_parquet_bytes received None; expected bytes")
    if len(data) == 0:
        raise ValueError("read_parquet_bytes received empty bytes; cannot deserialize")
    buffer = io.BytesIO(data)
    table = pq.read_table(buffer)
    return table.to_pylist()
