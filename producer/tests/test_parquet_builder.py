import io

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.parquet_builder import ParquetBuilder


class TestParquetBuilder:
    def test_builds_valid_parquet(self):
        positions = ["Alpha", "Beta", "Charlie"]
        parquet_bytes = ParquetBuilder().build(positions)

        table = pq.read_table(io.BytesIO(parquet_bytes))
        df = table.to_pandas()

        assert len(df) == 3
        assert list(df.columns) == ["Index", "Position_Title"]
        assert list(df["Index"]) == [1, 2, 3]
        assert list(df["Position_Title"]) == ["Alpha", "Beta", "Charlie"]

    def test_index_is_one_based(self):
        parquet_bytes = ParquetBuilder().build(["Only Position"])
        table = pq.read_table(io.BytesIO(parquet_bytes))
        df = table.to_pandas()
        assert df["Index"].iloc[0] == 1

    def test_schema_types(self):
        parquet_bytes = ParquetBuilder().build(["Test"])
        table = pq.read_table(io.BytesIO(parquet_bytes))
        assert str(table.schema.field("Index").type) == "int32"
        assert str(table.schema.field("Position_Title").type) == "string"

    def test_raises_on_empty_list(self):
        with pytest.raises(ValueError, match="empty"):
            ParquetBuilder().build([])

    def test_preserves_special_characters(self):
        positions = ["C++ Graphics Engineer", "Full-Stack Developer"]
        parquet_bytes = ParquetBuilder().build(positions)
        table = pq.read_table(io.BytesIO(parquet_bytes))
        df = table.to_pandas()
        assert "C++ Graphics Engineer" in df["Position_Title"].values
        assert "Full-Stack Developer" in df["Position_Title"].values
