import io
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.storage import generate_s3_key, df_to_parquet_bytes


class TestGenerateS3Key:
    @patch("src.storage.datetime")
    def test_key_format(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 18, 14, 30, 22, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        key = generate_s3_key()
        assert key == "positions/year=2026/month=03/day=18/positions_20260318143022.parquet"

    def test_key_starts_with_positions(self):
        key = generate_s3_key()
        assert key.startswith("positions/year=")
        assert key.endswith(".parquet")


class TestDfToParquetBytes:
    def test_produces_valid_parquet(self):
        df = pd.DataFrame({
            "Index": pd.array([1], dtype="int32"),
            "Position_Title": ["Test Engineer"],
            "category": ["Engineering"],
            "seniority_level": ["Mid"],
            "complexity_score": pd.array([50], dtype="int32"),
            "enriched_at": [datetime.now(timezone.utc)],
        })
        parquet_bytes = df_to_parquet_bytes(df)
        table = pq.read_table(io.BytesIO(parquet_bytes))
        assert len(table) == 1
        assert "category" in table.column_names


class TestS3Uploader:
    @patch("src.storage.boto3")
    def test_upload_calls_put_object(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from src.storage import S3Uploader
        uploader = S3Uploader()

        df = pd.DataFrame({
            "Index": pd.array([1], dtype="int32"),
            "Position_Title": ["Test"],
            "category": ["Other"],
            "seniority_level": ["Mid"],
            "complexity_score": pd.array([30], dtype="int32"),
            "enriched_at": [datetime.now(timezone.utc)],
        })

        key = uploader.upload(df)

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "wsc-positions-data"
        assert call_kwargs["Key"].startswith("positions/")
        assert call_kwargs["Key"].endswith(".parquet")
