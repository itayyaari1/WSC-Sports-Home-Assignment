import io

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.parquet_builder import ParquetBuilder

POSITIONS = [
    ("Alpha", "https://example.com/career/1"),
    ("Beta", "https://example.com/career/2"),
    ("Charlie", "https://example.com/career/3"),
]


class TestParquetBuilder:
    def test_builds_valid_parquet(self):
        parquet_bytes = ParquetBuilder().build(POSITIONS)

        table = pq.read_table(io.BytesIO(parquet_bytes))
        df = table.to_pandas()

        assert len(df) == 3
        assert list(df.columns) == ["Index", "Position_Title", "Position_URL"]
        assert list(df["Index"]) == [1, 2, 3]
        assert list(df["Position_Title"]) == ["Alpha", "Beta", "Charlie"]
        assert list(df["Position_URL"]) == [
            "https://example.com/career/1",
            "https://example.com/career/2",
            "https://example.com/career/3",
        ]

    def test_index_is_one_based(self):
        parquet_bytes = ParquetBuilder().build([("Only Position", "https://example.com/career/1")])
        table = pq.read_table(io.BytesIO(parquet_bytes))
        df = table.to_pandas()
        assert df["Index"].iloc[0] == 1

    def test_schema_types(self):
        parquet_bytes = ParquetBuilder().build([("Test", "https://example.com/career/1")])
        table = pq.read_table(io.BytesIO(parquet_bytes))
        assert str(table.schema.field("Index").type) == "int32"
        assert str(table.schema.field("Position_Title").type) == "string"
        assert str(table.schema.field("Position_URL").type) == "string"

    def test_raises_on_empty_list(self):
        with pytest.raises(ValueError, match="empty"):
            ParquetBuilder().build([])

    def test_preserves_special_characters(self):
        positions = [
            ("C++ Graphics Engineer", "https://example.com/career/1"),
            ("Full-Stack Developer", "https://example.com/career/2"),
        ]
        parquet_bytes = ParquetBuilder().build(positions)
        table = pq.read_table(io.BytesIO(parquet_bytes))
        df = table.to_pandas()
        assert "C++ Graphics Engineer" in df["Position_Title"].values
        assert "Full-Stack Developer" in df["Position_Title"].values
