import io
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pyarrow.parquet as pq
import pytest

from src.models import EnrichedPosition
from src.storage import generate_s3_key, enriched_to_parquet_bytes


def _make_enriched(index=1, title="Test Engineer") -> EnrichedPosition:
    return EnrichedPosition(
        index=index,
        title=title,
        url="https://wsc-sports.com/Careers/1",
        category="Engineering",
        seniority_level="Mid",
        years_of_experience=2,
        skills_count=4,
        complexity_score=50,
    )


class TestGenerateS3Key:
    @patch("src.storage.datetime")
    def test_key_format(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 18, 14, 30, 22, 123456, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        key = generate_s3_key()
        assert key == "positions/year=2026/month=03/day=18/positions_20260318143022123456.parquet"

    def test_key_starts_with_positions(self):
        key = generate_s3_key()
        assert key.startswith("positions/year=")
        assert key.endswith(".parquet")


class TestEnrichedToParquetBytes:
    def test_produces_valid_parquet(self):
        parquet_bytes = enriched_to_parquet_bytes([_make_enriched()])
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

        key = uploader.upload([_make_enriched()])

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "wsc-positions-data"
        assert call_kwargs["Key"].startswith("positions/")
        assert call_kwargs["Key"].endswith(".parquet")

    @patch("src.storage.boto3")
    def test_retry_on_transient_client_error(self, mock_boto3):
        """Test that transient ClientError triggers a retry and succeeds on second attempt."""
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        mock_client.put_object.side_effect = [
            ClientError({"Error": {"Code": "ServiceUnavailable"}}, "PutObject"),
            None,
        ]

        from src.storage import S3Uploader
        uploader = S3Uploader()

        key = uploader.upload([_make_enriched()])

        assert mock_client.put_object.call_count == 2
        assert key is not None

    @patch("src.storage.boto3")
    def test_exhausted_retries_raise_client_error(self, mock_boto3):
        """Test that exhausting retries propagates the ClientError."""
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        mock_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "PutObject"}}, "PutObject"
        )

        from src.storage import S3Uploader
        uploader = S3Uploader()

        with pytest.raises((ClientError, Exception)):
            uploader.upload([_make_enriched()])

        assert mock_client.put_object.call_count == 3

    @patch("src.storage.boto3")
    def test_empty_list_raises_error(self, mock_boto3):
        """Test that uploading an empty list raises ValueError."""
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        from src.storage import S3Uploader
        uploader = S3Uploader()

        with pytest.raises(ValueError, match="Refusing to upload empty"):
            uploader.upload([])

        mock_client.put_object.assert_not_called()
