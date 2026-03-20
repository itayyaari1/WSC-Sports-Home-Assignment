from datetime import datetime, timezone

import boto3
import pyarrow as pa
from botocore.exceptions import ClientError, EndpointConnectionError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from shared.logger import get_logger
from shared.parquet_io import write_parquet_bytes
from src.config import settings
from src.models import EnrichedPosition

logger = get_logger(__name__)

ENRICHED_SCHEMA = pa.schema([
    ("Index", pa.int32()),
    ("Position_Title", pa.string()),
    ("category", pa.string()),
    ("seniority_level", pa.string()),
    ("complexity_score", pa.int32()),
    ("enriched_at", pa.timestamp("us", tz="UTC")),
])


def generate_s3_key() -> str:
    """Generate a date-partitioned S3 key for the parquet file.

    Uses microsecond precision to avoid same-second key collisions.
    """
    now = datetime.now(timezone.utc)
    return (
        f"positions/year={now.year}/month={now.month:02d}/day={now.day:02d}/"
        f"positions_{now.strftime('%Y%m%d%H%M%S%f')}.parquet"
    )


def enriched_to_parquet_bytes(enriched: list[EnrichedPosition]) -> bytes:
    """Serialize a list of EnrichedPosition objects to Parquet bytes."""
    now = datetime.now(timezone.utc)
    table = pa.table(
        {
            "Index": pa.array([e.index for e in enriched], type=pa.int32()),
            "Position_Title": pa.array([e.title for e in enriched], type=pa.string()),
            "category": pa.array([e.category for e in enriched], type=pa.string()),
            "seniority_level": pa.array([e.seniority_level for e in enriched], type=pa.string()),
            "complexity_score": pa.array([e.complexity_score for e in enriched], type=pa.int32()),
            "enriched_at": pa.array([now] * len(enriched), type=pa.timestamp("us", tz="UTC")),
        },
        schema=ENRICHED_SCHEMA,
    )
    return write_parquet_bytes(table)


class S3Uploader:
    """Uploads enriched position data as Parquet files to S3."""

    def __init__(self) -> None:
        kwargs = {
            "service_name": "s3",
            "region_name": settings.aws_region,
            "aws_access_key_id": settings.aws_access_key_id,
            "aws_secret_access_key": settings.aws_secret_access_key,
        }
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        self._client = boto3.client(**kwargs)
        self._bucket = settings.s3_bucket

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ClientError, EndpointConnectionError, ConnectionError)),
        before_sleep=lambda retry_state: logger.warning(
            "S3 upload attempt %d failed, retrying...", retry_state.attempt_number
        ),
    )
    def upload(self, enriched: list[EnrichedPosition]) -> str:
        """Upload enriched positions as parquet to S3.

        Returns:
            The S3 key where the file was uploaded.
        """
        if not enriched:
            raise ValueError("Refusing to upload empty positions list to S3")

        parquet_bytes = enriched_to_parquet_bytes(enriched)
        s3_key = generate_s3_key()

        self._client.put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=parquet_bytes,
            ContentType="application/octet-stream",
        )

        logger.info(
            "Uploaded enriched parquet to s3://%s/%s (%d bytes)",
            self._bucket,
            s3_key,
            len(parquet_bytes),
        )
        return s3_key
